"""CLI entrypoint for the preprocessing pipeline.

Pipeline:  raw CSV  ->  validate  ->  clean  ->  save processed CSV

Usage (from the backend/ directory):

    uv run python -m scripts.preprocess
    uv run python -m scripts.preprocess path/to/raw.csv path/to/out.csv

The raw CSV is only read, never modified. If validation fails, no output is
written and the process exits with a non-zero status.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from app.preprocessing.cleaner import clean_dataframe
from app.preprocessing.transformer import add_search_text
from app.preprocessing.validator import (
    DEFAULT_RAW_DATASET,
    format_report,
    validate_dataset,
)

# backend/scripts/preprocess.py -> parents[1] == backend/
_BACKEND_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROCESSED_PATH: Path = (
    _BACKEND_ROOT / "data" / "processed" / "incidents_clean.csv"
)


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    raw_path = Path(args[0]) if len(args) >= 1 else DEFAULT_RAW_DATASET
    out_path = Path(args[1]) if len(args) >= 2 else DEFAULT_PROCESSED_PATH

    # 1. Validate.
    report = validate_dataset(raw_path)
    if not report.is_valid:
        print(format_report(report))
        print("\nValidation failed; aborting without writing output.")
        return 1

    # 2. Read the raw CSV (read-only; strings preserved, blanks -> NaN).
    df = pd.read_csv(raw_path, dtype=str, keep_default_na=True)

    # 3. Clean.
    cleaned, stats = clean_dataframe(df)

    # 4. Build the retrieval representation (adds the `search_text` column).
    transformed = add_search_text(cleaned)

    # 5. Save the processed CSV (never touches the raw file).
    out_path.parent.mkdir(parents=True, exist_ok=True)
    transformed.to_csv(out_path, index=False, encoding="utf-8")

    # 6. Report.
    print("Preprocessing complete.")
    print(f"  input records:      {stats.input_records}")
    print(f"  output records:     {stats.output_records}")
    print(
        f"  duplicates removed: {stats.duplicates_removed}"
        f"  (full-row: {stats.duplicate_rows_removed}, "
        f"ticket-id: {stats.duplicate_ticket_ids_removed})"
    )
    print(f"  columns:            {', '.join(map(str, transformed.columns))}")
    print(f"  output path:        {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
