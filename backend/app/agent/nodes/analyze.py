"""analyze node: deterministic normalization of the incoming incident.

No LLM. Trims/collapses whitespace, fills in retrieval defaults, and records the
technical terms detected in the incident (reusing the reranker's extractor).
"""

from __future__ import annotations

import re

from app.agent.state import RCAState
from app.core.logger import get_logger
from app.rag.reranker import DEFAULT_FETCH_K, DEFAULT_FINAL_K, technical_terms

logger = get_logger(__name__)

_WHITESPACE = re.compile(r"\s+")


def analyze_node(state: RCAState) -> dict:
    incident = (state.get("incident") or "").strip()
    if not incident:
        raise ValueError("incident must be a non-empty string.")

    normalized = _WHITESPACE.sub(" ", incident)
    fetch_k = state.get("fetch_k") or DEFAULT_FETCH_K
    top_k = state.get("top_k") or DEFAULT_FINAL_K
    terms = sorted(technical_terms(normalized))

    logger.info(
        "analyze: %d chars, %d technical term(s), fetch_k=%d, top_k=%d",
        len(normalized),
        len(terms),
        fetch_k,
        top_k,
    )
    return {
        "normalized_incident": normalized,
        "fetch_k": fetch_k,
        "top_k": top_k,
        "technical_terms": terms,
    }
