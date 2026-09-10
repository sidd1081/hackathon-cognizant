# Incident RCA Assistant — Backend

AI-Powered Incident Root Cause Analysis & Resolution Assistant — FastAPI service.

A RAG pipeline (Sentence Transformers + FAISS + LangChain) orchestrated by a
LangGraph workflow, with the LLM served by Groq. All deterministic steps
(retrieval, reranking, the evidence gate, and post-generation validation) live
outside the LLM so answers stay grounded in retrieved evidence.

## Requirements

- [uv](https://docs.astral.sh/uv/) (Python package/venv manager)
- Python 3.11 or 3.12 (pinned to 3.12; uv fetches it automatically)
- A Groq API key (for RCA generation) — https://console.groq.com

## Setup & run

From the `backend/` directory:

```bash
# 1. Create the virtual environment and install dependencies
uv sync

# 2. Configure the Groq API key
cp .env.example .env          # Windows: Copy-Item .env.example .env
#   then set GROQ_API_KEY=... in .env

# 3. Build the search index from the dataset
uv run python -m scripts.validate_dataset   # sanity-check data/raw/incidents.csv
uv run python -m scripts.preprocess         # -> data/processed/incidents_clean.csv
uv run python -m scripts.build_index        # -> data/vectorstore/ (FAISS + metadata)

# 4. Run the API (auto-reload for development)
uv run uvicorn app.main:app --reload --port 8000
```

The server listens on `http://127.0.0.1:8000`. Interactive docs at `/docs`.

## Verify

```bash
curl http://127.0.0.1:8000/api/health
# { "status": "ok" }

curl -X POST http://127.0.0.1:8000/api/incidents/analyze \
  -H "Content-Type: application/json" \
  -d '{"description":"A Kafka Streams app leaks resources because KeyValueIterator objects from state store queries are never closed."}'
```

## API

| Method | Endpoint | Auth | Purpose |
|---|---|---|---|
| `GET` | `/api/health` | — | Liveness probe |
| `POST` | `/api/auth/signup` | — | Create an account → `{ access_token, user }` |
| `POST` | `/api/auth/login` | — | Sign in → `{ access_token, user }` |
| `GET` | `/api/auth/me` | Bearer | Current authenticated user |
| `POST` | `/api/incidents/analyze` | Bearer | `{ "description": "..." }` → RCA + similar incidents |
| `POST` | `/api/dataset/upload` | Bearer | multipart CSV → validate, clean, embed, re-index |
| `GET` | `/api/evaluation` | — | Latest offline benchmark metrics |

Auth uses JWT bearer tokens (HS256); passwords are hashed with PBKDF2-HMAC-SHA256
(stdlib). Users are stored via SQLAlchemy — **PostgreSQL** when `DATABASE_URL` is
set (production/compose), otherwise a local SQLite file (`data/auth.db`, dev).
Protected routes require an `Authorization: Bearer <token>` header.

The public API exposes the technical resolution as `resolution` (mapped from the
dataset's `resolution_notes`). Jira `resolution_status` is never exposed as a
technical fix.

## Configuration

Settings live in `app/core/config.py` (Pydantic Settings), overridable via env
vars or `.env`:

- `GROQ_API_KEY` (required for RCA) — never committed
- `GROQ_MODEL` (default `openai/gpt-oss-120b`)
- `LLM_TEMPERATURE` (default `0.0`)
- `GROQ_MAX_RETRIES` (default `6`) — rides out free-tier 429 rate limits
- `EMBEDDING_MODEL` (default `sentence-transformers/all-MiniLM-L6-v2`)
- `JWT_SECRET` (**override in production**), `JWT_EXPIRE_MINUTES` (default `720`)
- `DATABASE_URL` (Postgres, e.g. `postgresql://user:pass@host:5432/db`; unset → SQLite)
- `LOG_LEVEL`, `CORS_ORIGINS`

## Scripts

Run from `backend/` as modules (e.g. `uv run python -m scripts.preprocess`):

- `validate_dataset` — read-only schema/quality check on the raw CSV
- `preprocess` — validate → clean → build `search_text` → write processed CSV
- `build_index` — embed `search_text` → build & save the FAISS index + metadata
- `evaluate` — run the labeled test set through the real pipeline → `evaluation/results.json`
- `test_embeddings`, `test_retrieval`, `test_reranker`, `test_llm`, `test_graph` — component smoke tests

## Layout

```
backend/
├── app/
│   ├── main.py                 # FastAPI app factory + entrypoint
│   ├── api/routes/             # health, incidents, dataset, evaluation
│   ├── core/                   # config (Pydantic Settings), logging
│   ├── models/schemas.py       # request/response + RCAResponse schemas
│   ├── preprocessing/          # validator, cleaner, transformer (search_text)
│   ├── rag/                    # embeddings, vector_store, retriever,
│   │                           #   reranker, prompts, llm (Groq)
│   ├── agent/                  # LangGraph workflow
│   │   ├── graph.py            # analyze→retrieve→rerank→evidence_check→…
│   │   └── nodes/              # analyze, retrieve, rerank, evidence_check,
│   │                           #   generate_rca, validate (+ fallback in graph)
│   └── services/               # dataset_service, rca_service (API adapters)
├── scripts/                    # CLI entrypoints (see above)
├── data/
│   ├── raw/incidents.csv       # source dataset (read-only)
│   ├── processed/              # incidents_clean.csv (generated)
│   └── vectorstore/            # index.faiss + metadata.pkl (generated)
├── docs/evaluation.md          # metric definitions
├── evaluation/results.json     # latest evaluation output
├── pyproject.toml / requirements.txt / uv.lock
└── .env.example
```

## Pipeline

```
CSV → validate → clean → search_text (project + summary + description)
    → embeddings (MiniLM, 384-d, L2-normalized) → FAISS IndexFlatIP + metadata
                                                              │
new incident → analyze → retrieve (FAISS Top-10) → rerank (Top-5)
        → evidence_check ┬─ sufficient   → Groq LLM → validate → RCA
                         └─ insufficient → "Not explicitly documented."
```

Only project/summary/description are embedded; `root_cause` and
`resolution_notes` are retained as metadata and returned as evidence after a
match — no answer leakage into the retrieval representation.
