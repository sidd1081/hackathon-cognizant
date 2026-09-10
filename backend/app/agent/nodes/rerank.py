"""rerank node: rerank FAISS candidates and select the final Top-``top_k``.

Reuses the existing reranker (semantic + technical + keyword blend); no scoring
logic is duplicated here.
"""

from __future__ import annotations

from app.agent.state import RCAState
from app.core.logger import get_logger
from app.rag.reranker import rerank

logger = get_logger(__name__)


def rerank_node(state: RCAState) -> dict:
    incident = state["normalized_incident"]
    candidates = state.get("candidates", [])
    top_k = state.get("top_k", 5)
    evidence = rerank(incident, candidates, top_k=top_k)
    logger.info("rerank: %d candidate(s) -> Top-%d", len(candidates), len(evidence))
    return {"evidence": evidence}
