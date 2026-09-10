"""LangGraph workflow wiring the RCA pipeline.

    START
      -> analyze
      -> retrieve   (FAISS Top-fetch_k)
      -> rerank     (rerank + select Top-top_k)
      -> evidence_check
      -> conditional routing:
             insufficient -> fallback     -> END
             sufficient   -> generate_rca -> validate -> END

The nodes reuse the existing retriever/reranker/LLM; the only non-deterministic
step is ``generate_rca``. ``fallback`` is a tiny deterministic node (no separate
module needed) that emits the exact 'Not explicitly documented.' response.
"""

from __future__ import annotations

from typing import Literal

from langgraph.graph import END, START, StateGraph

from app.agent.nodes import (
    analyze_node,
    evidence_check_node,
    generate_rca_node,
    rerank_node,
    retrieve_node,
    validate_node,
)
from app.agent.state import RCAState
from app.core.logger import get_logger
from app.models.schemas import NOT_DOCUMENTED, RCAResponse
from app.rag.reranker import DEFAULT_FETCH_K, DEFAULT_FINAL_K

logger = get_logger(__name__)


def _fallback_node(state: RCAState) -> dict:
    """Deterministic fallback when evidence is insufficient: emit the sentinel."""
    reason = state.get("evidence_reason", "Insufficient historical evidence.")
    rca = RCAResponse(
        root_cause=NOT_DOCUMENTED,
        resolution=NOT_DOCUMENTED,
        summary=(
            "Insufficient historical evidence to establish a technical root "
            f"cause. {reason}"
        ),
        supporting_ticket_ids=[],
        confidence="low",
    )
    logger.info("fallback: emitting 'not documented' response")
    return {
        "rca": rca,
        "status": "insufficient_evidence",
        "validation": {
            "citations_checked": True,
            "removed_citations": [],
            "root_cause_documented": False,
            "issues": [],
        },
    }


def _route_after_evidence(state: RCAState) -> Literal["generate", "fallback"]:
    """Conditional edge: pick the branch based on the evidence gate."""
    return "generate" if state.get("evidence_sufficient") else "fallback"


def build_graph():
    """Build and compile the RCA workflow graph."""
    builder = StateGraph(RCAState)

    builder.add_node("analyze", analyze_node)
    builder.add_node("retrieve", retrieve_node)
    builder.add_node("rerank", rerank_node)
    builder.add_node("evidence_check", evidence_check_node)
    builder.add_node("generate_rca", generate_rca_node)
    builder.add_node("validate", validate_node)
    builder.add_node("fallback", _fallback_node)

    builder.add_edge(START, "analyze")
    builder.add_edge("analyze", "retrieve")
    builder.add_edge("retrieve", "rerank")
    builder.add_edge("rerank", "evidence_check")
    builder.add_conditional_edges(
        "evidence_check",
        _route_after_evidence,
        {"generate": "generate_rca", "fallback": "fallback"},
    )
    builder.add_edge("generate_rca", "validate")
    builder.add_edge("validate", END)
    builder.add_edge("fallback", END)

    return builder.compile()


# Compiled once and reused.
rca_graph = build_graph()


def run_rca_graph(
    incident: str,
    fetch_k: int = DEFAULT_FETCH_K,
    top_k: int = DEFAULT_FINAL_K,
) -> RCAState:
    """Run the full workflow for a single incident and return the final state."""
    result: RCAState = rca_graph.invoke(
        {"incident": incident, "fetch_k": fetch_k, "top_k": top_k}
    )
    return result
