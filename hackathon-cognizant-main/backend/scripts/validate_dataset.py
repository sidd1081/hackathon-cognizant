"""CLI entrypoint for validating the historical incidents dataset.

Usage (from the backend/ directory):

    uv run python -m scripts.validate_dataset
    uv run python -m scripts.validate_dataset path/to/other.csv

Exit code is 0 when the dataset passes (no blocking errors), 1 otherwise.
"""

from __future__ import annotations

import sys
from pathlib import Path

from app.preprocessing.validator import (
    DEFAULT_RAW_DATASET,
    format_report,
    validate_dataset,
)


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    path = Path(args[0]) if args else DEFAULT_RAW_DATASET

    report = validate_dataset(path)
    print(format_report(report))
    return 0 if report.is_valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
