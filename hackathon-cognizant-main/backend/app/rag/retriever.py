"""Historical incident retrieval layer.

Given a newly reported incident (free text), embed it and search the FAISS
vector store for the most similar historical incidents:

    new incident -> format query -> embedding -> FAISS search -> Top K

The query text is placed in the description portion of the same three-field
template used when embedding historical incidents, so query and document
vectors occupy the same representation space.

Similarity is the cosine score returned by FAISS (embeddings are normalized, so
inner product == cosine). No LLM is involved in scoring, and historical
evidence is returned verbatim — never modified, never regenerated.
"""
# This is the retrival node
from __future__ import annotations

from dataclasses import asdict, dataclass
from threading import Lock

from app.core.logger import get_logger
from app.preprocessing.transformer import SEARCH_TEXT_TEMPLATE
from app.rag.embeddings import embed_text
from app.rag.vector_store import VectorStore

logger = get_logger(__name__)

_store: VectorStore | None = None
_store_lock = Lock()

_bm25_store: "BM25Store | None" = None  # noqa: F821 - lazy import
_bm25_lock = Lock()


class RetrievalError(RuntimeError):
    """Raised when retrieval cannot be performed (e.g. missing vector store)."""


@dataclass
class RetrievedIncident:
    """A historical incident returned by retrieval, with its similarity score.

    Retrieval metadata (``bm25_score``, ``rrf_score``, ``faiss_rank``,
    ``bm25_rank``, ``match_type``, ``hybrid_rank``) is populated by the hybrid
    retriever and preserved through reranking so the API can surface exactly
    how each result was found.
    """

    rank: int
    ticket_id: str
    project: str
    summary: str
    description: str
    root_cause: str
    resolution_status: str
    resolution_notes: str
    similarity: float | None  # FAISS cosine; None for BM25-only hits

    # ── Hybrid retrieval metadata (populated by hybrid_retriever) ────────────
    bm25_score: float | None = None
    rrf_score: float | None = None
    faiss_rank: int | None = None
    bm25_rank: int | None = None
    match_type: str = "semantic"      # "semantic" | "keyword" | "semantic+keyword"
    hybrid_rank: int = 0              # final RRF-fused position (1-based)

    @property
    def resolution(self) -> str:
        """Compatibility alias for technical resolution evidence only."""
        return self.resolution_notes

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["resolution"] = self.resolution_notes
        return payload


def _format_query(text: str) -> str:
    """Wrap a query in the same template used for historical embeddings.

    A submitted query is incident-description text, so project and summary are
    intentionally blank. Root cause, technical-resolution, and Jira workflow
    fields are never added to the query representation.
    """
    return SEARCH_TEXT_TEMPLATE.format(project="", summary="", description=text)


def set_vector_store(store: VectorStore) -> None:
    """Replace the cached vector store (e.g. after rebuilding the index).

    Ensures subsequent retrievals use the freshly built index without a
    process restart.
    """
    global _store
    with _store_lock:
        _store = store


def get_vector_store() -> VectorStore:
    """Load the FAISS vector store once (thread-safe) and reuse it."""
    global _store
    if _store is None:
        with _store_lock:
            if _store is None:
                try:
                    _store = VectorStore.load()
                except FileNotFoundError as exc:
                    raise RetrievalError(
                        "Vector store not found. Build it first with "
                        "`uv run python -m scripts.build_index`."
                    ) from exc
    return _store


def set_bm25_store(store: "BM25Store") -> None:  # noqa: F821
    """Replace the cached BM25 store (e.g. after rebuilding the index)."""
    global _bm25_store
    with _bm25_lock:
        _bm25_store = store


def get_bm25_store() -> "BM25Store":  # noqa: F821
    """Load the BM25 index once (thread-safe) and reuse it.

    Falls back gracefully: if the pickle doesn't exist, raises
    ``RetrievalError`` which the hybrid retriever catches.
    """
    global _bm25_store
    if _bm25_store is None:
        with _bm25_lock:
            if _bm25_store is None:
                from app.rag.bm25_store import BM25Store

                try:
                    _bm25_store = BM25Store.load()
                except FileNotFoundError as exc:
                    raise RetrievalError(
                        "BM25 index not found. Rebuild with "
                        "`uv run python -m scripts.build_index`."
                    ) from exc
    return _bm25_store

def retrieve_similar_incidents(
    query: str, top_k: int = 5
) -> list[RetrievedIncident]:
    """Return the ``top_k`` historical incidents most similar to ``query``.

    The query is placed in the description slot of the same three-field
    template used for historical embeddings before encoding.

    Args:
        query: The newly reported incident text.
        top_k: How many similar incidents to return (default 5).

    Returns:
        A list of :class:`RetrievedIncident`, ordered by descending similarity.

    Raises:
        TypeError: If ``query`` is not a string.
        ValueError: If ``query`` is empty or ``top_k`` is not positive.
        RetrievalError: If the vector store is unavailable.
    """
    if not isinstance(query, str):
        raise TypeError(f"query must be a str, got {type(query).__name__}")
    text = query.strip()
    if not text:
        raise ValueError("query must be a non-empty string.")
    if top_k <= 0:
        raise ValueError(f"top_k must be positive, got {top_k}")

    store = get_vector_store()
    formatted = _format_query(text)
    query_embedding = embed_text(formatted)
    hits = store.search(query_embedding, top_k=top_k)

    incidents = [
        RetrievedIncident(
            rank=hit.rank,
            ticket_id=hit.ticket_id,
            project=hit.project,
            summary=hit.summary,
            description=hit.description,
            root_cause=hit.root_cause,
            resolution_status=hit.resolution_status,
            resolution_notes=hit.resolution_notes,
            similarity=hit.score,
            faiss_rank=hit.rank,
            match_type="semantic",
        )
        for hit in hits
    ]

    # FAISS already returns hits sorted by descending similarity; sort again
    # defensively so the ordering contract holds regardless of backend.
    incidents.sort(
        key=lambda inc: inc.similarity if inc.similarity is not None else 0.0,
        reverse=True,
    )
    for new_rank, inc in enumerate(incidents, start=1):
        inc.rank = new_rank

    logger.info("Retrieved %d incidents for query (top_k=%d)", len(incidents), top_k)
    return incidents
