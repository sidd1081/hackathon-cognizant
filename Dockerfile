# Backend-only image for Hugging Face Spaces (Docker SDK).
# The frontend is deployed separately (e.g. Vercel) and points at this Space's
# URL via VITE_API_BASE_URL; set CORS_ORIGINS here to allow that domain.
#
# The MiniLM model and the FAISS index are baked in at build time so the Space
# starts instantly with no runtime downloads (Spaces storage is ephemeral).
# HF Spaces routes to port 7860 by default (see the Space README `app_port`).
#
# See DEPLOYMENT.md ("Hugging Face Spaces + Vercel") for the full steps.
FROM python:3.12-slim
WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Bake the embedding model (no runtime HuggingFace download).
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')"

COPY backend/app ./app
COPY backend/scripts ./scripts
COPY backend/data/raw ./data/raw
COPY backend/evaluation ./evaluation

# Bake the FAISS index so the Space boots instantly.
RUN python -m scripts.preprocess && python -m scripts.build_index

ENV PORT=7860
EXPOSE 7860
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-7860}"]
