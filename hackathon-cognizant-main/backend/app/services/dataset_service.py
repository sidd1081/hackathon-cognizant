"""Service layer for the dataset upload -> index pipeline.

Runs the full workflow on an uploaded CSV's bytes:

    parse -> validate -> clean -> search_text -> embeddings -> FAISS -> save

It reuses the existing preprocessing and RAG components (no duplicated logic)
and NEVER touches the original raw dataset (``data/raw/incidents.csv``). Only
derived artifacts are written: the processed CSV and the vector store. Typed
exceptions let the route map failures to HTTP status codes without leaking
internal details.
"""

from __future__ import annotations

import io
from pathlib import Path

import pandas as pd

from app.core.logger import get_logger
from app.models.schemas import DatasetUploadResponse
from app.preprocessing.cleaner import clean_dataframe
from app.preprocessing.transformer import SEARCH_TEXT_COLUMN, add_search_text
from app.preprocessing.validator import validate_dataframe
from app.rag.embeddings import embed_texts
from app.rag.retriever import set_vector_store
from app.rag.vector_store import METADATA_FIELDS, VectorStore

logger = get_logger(__name__)

# backend/app/services/dataset_service.py -> parents[2] == backend/
_BACKEND_ROOT = Path(__file__).resolve().parents[2]
# Derived output only; the raw source dataset is never written here.
DEFAULT_PROCESSED_PATH: Path = (
    _BACKEND_ROOT / "data" / "processed" / "incidents_clean.csv"
)


class InvalidCSVError(ValueError):
    """The uploaded file could not be parsed as a CSV (client error, 400)."""


class DatasetValidationError(ValueError):
    """The dataset failed content validation (client error, 422)."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("; ".join(errors))


class IndexingError(RuntimeError):
    """Embedding/index building failed (server error, 500 — details hidden)."""


def _parse_csv(contents: bytes) -> pd.DataFrame:
    """Parse uploaded bytes into a DataFrame, raising InvalidCSVError on failure."""
    if not contents or not contents.strip():
        raise InvalidCSVError("Uploaded file is empty.")
    try:
        return pd.read_csv(io.BytesIO(contents), dtype=str, keep_default_na=True)
    except pd.errors.EmptyDataError as exc:
        raise InvalidCSVError("Uploaded file has no header or rows.") from exc
    except pd.errors.ParserError as exc:
        raise InvalidCSVError(f"Malformed CSV: {exc}") from exc
    except UnicodeDecodeError as exc:
        raise InvalidCSVError("File is not valid UTF-8 CSV text.") from exc


def process_upload(contents: bytes) -> DatasetUploadResponse:
    """Run the upload-to-index pipeline and return a status response.

    Raises:
        InvalidCSVError: unparseable/empty upload.
        DatasetValidationError: missing columns / empty dataset.
        IndexingError: embedding or index build failed.
    """
    # 1. Parse.
    df = _parse_csv(contents)

    # 2. Validate (reuses the shared DataFrame validator).
    report = validate_dataframe(df, source="uploaded CSV")
    if not report.is_valid:
        raise DatasetValidationError(report.errors)

    # 3. Clean + 4. search_text.
    cleaned, stats = clean_dataframe(df)
    if cleaned.empty:
        raise DatasetValidationError(["Dataset is empty after cleaning."])
    transformed = add_search_text(cleaned)

    # 5-7. Persist processed CSV, embed, build & save FAISS + metadata.
    try:
        DEFAULT_PROCESSED_PATH.parent.mkdir(parents=True, exist_ok=True)
        transformed.to_csv(DEFAULT_PROCESSED_PATH, index=False, encoding="utf-8")

        texts = transformed[SEARCH_TEXT_COLUMN].fillna("").astype(str).tolist()
        embeddings = embed_texts(texts)
        metadata = (
            transformed[list(METADATA_FIELDS)]
            .fillna("")
            .astype(str)
            .to_dict(orient="records")
        )
        store = VectorStore.build(embeddings, metadata)
        store.save()
        set_vector_store(store)  # refresh retriever cache for immediate use
    except Exception as exc:  # noqa: BLE001 - hide internals from the client
        logger.exception("Indexing failed during upload")
        raise IndexingError("Failed to build the search index.") from exc

    logger.info(
        "Upload indexed: %d record(s), %d duplicate(s) removed, dim=%d",
        store.size,
        stats.duplicates_removed,
        store.dimension,
    )
    return DatasetUploadResponse(
        status="success",
        message="Dataset processed and indexed successfully.",
        records=store.size,
        duplicates_removed=stats.duplicates_removed,
        embedding_dimension=store.dimension,
        index_status="ready",
    )
