"""Health check endpoint."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    """Response body for the health check."""

    status: str


@router.get("/health", response_model=HealthResponse, summary="Liveness probe")
def health_check() -> HealthResponse:
    """Return service liveness status."""
    return HealthResponse(status="ok")
