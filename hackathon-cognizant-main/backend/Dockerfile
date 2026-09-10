# Backend: FastAPI + Sentence-Transformers (MiniLM) + FAISS + Groq.
# The embedding model is baked in at build time so the container never needs to
# download it at runtime. The FAISS index is built on first start (entrypoint)
# into the mounted data volume, so it persists across restarts.
FROM python:3.12-slim

WORKDIR /app

# Runtime libs: libgomp1 is required by faiss-cpu (and torch's OpenMP).
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first (better layer caching).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Bake the embedding model into the image (no runtime HuggingFace download).
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')"

# Application code, scripts, the raw dataset, and the latest eval results.
COPY app ./app
COPY scripts ./scripts
COPY data/raw ./data/raw
COPY evaluation ./evaluation
COPY docker-entrypoint.sh ./docker-entrypoint.sh
RUN chmod +x ./docker-entrypoint.sh

# Pre-build the FAISS + BM25 index at image build time so the container starts
# instantly on Cloud Run (no embedding work at runtime).
RUN python -m scripts.preprocess && python -m scripts.build_index

EXPOSE 8080
ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
