"""Dataset cleaning for the historical incidents CSV.

Cleaning is **non-destructive to meaning**: it normalizes whitespace and strips
obvious Jira wiki formatting, but never invents data and always preserves the
exact sentinel ``Not explicitly documented.``. Technical content (identifiers,
code, file paths, URLs) is deliberately preserved.

Design notes on Jira markup:
    * ``{{x}}`` is Jira *monospace* and almost always wraps a technical token
      (e.g. ``{{max.poll.interval.ms}}``), so it is UNWRAPPED to its inner text.
    * Only a WHITELIST of real Jira macros (``{code}``, ``{noformat}``,
      ``{quote}``, ``{color}`` ...) is removed. Arbitrary ``{...}`` is left
      alone so JSON/code such as ``{"key": "value"}`` survives intact.
    * User mentions ``[~username]`` are attribution noise for RCA similarity and
      are removed entirely (the username carries no technical signal).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import pandas as pd

# Exact sentinel that must survive cleaning verbatim.
NOT_DOCUMENTED = "Not explicitly documented."

# Free-text columns that receive full Jira cleaning.  ``resolution_status`` is
# intentionally excluded because it is Jira workflow state, not technical
# evidence.  ``resolution_notes`` is the canonical technical-resolution field.
TEXT_COLUMNS: tuple[str, ...] = (
    "summary",
    "description",
    "components",
    "labels",
    "comments",
    "root_cause",
    "resolution_notes",
)

# --- Whitespace normalization -------------------------------------------------
# Various Unicode spaces (incl. non-breaking space U+00A0) -> a regular space.
_UNICODE_SPACE_CODEPOINTS = (
    0x00A0,  # no-break space
    0x1680,  # ogham space mark
    0x2000, 0x2001, 0x2002, 0x2003, 0x2004, 0x2005, 0x2006, 0x2007,
    0x2008, 0x2009, 0x200A,  # en quad .. hair space
    0x202F,  # narrow no-break space
    0x205F,  # medium mathematical space
    0x3000,  # ideographic space
)
_UNICODE_SPACE_MAP = {cp: " " for cp in _UNICODE_SPACE_CODEPOINTS}
# Zero-width / BOM characters -> removed entirely.
# U+200B ZWSP, U+200C ZWNJ, U+200D ZWJ, U+2060 word-joiner, U+FEFF BOM.
_ZERO_WIDTH = re.compile("[​‌‍⁠﻿]")
_REPEATED_WHITESPACE = re.compile(r"\s+")

# --- Jira wiki markup ---------------------------------------------------------
_USER_MENTION = re.compile(r"\[~[^\]]+\]")
# Jira monospace uses ``{{ }}`` delimiters. Remove the delimiter tokens directly
# (rather than pair-matching) so nested/adjacent/unbalanced cases such as
# ``{{{{state.dir}}}}`` or ``...)}}  {{Apr 7...`` fully unwrap. Single-brace
# code/JSON like ``{"k": 1}`` is untouched.
_MONOSPACE_TOKENS = re.compile(r"\{\{|\}\}")
# Whitelisted block/inline macros, with optional ``:params`` (e.g. code:java).
_JIRA_MACRO = re.compile(
    r"\{(?:code|noformat|quote|color|panel|anchor|expand|section|align|cite"
    r"|sub|sup)(?::[^}]*)?\}",
    re.IGNORECASE,
)
# Dangling/unclosed macro opener (malformed source), e.g. a description that
# ends with ``{code:java`` and never closes. Only matched at end-of-string or
# before whitespace so it cannot bite into inline content.
_JIRA_MACRO_DANGLING = re.compile(
    r"\{(?:code|noformat|quote|color|panel|anchor|expand|section|align|cite"
    r"|sub|sup)(?::[^}\s]*)?(?=\s|$)",
    re.IGNORECASE,
)
# Labeled link ``[text|target]`` -> keep the human-readable ``text``.
_LABELED_LINK = re.compile(r"\[([^\]|]+)\|[^\]]*\]")
# Bare bracketed URL ``[https://...]`` -> keep the URL, drop the brackets.
_BARE_URL_LINK = re.compile(r"\[((?:https?|ftp)://[^\]\s|]+)\]")
# Line/segment headings ``h1.``..``h6.`` and blockquote ``bq.`` markers.
_HEADING = re.compile(r"(?<!\S)h[1-6]\.\s+")
_BLOCKQUOTE = re.compile(r"(?<!\S)bq\.\s+")


@dataclass
class CleaningStats:
    """Summary of what the cleaning step did."""

    input_records: int
    output_records: int
    duplicate_rows_removed: int
    duplicate_ticket_ids_removed: int

    @property
    def duplicates_removed(self) -> int:
        """Total rows dropped as duplicates (full-row + duplicate ticket ID)."""
        return self.duplicate_rows_removed + self.duplicate_ticket_ids_removed


def _normalize_whitespace(text: str) -> str:
    """Normalize Unicode/non-breaking spaces, collapse runs, and strip ends."""
    text = text.translate(_UNICODE_SPACE_MAP)
    text = _ZERO_WIDTH.sub("", text)
    text = _REPEATED_WHITESPACE.sub(" ", text)
    return text.strip()


def _is_missing(value: object) -> bool:
    """Return whether a scalar dataframe value is missing.

    CSV values are scalar, but this defensive check also avoids ambiguous
    truth-value errors if a caller provides a list-like object.
    """
    if value is None:
        return True
    if not pd.api.types.is_scalar(value):
        return False
    return bool(pd.isna(value))


def clean_text(value: object) -> object:
    """Clean a free-text field.

    Missing values are returned unchanged (never turned into ``"nan"`` — that
    would invent data). The sentinel ``Not explicitly documented.`` is returned
    verbatim.
    """
    if _is_missing(value):
        return value

    text = str(value)
    if text.strip() == NOT_DOCUMENTED:
        return NOT_DOCUMENTED

    # Jira markup (order matters: mentions, then unwrap monospace delimiters,
    # then single-brace macros).
    text = _USER_MENTION.sub("", text)
    text = _MONOSPACE_TOKENS.sub("", text)
    text = _JIRA_MACRO.sub("", text)
    text = _JIRA_MACRO_DANGLING.sub("", text)
    text = _LABELED_LINK.sub(r"\1", text)
    text = _BARE_URL_LINK.sub(r"\1", text)
    text = _HEADING.sub("", text)
    text = _BLOCKQUOTE.sub("", text)

    return _normalize_whitespace(text)


def clean_ticket_id(value: object) -> object:
    """Clean a ticket ID: whitespace normalization only (never alters the ID)."""
    if _is_missing(value):
        return value
    return _normalize_whitespace(str(value))


def clean_dataframe(df: pd.DataFrame) -> tuple[pd.DataFrame, CleaningStats]:
    """Return a cleaned copy of ``df`` plus cleaning statistics.

    Steps:
        1. Drop exact duplicate rows (keep first).
        2. Drop rows with a duplicate ``ticket_id`` (keep first).
        3. Clean ``ticket_id`` and the free-text columns.

    The input frame is never mutated in place.
    """
    input_records = len(df)

    # 1. Exact full-row duplicates.
    deduped_rows = df.drop_duplicates(keep="first")
    after_row_dedupe = len(deduped_rows)

    # 2. Duplicate ticket IDs (first occurrence preserved).
    if "ticket_id" in deduped_rows.columns:
        deduped = deduped_rows.drop_duplicates(subset=["ticket_id"], keep="first")
    else:
        deduped = deduped_rows
    after_id_dedupe = len(deduped)

    # 3. Field cleaning on a fresh copy.
    cleaned = deduped.copy()
    if "ticket_id" in cleaned.columns:
        cleaned["ticket_id"] = cleaned["ticket_id"].map(clean_ticket_id)
    for col in TEXT_COLUMNS:
        if col in cleaned.columns:
            cleaned[col] = cleaned[col].map(clean_text)
    cleaned = cleaned.reset_index(drop=True)

    stats = CleaningStats(
        input_records=input_records,
        output_records=after_id_dedupe,
        duplicate_rows_removed=input_records - after_row_dedupe,
        duplicate_ticket_ids_removed=after_row_dedupe - after_id_dedupe,
    )
    return cleaned, stats
