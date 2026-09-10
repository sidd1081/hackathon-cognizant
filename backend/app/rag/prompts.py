"""Prompt construction for the RCA LLM layer.

The system prompt encodes the hard rules (evidence-only, no hallucination,
similarity-is-not-proof, the exact 'Not explicitly documented.' fallback). The
user prompt packs the new incident together with the retrieved historical
incidents (similarity, root cause, technical resolution notes) as evidence.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from app.models.schemas import NOT_DOCUMENTED

# Per-field character caps for evidence included in the prompt. Historical Jira
# descriptions can be multi-KB stack traces; packing several verbatim would blow
# the model's token budget (Groq free tier caps requests/minute). Truncation
# affects ONLY what is sent to the LLM — the deterministic validator still uses
# the full evidence text from state, so grounding checks are unaffected.
MAX_DESCRIPTION_CHARS = 1200
MAX_ROOT_CAUSE_CHARS = 700
MAX_RESOLUTION_CHARS = 700
MAX_NEW_INCIDENT_CHARS = 2000


def _clip(text: str, limit: int) -> str:
    """Truncate ``text`` to ``limit`` chars on a word boundary, adding an ellipsis.

    Missing/empty values pass through unchanged so sentinels stay verbatim.
    """
    if not text:
        return text
    text = text.strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    # Prefer to break at the last space so we don't split a token mid-word.
    space = cut.rfind(" ")
    if space > limit * 0.6:
        cut = cut[:space]
    return cut.rstrip() + " […]"


@runtime_checkable
class EvidenceIncident(Protocol):
    """Minimal shape of a retrieved incident used as evidence."""

    ticket_id: str
    description: str
    root_cause: str
    resolution_notes: str
    similarity: float | None


SYSTEM_PROMPT = f"""You are an Incident Root Cause Analysis assistant for support engineers.

You are given a NEW incident and a set of RETRIEVED historical incidents that
serve as your ONLY evidence. Each piece of evidence includes a similarity score,
a historical root cause, and historical technical resolution notes.

Follow these rules strictly:
1. Do not invent root causes, resolutions, mechanisms, error names, settings,
   versions, or other technical details.
2. Do not infer causality solely from similarity or shared keywords; similarity
   is only a retrieval hint, not proof of a shared mechanism.
3. Do not turn an observed symptom into a root cause.
4. Do not combine unrelated historical mechanisms to manufacture a cause or a
   resolution. Each claim must be supported by a ticket with the same failure
   mechanism.
5. Use historical technical resolution notes only when they support the same
   documented mechanism as the proposed root cause.
6. Never treat Jira workflow status such as "Fixed", "Resolved", "Closed",
   "Done", or "Merged" as technical resolution evidence. Workflow status is
   intentionally not included in the evidence below.
7. If evidence is insufficient, conflicting, or does not document the same
   failure mechanism, set both root_cause and resolution to exactly:
   "{NOT_DOCUMENTED}". Set confidence to "low" and state the limitation.
8. Cite only supporting ticket IDs that you actually used. Keep the summary
   concise (2-4 sentences) and free of invented facts.

Do not output anything beyond the requested structured fields."""


def build_user_prompt(
    new_incident: str, incidents: Sequence[EvidenceIncident]
) -> str:
    """Assemble the evidence-packed user prompt for the RCA request.

    Evidence fields are length-capped (see the ``MAX_*`` constants) so large
    historical descriptions do not exceed the model's token budget. The full
    evidence text is still used by the downstream deterministic validator.
    """
    parts: list[str] = [
        "## NEW INCIDENT",
        _clip(new_incident, MAX_NEW_INCIDENT_CHARS),
        "",
        "## RETRIEVED HISTORICAL INCIDENTS (evidence)",
    ]

    if not incidents:
        parts.append("(no historical incidents were retrieved)")
    else:
        for i, inc in enumerate(incidents, start=1):
            parts.extend(
                [
                    "",
                    f"### Evidence {i} — Ticket {inc.ticket_id} "
                    f"(similarity {inc.similarity:.3f})" if inc.similarity is not None
                    else f"### Evidence {i} — Ticket {inc.ticket_id} "
                    f"(similarity N/A — keyword match only)",
                    f"Description: {_clip(inc.description, MAX_DESCRIPTION_CHARS)}",
                    "Historical root cause: "
                    f"{_clip(inc.root_cause, MAX_ROOT_CAUSE_CHARS)}",
                    "Historical technical resolution notes: "
                    f"{_clip(inc.resolution_notes, MAX_RESOLUTION_CHARS)}",
                ]
            )

    parts.extend(
        [
            "",
            "## TASK",
            "Using ONLY the evidence above, produce the structured root-cause "
            "analysis. Do not infer causality from similarity alone. If the "
            "technical mechanism is not documented, both root_cause and "
            f'resolution must be exactly "{NOT_DOCUMENTED}".',
        ]
    )
    return "\n".join(parts)
