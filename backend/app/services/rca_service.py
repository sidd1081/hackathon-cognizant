"""Service layer: run the LangGraph RCA workflow and shape it for the API.

This is a thin adapter over ``app.agent.graph.run_rca_graph`` — it contains no
RCA business logic (retrieval, reranking, generation, validation all live in the
graph/nodes). It only maps the graph's final state onto the HTTP response model.
"""

from __future__ import annotations

from app.agent.graph import run_rca_graph
from app.core.logger import get_logger
from app.models.schemas import AnalyzeResponse, SimilarIncident

logger = get_logger(__name__)


def _to_similar(item) -> SimilarIncident:
    """Map a reranked evidence item to the API ``SimilarIncident`` model.

    Retrieval metadata (FAISS/BM25 scores, per-source ranks, match type) is
    passed through verbatim from the hybrid retriever — this function never
    overwrites or recalculates upstream scores.
    """
    return SimilarIncident(
        ticket_id=item.ticket_id,
        similarity=round(float(item.similarity), 4) if item.similarity is not None else None,
        description=item.description,
        root_cause=item.root_cause,
        resolution=item.resolution,
        match_type=getattr(item, "match_type", "semantic"),
        hybrid_rank=getattr(item, "hybrid_rank", 0),
        bm25_score=round(float(item.bm25_score), 4) if getattr(item, "bm25_score", None) is not None else None,
        rrf_score=round(float(item.rrf_score), 6) if getattr(item, "rrf_score", None) is not None else None,
        faiss_rank=getattr(item, "faiss_rank", None),
        bm25_rank=getattr(item, "bm25_rank", None),
    )


def analyze_incident(description: str) -> AnalyzeResponse:
    """Run the RCA workflow for ``description`` and return the API response.

    Raises whatever the underlying graph raises (e.g. ``RetrievalError``,
    ``LLMError``); the route translates those into HTTP status codes.
    """
    logger.info("Analyzing incident (%d chars)", len(description))
    state = run_rca_graph(description)

    rca = state["rca"]
    evidence = state.get("evidence", [])

    similar = [_to_similar(item) for item in evidence]
    cited = set(rca.supporting_ticket_ids)
    supporting = [inc for inc in similar if inc.ticket_id in cited]

    logger.info(
        "Analysis done: status=%s confidence=%s supporting=%d",
        state.get("status"),
        rca.confidence,
        len(supporting),
    )

    return AnalyzeResponse(
        summary=rca.summary,
        root_cause=rca.root_cause,
        resolution=rca.resolution,
        confidence=rca.confidence.capitalize(),  # low/medium/high -> Low/Medium/High
        similar_incidents=similar,
        supporting_incidents=supporting,
    )
