"""Groq LLM layer for RCA generation (LangChain + langchain-groq).

Reads ``GROQ_API_KEY`` and the model name from Settings — the key is never
hard-coded, logged, or otherwise exposed. Generation is deterministic
(temperature 0) and returns a validated :class:`RCAResponse` via LangChain's
structured-output binding, so the model is constrained to the schema.
"""

from __future__ import annotations

from collections.abc import Sequence
from functools import lru_cache

from app.core.config import settings
from app.core.logger import get_logger
from app.models.schemas import NOT_DOCUMENTED, RCAResponse
from app.rag.prompts import SYSTEM_PROMPT, EvidenceIncident, build_user_prompt

logger = get_logger(__name__)


class LLMError(RuntimeError):
    """Raised when the LLM is unavailable or generation fails."""


@lru_cache
def _build_structured_llm():
    """Build and cache the Groq chat model bound to the RCAResponse schema."""
    if not settings.groq_api_key:
        raise LLMError(
            "GROQ_API_KEY is not set. Add it to backend/.env to enable RCA "
            "generation."
        )
    try:
        from langchain_groq import ChatGroq
    except ImportError as exc:  # pragma: no cover - env issue
        raise LLMError(
            "langchain-groq is not installed; run `uv sync`."
        ) from exc

    logger.info("Initializing Groq chat model: %s", settings.groq_model)
    llm = ChatGroq(
        model=settings.groq_model,
        temperature=settings.llm_temperature,
        api_key=settings.groq_api_key,
        # Ride out free-tier 429s (client backs off per Retry-After) so a burst
        # of requests waits out the per-minute window instead of hard-failing.
        max_retries=settings.groq_max_retries,
    )
    return llm.with_structured_output(RCAResponse)


def _normalize_sentinel(value: str | None) -> str:
    """Map empty/near-miss values to the exact 'Not explicitly documented.'."""
    if value is None:
        return NOT_DOCUMENTED
    text = value.strip()
    if not text:
        return NOT_DOCUMENTED
    if text.rstrip(".").strip().casefold() == "not explicitly documented":
        return NOT_DOCUMENTED
    return text


def _build_rca_messages(
    new_incident: str, incidents: Sequence[EvidenceIncident]
) -> list[object]:
    """Build the Groq messages with technical resolution notes as evidence.

    ``build_user_prompt`` reads ``resolution_notes`` from each incident. Jira
    workflow status is intentionally not added to the prompt, so values such as
    ``Fixed`` cannot be mistaken for a technical resolution.
    """
    from langchain_core.messages import HumanMessage, SystemMessage

    return [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=build_user_prompt(new_incident, incidents)),
    ]


def generate_rca(
    new_incident: str, incidents: Sequence[EvidenceIncident]
) -> RCAResponse:
    """Generate a structured RCA for ``new_incident`` from retrieved evidence.

    Args:
        new_incident: The newly reported incident text.
        incidents: Retrieved historical incidents, including documented
            ``resolution_notes`` used as technical-resolution evidence.

    Returns:
        A validated :class:`RCAResponse`.

    Raises:
        TypeError/ValueError: On invalid input.
        LLMError: If the model is unavailable or generation fails.
    """
    if not isinstance(new_incident, str):
        raise TypeError(
            f"new_incident must be a str, got {type(new_incident).__name__}"
        )
    if not new_incident.strip():
        raise ValueError("new_incident must be a non-empty string.")

    # Guardrail: with no evidence, a technical root cause cannot be established.
    if not incidents:
        logger.info("No evidence provided; returning 'not documented' RCA.")
        return RCAResponse(
            root_cause=NOT_DOCUMENTED,
            resolution=NOT_DOCUMENTED,
            summary="No historical evidence was retrieved for this incident, so "
            "a technical root cause cannot be established.",
            supporting_ticket_ids=[],
            confidence="low",
        )

    structured_llm = _build_structured_llm()
    messages = _build_rca_messages(new_incident, incidents)

    try:
        response = structured_llm.invoke(messages)
    except Exception as exc:  # noqa: BLE001 - surface any provider/parse error
        raise LLMError(f"Groq RCA generation failed: {exc}") from exc

    if not isinstance(response, RCAResponse):  # pragma: no cover - safety net
        raise LLMError(
            f"Unexpected LLM output type: {type(response).__name__}"
        )

    # Enforce the exact sentinel string on the guarded fields.
    response.root_cause = _normalize_sentinel(response.root_cause)
    response.resolution = _normalize_sentinel(response.resolution)
    logger.info(
        "RCA generated (confidence=%s, supporting=%d)",
        response.confidence,
        len(response.supporting_ticket_ids),
    )
    return response
