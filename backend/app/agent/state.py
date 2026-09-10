"""Typed state for the RCA LangGraph workflow.

The graph threads a single ``RCAState`` dict through its nodes. Each node reads
the fields it needs and returns a partial dict update (the default LangGraph
channel behavior overwrites). ``total=False`` because the state is populated
incrementally as the workflow progresses.

Note: the referenced types are imported at runtime (not behind TYPE_CHECKING)
because LangGraph resolves the state's type hints via ``get_type_hints`` when
the graph is compiled.
"""

from __future__ import annotations

from typing import TypedDict

from app.models.schemas import RCAResponse
from app.rag.reranker import RerankedIncident
from app.rag.retriever import RetrievedIncident


class RCAState(TypedDict, total=False):
    """Everything the RCA workflow reads and produces."""

    # --- input ---
    incident: str          # raw incident text (required to start)
    fetch_k: int           # how many candidates FAISS returns (stage 1)
    top_k: int             # how many survive reranking (stage 2)

    # --- analyze ---
    normalized_incident: str
    technical_terms: list[str]

    # --- retrieve / rerank ---
    candidates: list[RetrievedIncident]  # FAISS Top-fetch_k
    evidence: list[RerankedIncident]     # reranked Top-top_k

    # --- evidence check (deterministic routing gate) ---
    evidence_sufficient: bool
    evidence_reason: str

    # --- output ---
    rca: RCAResponse
    validation: dict[str, object]
    status: str            # "generated" | "insufficient_evidence"
