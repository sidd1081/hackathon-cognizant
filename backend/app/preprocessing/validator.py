"""Dataset validation for the historical incidents CSV.

This module performs **read-only** validation. It never modifies the raw
dataset and never invents or fills in missing data — it only inspects and
reports on the file's structure and quality.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

# Canonical columns required to ingest historical incidents.  ``resolution``
# deliberately is not required: ``resolution_status`` is workflow state while
# ``resolution_notes`` contains the technical fix evidence used by the RAG
# pipeline.
REQUIRED_COLUMNS: tuple[str, ...] = (
    "ticket_id",
    "project",
    "summary",
    "description",
    "root_cause",
    "resolution_status",
    "resolution_notes",
)

# These fields add useful context when present but must not reject an otherwise
# canonical dataset when absent.
OPTIONAL_COLUMNS: tuple[str, ...] = (
    "components",
    "labels",
    "comments",
    "root_cause_source",
    "resolution_source",
    "evidence_quality",
    "search_text",
)

# backend/app/preprocessing/validator.py -> parents[2] == backend/
_BACKEND_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RAW_DATASET: Path = _BACKEND_ROOT / "data" / "raw" / "incidents.csv"


@dataclass
class ValidationReport:
    """Structured result of validating the incidents dataset.

    `errors` are blocking, structural problems (missing file, missing required
    columns, empty dataset). `warnings` are non-blocking data-quality issues
    (missing values, duplicate rows, duplicate ticket IDs).
    """

    file_path: str | Path
    file_exists: bool = False
    is_readable: bool = False
    present_columns: list[str] = field(default_factory=list)
    missing_columns: list[str] = field(default_factory=list)
    record_count: int = 0
    is_empty: bool = True
    missing_values_by_column: dict[str, int] = field(default_factory=dict)
    duplicate_row_count: int = 0
    duplicate_ticket_id_count: int = 0
    duplicate_ticket_ids: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        """True when there are no blocking (structural) errors."""
        return not self.errors


def _count_missing(series: pd.Series) -> int:
    """Count NaN/None plus empty or whitespace-only string values.

    Operates on copies via `fillna`/`astype`; the source column is untouched.
    """
    filled = series.fillna("").astype(str).str.strip()
    return int(filled.eq("").sum())


def validate_dataframe(
    df: pd.DataFrame, source: str | Path = "<dataframe>"
) -> ValidationReport:
    """Validate an already-loaded incidents DataFrame (read-only).

    Shared by the CLI (via :func:`validate_dataset`) and the upload endpoint so
    the checks live in exactly one place.
    """
    report = ValidationReport(
        file_path=source, file_exists=True, is_readable=True
    )
    report.present_columns = list(df.columns)

    # 1. Required columns must all be present.
    report.missing_columns = [
        col for col in REQUIRED_COLUMNS if col not in df.columns
    ]
    if report.missing_columns:
        report.errors.append(
            "Missing required column(s): " + ", ".join(report.missing_columns)
        )

    # 2. Dataset must not be empty.
    report.record_count = int(len(df))
    report.is_empty = report.record_count == 0
    if report.is_empty:
        report.errors.append("Dataset has 0 records.")

    # 3. Missing values per required column (only those actually present).
    for col in REQUIRED_COLUMNS:
        if col in df.columns:
            missing = _count_missing(df[col])
            report.missing_values_by_column[col] = missing
            if missing:
                report.warnings.append(
                    f"{missing} missing value(s) in column '{col}'."
                )

    # 4. Fully duplicated rows.
    report.duplicate_row_count = int(df.duplicated().sum())
    if report.duplicate_row_count:
        report.warnings.append(
            f"{report.duplicate_row_count} duplicate row(s) found."
        )

    # 5. Duplicate ticket IDs (requires the ticket_id column).
    if "ticket_id" in df.columns:
        ticket_ids = df["ticket_id"]
        report.duplicate_ticket_id_count = int(ticket_ids.duplicated().sum())
        if report.duplicate_ticket_id_count:
            dup_values = (
                ticket_ids[ticket_ids.duplicated(keep=False)]
                .dropna()
                .unique()
                .tolist()
            )
            report.duplicate_ticket_ids = sorted(map(str, dup_values))
            report.warnings.append(
                f"{report.duplicate_ticket_id_count} duplicate ticket ID(s) "
                f"across {len(report.duplicate_ticket_ids)} distinct ID(s)."
            )

    return report


def validate_dataset(path: str | Path = DEFAULT_RAW_DATASET) -> ValidationReport:
    """Validate the incidents CSV at `path` and return a report.

    The raw file is only read, never written to.
    """
    path = Path(path)
    report = ValidationReport(file_path=path)

    # File must exist.
    if not path.is_file():
        report.errors.append(f"File not found: {path}")
        return report
    report.file_exists = True

    # Read the CSV (all columns as strings; blank cells become NaN).
    try:
        df = pd.read_csv(path, dtype=str, keep_default_na=True)
    except pd.errors.EmptyDataError:
        report.is_readable = True
        report.is_empty = True
        report.errors.append("Dataset is empty (no header or rows).")
        return report
    except Exception as exc:  # noqa: BLE001 - report any parse failure clearly
        report.errors.append(f"Failed to read CSV: {exc}")
        return report

    return validate_dataframe(df, source=path)


def format_report(report: ValidationReport) -> str:
    """Render a `ValidationReport` as a human-readable text block."""
    line = "=" * 60
    sub = "-" * 60
    out: list[str] = [line, " DATASET VALIDATION REPORT", line]

    out.append(f"File:      {report.file_path}")
    out.append(f"Exists:    {'yes' if report.file_exists else 'no'}")
    out.append(f"Readable:  {'yes' if report.is_readable else 'no'}")
    out.append(f"Records:   {report.record_count}")
    out.append("")

    out.append("Required columns: " + ", ".join(REQUIRED_COLUMNS))
    if report.present_columns:
        out.append("Present columns:  " + ", ".join(report.present_columns))
    out.append(
        "Missing columns:  "
        + (", ".join(report.missing_columns) if report.missing_columns else "none")
    )
    out.append("")

    out.append("Missing values by column:")
    if report.missing_values_by_column:
        width = max(len(c) for c in report.missing_values_by_column)
        for col, count in report.missing_values_by_column.items():
            out.append(f"  {col.ljust(width)} : {count}")
    else:
        out.append("  (no required columns available to check)")
    out.append("")

    out.append(f"Duplicate rows:       {report.duplicate_row_count}")
    out.append(f"Duplicate ticket IDs: {report.duplicate_ticket_id_count}")
    if report.duplicate_ticket_ids:
        preview = ", ".join(report.duplicate_ticket_ids[:10])
        more = (
            f" (+{len(report.duplicate_ticket_ids) - 10} more)"
            if len(report.duplicate_ticket_ids) > 10
            else ""
        )
        out.append(f"  duplicated IDs: {preview}{more}")
    out.append("")

    out.append(sub)
    result = "PASS" if report.is_valid else "FAIL"
    detail = "no blocking errors" if report.is_valid else "blocking errors present"
    out.append(f" RESULT: {result}  ({detail})")

    if report.errors:
        out.append(f" Errors: {len(report.errors)}")
        out.extend(f"   - {e}" for e in report.errors)
    if report.warnings:
        out.append(f" Warnings: {len(report.warnings)}")
        out.extend(f"   - {w}" for w in report.warnings)
    if not report.errors and not report.warnings:
        out.append(" No issues detected.")

    out.append(line)
    return "\n".join(out)
