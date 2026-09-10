"""Incident analysis endpoint.

POST /api/incidents/analyze — run the RCA workflow for a newly reported
incident and return the structured analysis plus supporting evidence.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.routes.auth import get_current_user
from app.core.logger import get_logger
from app.models.schemas import AnalyzeRequest, AnalyzeResponse
from app.rag.llm import LLMError
from app.rag.retriever import RetrievalError
from app.services.rca_service import analyze_incident

logger = get_logger(__name__)

router = APIRouter(prefix="/incidents", tags=["incidents"])


@router.post(
    "/analyze",
    response_model=AnalyzeResponse,
    summary="Analyze a newly reported incident",
)
def analyze(
    request: AnalyzeRequest,
    _user: dict = Depends(get_current_user),
) -> AnalyzeResponse:
    """Retrieve similar historical incidents and generate an RCA.

    Requires authentication. The request body is validated by Pydantic (empty
    descriptions -> 422).
    """
    try:
        return analyze_incident(request.description)
    except RetrievalError as exc:
        # Vector store not built yet -> the service is not ready.
        logger.warning("Retrieval unavailable: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    except LLMError as exc:
        # Groq unavailable/misconfigured (never includes the API key).
        logger.warning("LLM unavailable: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except Exception as exc:  # noqa: BLE001 - last-resort guard
        logger.exception("Unexpected error during incident analysis")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error during incident analysis.",
        ) from exc
