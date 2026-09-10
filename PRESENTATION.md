# Incident Root Cause Analysis (RCA) Assistant — Presentation & Q&A

An evidence-grounded, RAG-based assistant that helps support engineers find the
**root cause** and **technical resolution** of a newly reported incident by
retrieving and reasoning over 3,000 real historical incidents from 8 Apache
open-source projects.

---

## 1. What problem are we solving?

When a production incident is reported, engineers waste hours manually searching
old tickets, wikis, and chat history to answer two questions: *"Have we seen this
before?"* and *"How was it actually fixed?"*

This is slow and error-prone because:

- **Institutional knowledge is buried** in thousands of unstructured Jira tickets.
- **Keyword search fails** — the same failure is described with different words
  (e.g. "NPE" vs. "NullPointerException", "consumer stuck" vs. "rebalance loop").
- **Jira status lies about resolution** — a ticket marked *"Fixed"/"Closed"* tells
  you nothing about *how* it was fixed. The technical fix lives in comments and
  descriptions, not the workflow status.

**Our solution:** paste an incident description and instantly get a ranked list of
the most similar historical incidents **plus** an AI-generated root-cause analysis
that is grounded *only* in that retrieved evidence — never invented.

---

## 2. How the solution works

The end-to-end flow, from raw data to answer:

```
CSV upload
   ↓  validate (schema + quality)
   ↓  clean   (Jira markup, Unicode, whitespace — meaning preserved)
   ↓  search_text  = Project + Summary + Description  ONLY
   ↓  SentenceTransformer embeddings (local, 384-dim, L2-normalized)
   ↓  FAISS vector store + per-vector metadata
──────────────────────────────────────────────────────────────
New incident submitted
   ↓  analyze   (normalize text, extract technical terms)
   ↓  retrieve  (FAISS cosine → Top-10 candidates)
   ↓  rerank    (0.70·semantic + 0.15·technical-overlap + 0.15·keyword → Top-5)
   ↓  evidence_check   (5-dimension alignment gate — anti-hallucination)
   ↓         ├─ insufficient → deterministic "Not explicitly documented." fallback
   ↓         └─ sufficient   → Groq LLM RCA generation
   ↓  validate  (citation check + mechanism check — anti-hallucination)
   ↓  API response  (resolution_notes → public "resolution")
   ↓  Frontend  (RCA summary + cited tickets + similar incidents)
```

**The key design decision:** we embed *only* the problem statement
(project + summary + description). The **answer fields** — `root_cause` and
`resolution_notes` — are stored as retrieval metadata and returned *after* a match
is found. This avoids **semantic leakage** (embedding the answer into the search
text would let the model "cheat" and inflate similarity).

---

## 3. Technology stack

| Layer | Technology | Why |
|---|---|---|
| **Frontend** | React 18, Vite 6, Tailwind CSS 4 | Fast dev, small footprint, clean UI |
| **Backend API** | FastAPI + Uvicorn | Async, auto-validated, OpenAPI docs out of the box |
| **Validation/models** | Pydantic v2 + pydantic-settings | Typed request/response + typed config |
| **Data processing** | pandas | Robust CSV parsing, NaN/Unicode/multiline handling |
| **Embeddings** | Sentence-Transformers `all-MiniLM-L6-v2` (**local**) | 384-dim, fast, free, no data leaves the box |
| **Vector store** | FAISS `IndexFlatIP` (CPU) | Exact cosine search over normalized vectors |
| **Orchestration** | LangGraph | Explicit, inspectable state-machine workflow |
| **LLM** | Groq (`openai/gpt-oss-120b`) via LangChain | Very low latency; structured output binding |
| **Package mgmt** | `uv` | Fast, reproducible Python environments |

**Embeddings are local; only the final RCA text generation calls Groq.** The Groq
API key is read from `.env` and is never logged, embedded in prompts, or sent to
the frontend.

---

## 4. System architecture and data flow

### Components

- **Preprocessing** (`app/preprocessing/`): `validator` → `cleaner` → `transformer`.
- **RAG core** (`app/rag/`): `embeddings`, `vector_store`, `retriever`, `reranker`,
  `prompts`, `llm`.
- **Agent workflow** (`app/agent/`): a LangGraph `StateGraph` with nodes
  `analyze → retrieve → rerank → evidence_check → (generate_rca → validate | fallback)`.
- **Service layer** (`app/services/`): `dataset_service` (upload→index),
  `rca_service` (graph→API shape).
- **API** (`app/api/routes/`): `health`, `incidents`, `dataset`.

### Two data flows

**A. Ingestion (offline / on upload):**
`CSV → validate → clean → build search_text → embed (batched) → FAISS index +
metadata.pkl` saved to `data/vectorstore/`.

**B. Query (online, per request):**
`incident text → normalize → embed → FAISS Top-10 → rerank Top-5 → evidence gate
→ LLM (or fallback) → deterministic validation → JSON response`.

The graph is **compiled once and reused**; the FAISS store and embedding model are
**loaded once (thread-safe) and cached** in memory for low per-request latency.

### The canonical dataset schema (14 columns)

`ticket_id, project, summary, description, components, labels, comments,
root_cause, resolution_status, resolution_notes, root_cause_source,
resolution_source, evidence_quality, search_text`

> **Critical distinction:** `resolution_status` is Jira workflow state
> (Fixed/Resolved/Closed) and is **never** treated as technical evidence.
> `resolution_notes` is the actual technical fix. Internally we use
> `resolution_notes`; the public API exposes it under the field name `resolution`
> for backward compatibility.

---

## 5. Where AI / ML / GenAI is used

We use AI at **three distinct stages**, each with a specific job:

1. **ML — Embeddings (retrieval).** A local Sentence-Transformer model
   (`all-MiniLM-L6-v2`) converts text into 384-dim vectors so we can find
   *semantically* similar incidents — matching meaning, not keywords.

2. **Heuristic ML — Reranking.** A transparent, weighted blend
   (`0.70·cosine + 0.15·technical-term-overlap + 0.15·keyword-overlap`) refines the
   FAISS candidates. This promotes incidents sharing exact exception names / config
   keys — explainable to a judge, no black box.

3. **GenAI — Root-cause synthesis.** Groq's LLM reads the retrieved evidence and
   produces a structured RCA (`root_cause`, `resolution`, `summary`, cited tickets,
   confidence). It is **constrained by structured output** and **hard guardrails**:
   evidence-only, no inventing causes, similarity ≠ proof, workflow status ≠
   resolution, and the exact fallback string *"Not explicitly documented."* when
   evidence is insufficient.

**Anti-hallucination is itself two deterministic (non-AI) gates** wrapped around
the LLM: an **evidence-alignment gate** before generation and a
**citation + mechanism-match validator** after generation.

---

## 6. APIs, database, and integrations

### REST API (FastAPI, prefix `/api`)

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/api/health` | Liveness probe |
| `POST` | `/api/incidents/analyze` | Analyze an incident → RCA + evidence |
| `POST` | `/api/dataset/upload` | Upload CSV → validate, clean, embed, rebuild index |

**`/api/incidents/analyze` response shape:**
`summary, root_cause, resolution, confidence, similar_incidents[], supporting_incidents[]`
— where each incident carries `ticket_id, similarity, description, root_cause,
resolution`.

### "Database"

There is **no traditional database.** The store is a **file-based vector index**:
- `data/vectorstore/index.faiss` — the FAISS vectors (~4.6 MB for 3,000 records).
- `data/vectorstore/metadata.pkl` — aligned per-vector metadata (~23 MB).
- `data/processed/incidents_clean.csv` — the cleaned, derived dataset.

The **raw dataset is treated as read-only**; only derived artifacts are written.
This keeps the system dependency-free and trivially portable. (A managed vector DB
like Qdrant/pgvector is a clean future swap — the `VectorStore` class is the seam.)

### Integrations

- **Groq API** — the only external network call, used solely for RCA text
  generation (via LangChain's `ChatGroq` with structured output).
- **Hugging Face** — one-time download/cache of the embedding model weights.

---

## 7. How the solution is deployed

**Backend** (from `backend/`):
```bash
uv sync                                        # install deps
uv run python -m scripts.validate_dataset      # 1. validate CSV
uv run python -m scripts.preprocess            # 2. clean + build search_text
uv run python -m scripts.build_index           # 3. embed + build FAISS
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

**Frontend** (from `frontend/`):
```bash
npm install
npm run dev        # dev server (proxies /api to the backend)
npm run build      # production static bundle
```

**Configuration** via `backend/.env`: `GROQ_API_KEY`, `GROQ_MODEL`,
`EMBEDDING_MODEL`, `LOG_LEVEL`, CORS origins. Every setting has a safe default
except the Groq key.

**Deployment model:** the backend is a standard ASGI app — deployable as a
container behind any ASGI server, or on any VM. Because the vector store is just
two files, deployment is stateless apart from those artifacts (bake them into the
image or mount a volume). The frontend is a static bundle servable from any CDN.

---

## 8. Anticipated evaluator questions

### Q: Why did you choose this approach (RAG over fine-tuning)?
Historical incidents change constantly — new tickets arrive daily. **RAG lets us
update knowledge by re-indexing (seconds), with zero retraining.** It's also
**auditable**: every claim cites a real ticket ID, which is essential for engineer
trust. Fine-tuning would bake knowledge into opaque weights, be expensive to
refresh, and hallucinate confidently without citations.

### Q: Why is AI required?
Keyword/SQL search cannot bridge vocabulary gaps ("NPE" ≠ "NullPointerException",
"consumer stuck" ≠ "rebalance loop"). **Embeddings capture meaning**, so we match
incidents that describe the same failure in different words. Then a **GenAI layer
synthesizes** scattered evidence (description + root cause + fix notes across
several tickets) into one concise, actionable answer — something no rule-based
system can do across free-form Jira text.

### Q: How did you test / evaluate it?
Three levels:
- **Unit/pipeline checks** on the real 3,000-record dataset: 8 projects, no
  duplicate ticket IDs, NaN/Unicode/multiline-safe cleaning, sentinel preservation,
  and a **leakage check proving `search_text` contains only project+summary+
  description** (no answer fields).
- **A labeled evaluation harness** (`scripts/evaluate.py`) runs 8 paraphrased
  queries (one per Apache project, plus 1 deliberately out-of-domain) through the
  **real** pipeline (embeddings → FAISS → rerank → LangGraph → Groq). Measured
  results on the current dataset (Top-5 evidence):

  | Metric | Result |
  |---|---|
  | Recall@5 | **0.875** (7/8 correct ticket retrieved) |
  | MRR | **0.875** (correct ticket ranked #1 for 7/8) |
  | Root-cause correctness | **0.67** |
  | Mean root-cause alignment (cosine vs. gold) | **0.61** |
  | Resolution relevance (cosine vs. gold) | **0.51** |
  | Evidence-support rate (citations grounded) | **1.0** |
  | **Hallucination rate** | **0.0** |
  | Abstention-correct (out-of-domain) | **1.0** |
  | Latency — embedding / retrieval | ~74 ms / ~54 ms |

  The one retrieval miss was a Flink test-failure case; the out-of-domain "coffee
  machine" query correctly **abstained** (similarity 0.26, below the relevance
  floor). **Zero hallucinations** and **100% grounded citations** across the set.
  (Root-cause correctness is graded strictly by cosine ≥ 0.55 against a single
  gold ticket over just 8 cases, so one borderline paraphrase swings it ~11%; the
  grounding metrics — 0.0 hallucination, 1.0 evidence support — are the robust
  signal.)
- **End-to-end HTTP tests:** upload → index → analyze verified through the live API,
  including the abstention path (returns the exact sentinel, cites nothing).

### Q: What makes your solution different?
1. **No semantic leakage** — we deliberately *exclude* answers from the embedding
   text; most naive RAG demos embed everything and inflate their own scores.
2. **Two deterministic anti-hallucination gates** around the LLM (evidence
   alignment before, citation + mechanism-match after). It *abstains* with
   *"Not explicitly documented."* rather than guessing.
3. **Workflow status ≠ resolution** — we refuse to treat "Fixed"/"Closed" as a
   technical fix, a subtlety most systems get wrong.
4. **Explainable reranking** — fixed, visible weights, not a black box.
5. **Every answer is cited** to real ticket IDs.

### Q: Can it handle more users or data?
- **Data:** FAISS `IndexFlatIP` handles tens of thousands of vectors on CPU
  comfortably; for millions, swap to an approximate index (`IndexIVFFlat`/HNSW) —
  the `VectorStore` class isolates that change. Embeddings are batched.
- **Users:** the FastAPI app is async and stateless per request; the model and
  index are loaded once and shared. Scale horizontally by running multiple workers/
  replicas behind a load balancer (they share the read-only index). Groq is the
  main latency/throughput dependency and is itself highly scalable.

### Q: What would you improve with more time?
- Swap file-based FAISS for a **managed vector DB** (Qdrant/pgvector) with metadata
  filtering (e.g. restrict to one project).
- **Hybrid retrieval** (BM25 + dense) for rare exact identifiers.
- A **feedback loop** — let engineers mark answers helpful/not, and use it to tune
  reranker weights and thresholds.
- **Streaming** LLM responses and per-project fine-tuned thresholds.
- **Automated regression evals** in CI on every change.
- Richer observability (latency/quality dashboards).

---

## Quick reference — commands

```bash
# Run backend (from backend/)
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000

# Build the dataset/index (from backend/)
uv run python -m scripts.validate_dataset
uv run python -m scripts.preprocess
uv run python -m scripts.build_index

# Test an RCA request
curl -X POST http://127.0.0.1:8000/api/incidents/analyze \
  -H "Content-Type: application/json" \
  -d '{"description":"Kafka Streams resource leak because KeyValueIterator instances are not closed after iteration."}'
```
