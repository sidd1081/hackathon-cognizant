"""validate node: deterministic post-checks on the LLM output.

No LLM. Enforces grounding through multiple checks:

1. **Citation check** — drops any cited ticket ID not in the retrieved evidence.
2. **Mechanism check** — extracts technical terms from the generated root_cause
   and verifies they appear in cited evidence descriptions, root causes, or
   technical resolution notes. Jira workflow status is never technical evidence.
   This catches cases where the LLM introduces technical claims not supported by
   the evidence (e.g., blaming "ConcurrentModificationException" when no cited
   evidence mentions that exception).
3. **Confidence adjustment** — downgrades confidence to "low" when issues are
   found, and replaces root_cause/resolution with the sentinel when mechanism
   validation fails entirely.
"""

from __future__ import annotations

import re

from app.agent.state import RCAState
from app.core.logger import get_logger
from app.models.schemas import NOT_DOCUMENTED

logger = get_logger(__name__)

# Technical term extraction patterns (same approach as evidence_check).
_TECH_PATTERNS = (
    re.compile(r"\b\w+(?:\.\w+)+\b"),           # dotted identifiers
    re.compile(r"\b\w*_\w+\b"),                  # snake_case
    re.compile(r"\b[A-Za-z]*[a-z][A-Z]\w*\b"),   # camelCase/PascalCase
    re.compile(r"\b[A-Z]{2,}\b"),                # ALL-CAPS acronyms
)

# Generic terms that should not be penalized as "unsupported technical terms".
_GENERIC_TERMS = frozenset({
    "kafka", "apache", "java", "jvm",
    "http", "rest", "api", "tcp", "ssl", "tls",
    "cpu", "ram", "disk", "io",
})

# Abbreviation equivalences: maps a lowered term to its known equivalents.
# If the LLM says "NullPointerException" but the evidence says "NPE", they
# should be treated as the same technical term.
_ABBREVIATION_EQUIVALENCES: dict[str, set[str]] = {
    "nullpointerexception": {"npe"},
    "npe": {"nullpointerexception"},
    "outofmemoryerror": {"oom", "outofmemory"},
    "oom": {"outofmemoryerror", "outofmemory"},
    "concurrentmodificationexception": {"cme"},
    "cme": {"concurrentmodificationexception"},
    "classnotfoundexception": {"cnfe"},
    "cnfe": {"classnotfoundexception"},
    "illegalstateexception": {"ise"},
    "ise": {"illegalstateexception"},
    "interbrokersendsthread": {"ibst"},
    "replicafetcherthread": {"rft"},
}

# Regex to split camelCase into component words.
_CAMEL_SPLIT = re.compile(r"(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")

_WORD = re.compile(r"[A-Za-z0-9]+")


def _extract_technical(text: str) -> set[str]:
    """Extract lowercased technical terms from text."""
    terms: set[str] = set()
    for pattern in _TECH_PATTERNS:
        for match in pattern.findall(text):
            if len(match) > 1:
                terms.add(match.lower())
    return terms


def _extract_words(text: str) -> set[str]:
    """Extract lowercased words from text."""
    return {m.lower() for m in _WORD.findall(text) if len(m) > 2}


def _camel_components(term: str) -> set[str]:
    """Split a camelCase term into lowercase component words.

    E.g. "nullpointerexception" doesn't split (already lowercase), but
    "NullPointerException" -> {"null", "pointer", "exception"}.
    We work on the original mixed-case form if available.
    """
    parts = _CAMEL_SPLIT.split(term)
    if len(parts) > 1:
        return {p.lower() for p in parts if len(p) > 2}
    return set()


def _has_equivalent(term: str, reference_terms: set[str],
                    reference_words: set[str]) -> bool:
    """Check if a term has an equivalent in the reference sets.

    Checks: direct match, abbreviation equivalence, and camelCase component
    word overlap (all component words must appear in reference_words).
    """
    # Direct match.
    if term in reference_terms or term in reference_words:
        return True

    # Abbreviation equivalence.
    equivalents = _ABBREVIATION_EQUIVALENCES.get(term, set())
    if equivalents & (reference_terms | reference_words):
        return True

    # CamelCase component words: if ALL components appear in reference, it's
    # a match. E.g. "nullpointerexception" matches if "null", "pointer",
    # "exception" all appear in the evidence text.
    components = _camel_components(term)
    if components and components.issubset(reference_words):
        return True

    return False


def validate_node(state: RCAState) -> dict:
    rca = state["rca"]
    evidence = state.get("evidence", [])
    valid_ids = {item.ticket_id for item in evidence}

    cited = list(rca.supporting_ticket_ids)
    removed = [ticket for ticket in cited if ticket not in valid_ids]
    issues: list[str] = []

    root_documented = bool(rca.root_cause.strip()) and rca.root_cause != NOT_DOCUMENTED

    if not root_documented:
        # No established root cause => nothing genuinely supports one.
        if cited:
            issues.append(
                "Cleared supporting citations because the root cause is not "
                "documented."
            )
        kept: list[str] = []
    else:
        # Keep only citations that actually appear in the retrieved evidence.
        kept = [ticket for ticket in cited if ticket in valid_ids]
        if removed:
            issues.append(
                f"Dropped {len(removed)} cited ticket ID(s) not present in the "
                f"evidence: {removed}"
            )
        if not kept:
            issues.append(
                "A concrete root cause was asserted without citing any evidence."
            )

    rca.supporting_ticket_ids = kept

    # --- Mechanism-match validation -------------------------------------------
    # If the LLM claimed a root cause and cited evidence, check that the
    # technical terms in the root cause actually appear in the cited evidence
    # descriptions, root causes, or technical resolution notes. This catches
    # cases where the LLM hallucinates technical details not present in any
    # cited ticket. ``resolution_status`` is deliberately excluded: "Fixed"
    # is workflow state, not technical evidence.
    mechanism_valid = True
    if root_documented and kept:
        # Extract technical terms from the generated root cause.
        rc_technical = _extract_technical(rca.root_cause) - _GENERIC_TERMS

        if rc_technical:
            # Collect technical terms from every historical evidence field that
            # documents a mechanism or technical fix. Jira workflow status is
            # intentionally not part of the evidence corpus.
            cited_items = [item for item in evidence if item.ticket_id in set(kept)]
            cited_technical: set[str] = set()
            cited_words: set[str] = set()
            for item in cited_items:
                for evidence_text in (
                    item.description,
                    item.root_cause,
                    item.resolution_notes,
                ):
                    cited_technical.update(_extract_technical(evidence_text))
                    cited_words.update(_extract_words(evidence_text))

            unsupported = rc_technical - cited_technical - _GENERIC_TERMS
            # Check each unsupported term for abbreviation equivalences and
            # camelCase component word matches before flagging it.
            truly_unsupported = {
                term for term in unsupported
                if not _has_equivalent(term, cited_technical, cited_words)
            }

            if truly_unsupported:
                fraction = len(truly_unsupported) / len(rc_technical)
                if fraction > 0.5:
                    # More than half of the root cause's technical terms are
                    # unsupported — the mechanism doesn't match.
                    mechanism_valid = False
                    issues.append(
                        f"Mechanism mismatch: {len(truly_unsupported)} of "
                        f"{len(rc_technical)} technical term(s) in the root "
                        f"cause are not found in any cited evidence: "
                        f"{sorted(truly_unsupported)}"
                    )
                elif truly_unsupported:
                    # Some unsupported terms, but less than half — flag as
                    # a warning and downgrade confidence.
                    issues.append(
                        f"Partially unsupported root cause: "
                        f"{sorted(truly_unsupported)} not found in cited evidence."
                    )

    # --- Apply corrections based on validation --------------------------------
    if not mechanism_valid:
        # Mechanism check failed: the root cause is not grounded in evidence.
        rca.root_cause = NOT_DOCUMENTED
        rca.resolution = NOT_DOCUMENTED
        rca.supporting_ticket_ids = []
        rca.confidence = "low"
        rca.summary = (
            "The retrieved historical evidence was insufficient to establish "
            "a documented technical root cause. The failure mechanism in the "
            "evidence does not match the reported incident."
        )
        kept = []
        issues.append(
            "Replaced root cause with sentinel due to mechanism mismatch."
        )
    elif issues and root_documented:
        # Some issues found but mechanism check passed — downgrade confidence.
        if rca.confidence == "high":
            rca.confidence = "medium"
            issues.append("Downgraded confidence from high to medium due to issues.")
        elif rca.confidence == "medium" and len(issues) > 1:
            rca.confidence = "low"
            issues.append("Downgraded confidence from medium to low due to multiple issues.")

    validation = {
        "citations_checked": True,
        "removed_citations": removed,
        "root_cause_documented": root_documented and mechanism_valid,
        "mechanism_valid": mechanism_valid,
        "issues": issues,
    }
    logger.info(
        "validate: %d issue(s), citations kept=%d, mechanism_valid=%s",
        len(issues), len(kept), mechanism_valid,
    )
    return {"rca": rca, "validation": validation, "status": "generated"}
