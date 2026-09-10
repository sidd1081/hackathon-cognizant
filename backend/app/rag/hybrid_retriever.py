"""Hybrid retrieval: FAISS semantic + BM25 keyword search with RRF fusion.

Combines two retrieval sources:

    1. FAISS dense search  — cosine similarity on MiniLM embeddings (semantic)
    2. BM25 sparse search  — Okapi BM25 keyword matching (lexical)

Results are fused using Reciprocal Rank Fusion (RRF):

    RRF_score(d) = Σ  weight_i / (k + rank_i(d))

where ``k`` is a smoothing constant (default 60, per the original RRF paper)
and the sum is over the retrieval sources that returned document ``d``.

The fused candidate list is returned as ``list[RetrievedIncident]`` — the same
interface the rest of the pipeline (reranker, graph nodes) already expects.
"""

from __future__ import annotations

from app.core.logger import get_logger
from app.rag.bm25_store import BM25Store
from app.rag.retriever import (
    RetrievedIncident,
    _format_query,
    get_bm25_store,
    get_vector_store,
)
from app.rag.embeddings import embed_text
from app.rag.vector_store import SearchResult

logger = get_logger(__name__)

# ── RRF defaults ─────────────────────────────────────────────────────────────
# k=60 is the standard RRF smoothing constant from:
#   Cormack, Clarke & Buettcher (2009) "Reciprocal Rank Fusion outperforms
#   Condorcet and individual Rank Learning Methods"
RRF_K = 60

# Per-source candidate pool size (wider than the final top-k to give RRF
# enough diversity from both sources before trimming).
DEFAULT_PER_SOURCE_K = 15

# Default RRF weights — equal weighting is a safe starting point. Tune after
# evaluating on real incident queries if needed.
DEFAULT_FAISS_WEIGHT = 0.5
DEFAULT_BM25_WEIGHT = 0.5


def _rrf_score(rank: int, weight: float, k: int = RRF_K) -> float:
    """Reciprocal rank contribution for a single source."""
    return weight / (k + rank)


def reciprocal_rank_fusion(
    faiss_results: list[SearchResult],
    bm25_results: list[SearchResult],
    *,
    faiss_weight: float = DEFAULT_FAISS_WEIGHT,
    bm25_weight: float = DEFAULT_BM25_WEIGHT,
    k: int = RRF_K,
) -> list[tuple[str, float, SearchResult]]:
    """Fuse two ranked lists via weighted Reciprocal Rank Fusion.

    Returns a list of ``(ticket_id, rrf_score, best_SearchResult)`` tuples,
    sorted by descending RRF score.  When a ticket appears in both lists, the
    ``SearchResult`` from the source with the higher individual contribution
    is kept (so metadata is always from the best-matching source).
    """
    # Accumulate RRF scores and keep track of the best SearchResult per ticket.
    scores: dict[str, float] = {}
    best_hit: dict[str, SearchResult] = {}
    best_contrib: dict[str, float] = {}

    for result in faiss_results:
        tid = result.ticket_id
        contrib = _rrf_score(result.rank, faiss_weight, k)
        scores[tid] = scores.get(tid, 0.0) + contrib
        if contrib > best_contrib.get(tid, -1.0):
            best_hit[tid] = result
            best_contrib[tid] = contrib

    for result in bm25_results:
        tid = result.ticket_id
        contrib = _rrf_score(result.rank, bm25_weight, k)
        scores[tid] = scores.get(tid, 0.0) + contrib
        if contrib > best_contrib.get(tid, -1.0):
            best_hit[tid] = result
            best_contrib[tid] = contrib

    # Sort by descending RRF score.
    fused = [
        (tid, scores[tid], best_hit[tid])
        for tid in scores
    ]
    fused.sort(key=lambda x: x[1], reverse=True)
    return fused


def hybrid_retrieve(
    query: str,
    top_k: int = 10,
    *,
    per_source_k: int = DEFAULT_PER_SOURCE_K,
    faiss_weight: float = DEFAULT_FAISS_WEIGHT,
    bm25_weight: float = DEFAULT_BM25_WEIGHT,
) -> list[RetrievedIncident]:
    """Run hybrid retrieval: FAISS + BM25 → RRF fusion → top_k results.

    Args:
        query: The incident text to search for.
        top_k: How many fused results to return.
        per_source_k: How many candidates each source fetches before fusion.
        faiss_weight: RRF weight for the FAISS (semantic) source.
        bm25_weight: RRF weight for the BM25 (keyword) source.

    Returns:
        A list of ``RetrievedIncident``, ordered by descending RRF score.
        Each incident carries full retrieval metadata (FAISS cosine, BM25
        score, per-source ranks, match type, and hybrid rank).

    Raises:
        TypeError: If ``query`` is not a string.
        ValueError: If ``query`` is empty or ``top_k`` is not positive.
    """
    if not isinstance(query, str):
        raise TypeError(f"query must be a str, got {type(query).__name__}")
    text = query.strip()
    if not text:
        raise ValueError("query must be a non-empty string.")
    if top_k <= 0:
        raise ValueError(f"top_k must be positive, got {top_k}")

    # ── FAISS semantic search ────────────────────────────────────────────────
    store = get_vector_store()
    from app.rag.retriever import _format_query as fmt_query

    formatted = fmt_query(text)
    query_embedding = embed_text(formatted)
    faiss_results = store.search(query_embedding, top_k=per_source_k)
    logger.info("Hybrid: FAISS returned %d candidates", len(faiss_results))

    # ── BM25 keyword search ──────────────────────────────────────────────────
    bm25_results: list[SearchResult] = []
    try:
        bm25_store = get_bm25_store()
        bm25_results = bm25_store.search(text, top_k=per_source_k)
        logger.info("Hybrid: BM25 returned %d candidates", len(bm25_results))
    except Exception as exc:
        # BM25 is supplementary — if it fails, fall back to FAISS-only.
        logger.warning("BM25 search failed, falling back to FAISS-only: %s", exc)

    # ── Build per-source lookup dicts ────────────────────────────────────────
    # These capture the raw retrieval metadata from each source so it can be
    # attached to the fused results.  The reranker and API preserve these
    # verbatim — they are never overwritten or recalculated downstream.
    faiss_cosine: dict[str, float] = {r.ticket_id: r.score for r in faiss_results}
    faiss_rank_map: dict[str, int] = {r.ticket_id: r.rank for r in faiss_results}
    bm25_score_map: dict[str, float] = {r.ticket_id: r.score for r in bm25_results}
    bm25_rank_map: dict[str, int] = {r.ticket_id: r.rank for r in bm25_results}

    faiss_ids = set(faiss_cosine)
    bm25_ids = set(bm25_score_map)

    # ── RRF fusion ───────────────────────────────────────────────────────────
    fused = reciprocal_rank_fusion(
        faiss_results,
        bm25_results,
        faiss_weight=faiss_weight,
        bm25_weight=bm25_weight,
    )

    # Convert to RetrievedIncident (the interface the reranker expects).
    incidents: list[RetrievedIncident] = []
    for rank, (tid, rrf_score, hit) in enumerate(fused[:top_k], start=1):
        # Determine match type
        in_faiss = tid in faiss_ids
        in_bm25 = tid in bm25_ids
        if in_faiss and in_bm25:
            match_type = "semantic+keyword"
        elif in_bm25:
            match_type = "keyword"
        else:
            match_type = "semantic"

        incidents.append(
            RetrievedIncident(
                rank=rank,
                ticket_id=hit.ticket_id,
                project=hit.project,
                summary=hit.summary,
                description=hit.description,
                root_cause=hit.root_cause,
                resolution_status=hit.resolution_status,
                resolution_notes=hit.resolution_notes,
                # FAISS cosine: None for BM25-only hits (not 0.0)
                similarity=faiss_cosine.get(tid),
                # Retrieval metadata
                bm25_score=bm25_score_map.get(tid),
                rrf_score=round(rrf_score, 6),
                faiss_rank=faiss_rank_map.get(tid),
                bm25_rank=bm25_rank_map.get(tid),
                match_type=match_type,
                hybrid_rank=rank,
            )
        )

    logger.info(
        "Hybrid retrieval: %d FAISS + %d BM25 → %d fused (top_k=%d)",
        len(faiss_results),
        len(bm25_results),
        len(incidents),
        top_k,
    )
    return incidents
