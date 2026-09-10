"""BM25 sparse retrieval index for historical incident matching.

Provides keyword-based retrieval using BM25Okapi (Okapi BM25 with Robertson's
IDF variant). This complements the dense FAISS semantic search:

    query → tokenize → BM25 score against corpus → Top K

Tokenization reuses the reranker's ``_keyword_tokens`` logic (lowercased,
stopwords removed, len > 2) so both BM25 and the downstream reranker operate
on the same vocabulary.

The index and corpus metadata are persisted to a single pickle file alongside
the FAISS index (``data/vectorstore/bm25.pkl``).
"""

from __future__ import annotations

import pickle
from pathlib import Path

import numpy as np
from rank_bm25 import BM25Okapi

from app.core.logger import get_logger
from app.rag.vector_store import DEFAULT_VECTORSTORE_DIR, SearchResult

logger = get_logger(__name__)

DEFAULT_BM25_PATH: Path = DEFAULT_VECTORSTORE_DIR / "bm25.pkl"

# ── Tokenizer (shared vocabulary with reranker) ─────────────────────────────
# Import the same helpers the reranker uses so BM25 and the reranker score
# against identical token sets.
from app.rag.reranker import _keyword_tokens  # noqa: E402


def _tokenize(text: str) -> list[str]:
    """Tokenize text for BM25 — same vocabulary as the reranker's keywords."""
    return sorted(_keyword_tokens(text))


class BM25Store:
    """A BM25Okapi index paired with per-document metadata.

    Mirrors the ``VectorStore`` interface (build / search / save / load) so the
    hybrid retriever can treat both sources uniformly.
    """

    def __init__(
        self,
        bm25: BM25Okapi | None = None,
        metadata: list[dict[str, str]] | None = None,
        tokenized_corpus: list[list[str]] | None = None,
    ) -> None:
        self.bm25 = bm25
        self.metadata: list[dict[str, str]] = list(metadata) if metadata else []
        self._tokenized_corpus: list[list[str]] = (
            list(tokenized_corpus) if tokenized_corpus else []
        )

    @property
    def size(self) -> int:
        """Number of documents in the index."""
        return len(self.metadata)

    # ── build ────────────────────────────────────────────────────────────────
    @classmethod
    def build(
        cls, corpus_texts: list[str], metadata: list[dict[str, str]]
    ) -> "BM25Store":
        """Build a BM25 index from raw corpus texts and aligned metadata.

        Args:
            corpus_texts: The same ``search_text`` strings used for FAISS
                embeddings.
            metadata: Per-document metadata dicts (one per corpus text), in the
                same order — identical to what ``VectorStore.build`` receives.

        Returns:
            A ready-to-search ``BM25Store``.

        Raises:
            ValueError: On length mismatches or empty input.
        """
        if len(corpus_texts) == 0:
            raise ValueError("Cannot build a BM25 index from 0 documents.")
        if len(corpus_texts) != len(metadata):
            raise ValueError(
                f"corpus length ({len(corpus_texts)}) must match metadata "
                f"length ({len(metadata)})."
            )

        tokenized = [_tokenize(text) for text in corpus_texts]
        bm25 = BM25Okapi(tokenized)

        logger.info("Built BM25Okapi index: %d documents", len(corpus_texts))
        return cls(bm25=bm25, metadata=metadata, tokenized_corpus=tokenized)

    # ── search ───────────────────────────────────────────────────────────────
    def search(self, query: str, top_k: int = 10) -> list[SearchResult]:
        """Return the ``top_k`` most relevant documents for ``query``.

        Args:
            query: The raw query text (will be tokenized internally).
            top_k: How many results to return.

        Returns:
            A list of ``SearchResult`` ordered by descending BM25 score.

        Raises:
            ValueError: If the index has not been built/loaded or top_k <= 0.
        """
        if self.bm25 is None:
            raise ValueError("BM25 index is empty; build or load it first.")
        if top_k <= 0:
            raise ValueError(f"top_k must be positive, got {top_k}")
        if self.size == 0:
            return []

        tokenized_query = _tokenize(query)
        if not tokenized_query:
            # No meaningful tokens — return empty rather than all-zeros.
            return []

        scores = self.bm25.get_scores(tokenized_query)
        # Get top-k indices sorted by descending score.
        k = min(top_k, self.size)
        top_indices = np.argpartition(scores, -k)[-k:]
        top_indices = top_indices[np.argsort(scores[top_indices])[::-1]]

        results: list[SearchResult] = []
        for rank, idx in enumerate(top_indices, start=1):
            score = float(scores[idx])
            if score <= 0:
                # BM25 scores of 0 mean no term overlap; skip them.
                continue
            meta = self.metadata[int(idx)]
            results.append(
                SearchResult(
                    rank=rank,
                    score=score,
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

    # ── persistence ──────────────────────────────────────────────────────────
    def save(self, path: str | Path = DEFAULT_BM25_PATH) -> None:
        """Persist the BM25 index and metadata to disk."""
        if self.bm25 is None:
            raise ValueError("Nothing to save: the BM25 index has not been built.")
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "bm25": self.bm25,
            "metadata": self.metadata,
            "tokenized_corpus": self._tokenized_corpus,
        }
        with path.open("wb") as fh:
            pickle.dump(payload, fh, protocol=pickle.HIGHEST_PROTOCOL)
        logger.info("Saved BM25 index -> %s (%d documents)", path, self.size)

    @classmethod
    def load(cls, path: str | Path = DEFAULT_BM25_PATH) -> "BM25Store":
        """Load a previously saved BM25 index from disk."""
        path = Path(path)
        if not path.is_file():
            raise FileNotFoundError(f"BM25 index not found: {path}")
        with path.open("rb") as fh:
            payload = pickle.load(fh)

        store = cls(
            bm25=payload["bm25"],
            metadata=payload["metadata"],
            tokenized_corpus=payload.get("tokenized_corpus", []),
        )
        if store.bm25 is not None and store.size != len(store.metadata):
            raise ValueError(
                f"Corrupt BM25 store: corpus size and metadata length differ."
            )
        logger.info("Loaded BM25 store: %d documents", store.size)
        return store
