"""Evaluation metrics endpoint.

GET /api/evaluation — serve the headline metrics from the latest offline
evaluation run (``evaluation/results.json``, produced by
``scripts/evaluate.py``). This is a read-only view over a static artifact; it
does not trigger an evaluation.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, status

from app.core.logger import get_logger
from app.models.schemas import EvaluationResponse

logger = get_logger(__name__)

router = APIRouter(prefix="/evaluation", tags=["evaluation"])

# app/api/routes/evaluation.py -> parents[3] == backend/
_BACKEND_ROOT = Path(__file__).resolve().parents[3]
RESULTS_PATH = _BACKEND_ROOT / "evaluation" / "results.json"


def _to_response(payload: dict) -> EvaluationResponse:
    """Map a results.json payload onto the flat API response (defensively)."""
    config = payload.get("config", {}) or {}
    retrieval = payload.get("retrieval", {}) or {}
    rca = payload.get("rca", {}) or {}
    perf = payload.get("performance_ms", {}) or {}

    def _mean(section: str) -> float | None:
        block = perf.get(section) or {}
        return block.get("mean")

    return EvaluationResponse(
        generated_at=payload.get("generated_at"),
        num_cases=int(config.get("num_cases", len(payload.get("cases", []) or []))),
        embedding_model=config.get("embedding_model"),
        groq_model=config.get("groq_model"),
        top_k=config.get("top_k"),
        recall_at_5=retrieval.get("recall_at_5"),
        precision_at_5=retrieval.get("precision_at_5"),
        mrr=retrieval.get("mrr"),
        root_cause_correctness=rca.get("root_cause_correctness"),
        mean_root_cause_alignment=rca.get("mean_root_cause_alignment"),
        resolution_relevance=rca.get("resolution_relevance_mean"),
        evidence_support_rate=rca.get("evidence_support_rate"),
        hallucination_rate=rca.get("hallucination_rate"),
        abstention_correct_rate=rca.get("abstention_correct_rate"),
        embedding_latency_ms=_mean("embedding"),
        retrieval_latency_ms=_mean("retrieval"),
        total_rca_latency_ms=_mean("total_rca"),
    )


@router.get(
    "",
    response_model=EvaluationResponse,
    summary="Latest offline evaluation metrics",
)
def get_evaluation() -> EvaluationResponse:
    """Return the headline metrics from the most recent evaluation run."""
    if not RESULTS_PATH.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "No evaluation results found. Run "
                "`uv run python -m scripts.evaluate` to generate them."
            ),
        )
    try:
        payload = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to read evaluation results: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Evaluation results file is unreadable or malformed.",
        ) from exc

    return _to_response(payload)
