#!/bin/sh
# Build the FAISS index on first start if it isn't present yet (e.g. a fresh
# data volume). The embedding model is already baked into the image, so this is
# just preprocessing + local embedding — no network required. Subsequent starts
# reuse the persisted index.
set -e

if [ ! -f /app/data/vectorstore/index.faiss ]; then
  echo "[entrypoint] No FAISS index found — building it (one-time)…"
  python -m scripts.preprocess
  python -m scripts.build_index
  echo "[entrypoint] Index build complete."
else
  echo "[entrypoint] Existing FAISS index found — skipping build."
fi

exec "$@"
