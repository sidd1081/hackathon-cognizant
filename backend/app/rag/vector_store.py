"""FAISS vector store for historical incident retrieval.

Vectors are the (L2-normalized) ``search_text`` embeddings. Because they are
normalized, a ``faiss.IndexFlatIP`` inner-product search returns cosine
similarity directly.

The index and the metadata are stored in **separate** files:
    * ``index.faiss``   -- the FAISS index (vectors only)
    * ``metadata.pkl``  -- per-vector metadata, row i <-> vector i

Each vector maps to canonical incident metadata. ``search_text`` is embedded;
the root cause and technical resolution notes are retained only as retrieved
evidence. Jira ``resolution_status`` remains separate from the technical
resolution notes.
"""

from __future__ import annotations

import pickle
from dataclasses import asdict, dataclass
from pathlib import Path

import faiss
import numpy as np

from app.core.logger import get_logger

logger = get_logger(__name__)

# backend/app/rag/vector_store.py -> parents[2] == backend/
_BACKEND_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_VECTORSTORE_DIR: Path = _BACKEND_ROOT / "data" / "vectorstore"
DEFAULT_INDEX_PATH: Path = DEFAULT_VECTORSTORE_DIR / "index.faiss"
DEFAULT_METADATA_PATH: Path = DEFAULT_VECTORSTORE_DIR / "metadata.pkl"

# The metadata fields each vector maps to (and their order).
METADATA_FIELDS: tuple[str, ...] = (
    "ticket_id",
    "project",
    "summary",
    "description",
    "components",
    "labels",
    "comments",
    "root_cause",
    "resolution_status",
    "resolution_notes",
    "evidence_quality",
)


@dataclass
class SearchResult:
    """A single retrieval hit: the incident metadata plus its similarity."""

    rank: int
    score: float
    ticket_id: str
    project: str
    summary: str
    description: str
    components: str
    labels: str
    comments: str
    root_cause: str
    resolution_status: str
    resolution_notes: str
    evidence_quality: str

    @property
    def resolution(self) -> str:
        """Compatibility alias for the historical technical resolution.

        This must never expose ``resolution_status`` as technical evidence.
        Callers should migrate to ``resolution_notes``.
        """
        return self.resolution_notes

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class VectorStore:
    """A FAISS ``IndexFlatIP`` index paired with per-vector metadata."""

    def __init__(
        self,
        index: "faiss.Index | None" = None,
        metadata: list[dict[str, str]] | None = None,
    ) -> None:
        self.index = index
        self.metadata: list[dict[str, str]] = list(metadata) if metadata else []

    # -- properties ----------------------------------------------------------
    @property
    def size(self) -> int:
        """Number of vectors currently in the index."""
        return int(self.index.ntotal) if self.index is not None else 0

    @property
    def dimension(self) -> int:
        """Embedding dimension of the index."""
        if self.index is None:
            raise ValueError("Vector store has no index loaded.")
        return int(self.index.d)

    # -- build ---------------------------------------------------------------
    @classmethod
    def build(
        cls, embeddings: np.ndarray, metadata: list[dict[str, str]]
    ) -> "VectorStore":
        """Build a store from normalized embeddings and aligned metadata.

        Args:
            embeddings: ``(n, dim)`` float array of L2-normalized vectors.
            metadata: length-``n`` list; ``metadata[i]`` describes vector ``i``.

        Raises:
            ValueError: On shape/length mismatches or empty input.
        """
        if embeddings.ndim != 2:
            raise ValueError(
                f"embeddings must be 2-D (n, dim), got shape {embeddings.shape}"
            )
        n_vectors, dim = embeddings.shape
        if n_vectors == 0:
            raise ValueError("Cannot build an index from 0 embeddings.")
        if len(metadata) != n_vectors:
            raise ValueError(
                f"metadata length ({len(metadata)}) must match number of "
                f"embeddings ({n_vectors})."
            )

        vectors = np.ascontiguousarray(embeddings, dtype=np.float32)
        index = faiss.IndexFlatIP(dim)
        index.add(vectors)
        logger.info("Built FAISS IndexFlatIP: %d vectors, dim=%d", n_vectors, dim)
        return cls(index=index, metadata=metadata)

    # -- search --------------------------------------------------------------
    def search(
        self, query_embedding: np.ndarray, top_k: int = 5
    ) -> list[SearchResult]:
        """Return the ``top_k`` most similar incidents to a query embedding.

        The query embedding should be L2-normalized (as produced by the
        embedding layer) so scores are cosine similarities in ``[-1, 1]``.
        """
        if self.index is None:
            raise ValueError("Vector store is empty; build or load it first.")
        if top_k <= 0:
            raise ValueError(f"top_k must be positive, got {top_k}")
        if self.size == 0:
            return []

        query = np.asarray(query_embedding, dtype=np.float32)
        if query.ndim == 1:
            query = query.reshape(1, -1)
        if query.shape[0] != 1:
            raise ValueError(
                f"search expects a single query vector, got {query.shape[0]}"
            )
        if query.shape[1] != self.dimension:
            raise ValueError(
                f"query dimension {query.shape[1]} != index dimension "
                f"{self.dimension}"
            )
        query = np.ascontiguousarray(query)

        k = min(top_k, self.size)
        scores, indices = self.index.search(query, k)

        results: list[SearchResult] = []
        for rank, (idx, score) in enumerate(zip(indices[0], scores[0]), start=1):
            if idx < 0:  # FAISS pads with -1 when fewer than k results exist
                continue
            meta = self.metadata[int(idx)]
            results.append(
                SearchResult(
                    rank=rank,
                    score=float(score),
                    ticket_id=str(meta.get("ticket_id", "")),
                    project=str(meta.get("project", "")),
                    summary=str(meta.get("summary", "")),
                    description=str(meta.get("description", "")),
                    components=str(meta.get("components", "")),
                    labels=str(meta.get("labels", "")),
                    comments=str(meta.get("comments", "")),
                    root_cause=str(meta.get("root_cause", "")),
                    resolution_status=str(meta.get("resolution_status", "")),
                    resolution_notes=str(meta.get("resolution_notes", "")),
                    evidence_quality=str(meta.get("evidence_quality", "")),
                )
            )
        return results

    # -- persistence ---------------------------------------------------------
    def save(
        self,
        index_path: str | Path = DEFAULT_INDEX_PATH,
        metadata_path: str | Path = DEFAULT_METADATA_PATH,
    ) -> None:
        """Persist the index and metadata to disk (creating parent dirs)."""
        if self.index is None:
            raise ValueError("Nothing to save: the index has not been built.")
        index_path = Path(index_path)
        metadata_path = Path(metadata_path)
        index_path.parent.mkdir(parents=True, exist_ok=True)
        metadata_path.parent.mkdir(parents=True, exist_ok=True)

        faiss.write_index(self.index, str(index_path))
        payload = {"metadata": self.metadata, "dimension": self.dimension}
        with metadata_path.open("wb") as fh:
            pickle.dump(payload, fh, protocol=pickle.HIGHEST_PROTOCOL)
        logger.info(
            "Saved index -> %s and metadata -> %s", index_path, metadata_path
        )

    @classmethod
    def load(
        cls,
        index_path: str | Path = DEFAULT_INDEX_PATH,
        metadata_path: str | Path = DEFAULT_METADATA_PATH,
    ) -> "VectorStore":
        """Load a previously saved index and metadata from disk."""
        index_path = Path(index_path)
        metadata_path = Path(metadata_path)
        if not index_path.is_file():
            raise FileNotFoundError(f"Index file not found: {index_path}")
        if not metadata_path.is_file():
            raise FileNotFoundError(f"Metadata file not found: {metadata_path}")

        index = faiss.read_index(str(index_path))
        with metadata_path.open("rb") as fh:
            payload = pickle.load(fh)

        # Support both the dict payload and a bare list (defensive).
        if isinstance(payload, dict):
            metadata = payload.get("metadata", [])
        else:
            metadata = payload

        store = cls(index=index, metadata=metadata)
        if store.size != len(store.metadata):
            raise ValueError(
                f"Corrupt store: {store.size} vectors but "
                f"{len(store.metadata)} metadata records."
            )
        logger.info(
            "Loaded FAISS store: %d vectors, dim=%d", store.size, store.dimension
        )
        return store
