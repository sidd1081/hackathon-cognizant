"""retrieve node: hybrid FAISS + BM25 retrieval with RRF fusion (stage 1).

Runs both semantic (FAISS) and keyword (BM25) search, fuses results via
Reciprocal Rank Fusion, and returns the unified candidate list.  Falls back
to FAISS-only if the BM25 index is unavailable.
"""

from __future__ import annotations

from app.agent.state import RCAState
from app.core.logger import get_logger
from app.rag.hybrid_retriever import hybrid_retrieve

logger = get_logger(__name__)


def retrieve_node(state: RCAState) -> dict:
    incident = state["normalized_incident"]
    fetch_k = state.get("fetch_k", 10)
    candidates = hybrid_retrieve(incident, top_k=fetch_k)
    logger.info("retrieve: %d hybrid candidate(s)", len(candidates))
    return {"candidates": candidates}

