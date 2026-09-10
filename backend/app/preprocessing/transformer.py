"""Build the retrieval representation (``search_text``) for each incident.

``search_text`` is the text that gets embedded in the FAISS vector store. It
contains the incident's project, summary, and description. Root cause,
technical resolution notes, and workflow status are deliberately excluded from
the embedding so that answer evidence and Jira workflow state do not pollute
the vector space. This produces tighter, more focused semantic similarity.

Root cause and resolution notes remain in the DataFrame as metadata columns and
are returned after retrieval for use as evidence.

Layout (exact):

    Project: <project>
    Summary: <summary>
    Description: <description>
"""

from __future__ import annotations

import pandas as pd

from app.preprocessing.validator import REQUIRED_COLUMNS

SEARCH_TEXT_COLUMN = "search_text"

SEARCH_TEXT_TEMPLATE = (
    "Project: {project}\n"
    "Summary: {summary}\n"
    "Description: {description}"
)

# Datasets produced by the previous preprocessing implementation used this
# equivalent, answer-free layout. Preserve it when it can be verified against
# the incident fields instead of needlessly replacing user-provided text.
_LEGACY_SAFE_SEARCH_TEXT_TEMPLATE = (
    "Project: {project}\n"
    "Summary: {summary}\n"
    "Incident Description: {description}"
)


def _as_text(value: object) -> str:
    """Render a cell for inclusion in ``search_text``.

    Missing values map to an empty string so we never emit the literal
    ``"nan"`` and never invent content — the corresponding line is simply left
    blank.
    """
    if value is None or (
        pd.api.types.is_scalar(value) and bool(pd.isna(value))
    ):
        return ""
    return str(value)


def build_search_text(
    project: object, summary: object, description: object
) -> str:
    """Assemble the ``search_text`` block for a single incident.

    Only project, summary, and description are embedded. Root cause,
    ``resolution_notes``, and ``resolution_status`` remain metadata and are
    not part of the vector representation.
    """
    return SEARCH_TEXT_TEMPLATE.format(
        project=_as_text(project),
        summary=_as_text(summary),
        description=_as_text(description),
    )


def _is_valid_existing_search_text(
    value: object, project: object, summary: object, description: object
) -> bool:
    """Return whether ``value`` is a verified answer-free search representation.

    A non-empty arbitrary value is not enough to trust: it must exactly match
    either the canonical template or the prior safe template, both built only
    from the allowed retrieval fields.
    """
    text = _as_text(value)
    if not text:
        return False

    fields = {
        "project": _as_text(project),
        "summary": _as_text(summary),
        "description": _as_text(description),
    }
    return text in {
        SEARCH_TEXT_TEMPLATE.format(**fields),
        _LEGACY_SAFE_SEARCH_TEXT_TEMPLATE.format(**fields),
    }


def add_search_text(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of ``df`` with a ``search_text`` column appended.

    Original columns are not modified. A supplied ``search_text`` is preserved
    only when it can be verified as an answer-free representation built from
    project, summary, and description; otherwise the canonical text is built.
    The returned frame's columns are ordered as the canonical required fields,
    then ``search_text``; optional and unexpected columns are preserved after
    them.
    """
    result = df.copy()
    existing = (
        result[SEARCH_TEXT_COLUMN]
        if SEARCH_TEXT_COLUMN in result.columns
        else pd.Series([None] * len(result), index=result.index)
    )
    result[SEARCH_TEXT_COLUMN] = [
        existing_text
        if _is_valid_existing_search_text(
            existing_text, project, summary, description
        )
        else build_search_text(project, summary, description)
        for existing_text, project, summary, description in zip(
            existing,
            result["project"],
            result["summary"],
            result["description"],
        )
    ]

    ordered = [*REQUIRED_COLUMNS, SEARCH_TEXT_COLUMN]
    extras = [col for col in result.columns if col not in ordered]
    return result[ordered + extras]
