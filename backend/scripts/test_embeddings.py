"""Smoke test for the embedding layer.

Usage (from the backend/ directory):

    uv run python -m scripts.test_embeddings

Checks: embedding count, embedding dimension, and L2 normalization.
Exit code is 0 on success, 1 on failure.
"""

from __future__ import annotations

import numpy as np

from app.core.config import settings
from app.rag.embeddings import embed_texts, embedding_dimension

SAMPLE_TEXTS: list[str] = [
    "Restarting a Kafka connector returns an empty body and causes a NullPointerException.",
    "Consumer group offset reset misinterprets microseconds passed to --to-datetime.",
    "ZooKeeper TLS system tests fail after a ConfigCommand change.",
]


def main() -> int:
    print(f"Embedding model: {settings.embedding_model}")
    print(f"Sample texts:    {len(SAMPLE_TEXTS)}")

    embeddings = embed_texts(SAMPLE_TEXTS)
    dim = embedding_dimension()
    norms = np.linalg.norm(embeddings, axis=1)

    print(f"embeddings shape:     {embeddings.shape}")
    print(f"number of embeddings: {embeddings.shape[0]}")
    print(f"embedding dimension:  {embeddings.shape[1]}")
    print(f"dtype:                {embeddings.dtype}")
    print(f"per-vector L2 norms:  {np.round(norms, 6).tolist()}")

    checks: list[tuple[str, bool]] = [
        ("count == 3", embeddings.shape[0] == len(SAMPLE_TEXTS)),
        (f"dimension == {dim}", embeddings.shape[1] == dim),
        ("dtype float32", embeddings.dtype == np.float32),
        ("L2-normalized (norm ~= 1.0)", bool(np.allclose(norms, 1.0, atol=1e-4))),
    ]

    print("\nChecks:")
    all_ok = True
    for label, ok in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {label}")
        all_ok = all_ok and ok

    print("\nRESULT:", "PASS" if all_ok else "FAIL")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
