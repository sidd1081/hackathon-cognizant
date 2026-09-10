# Project Deep Dive — AI Incident Resolver

A reference for explaining this project confidently — what it does, how each
piece works, why it was built this way, and how to answer hard questions about
it. Everything below is verified against the actual code and data, not just
written docs.

---

## 1. One-paragraph pitch

When a new incident is reported, support engineers waste hours manually
searching old tickets to answer two questions: *"have we seen this before?"*
and *"how was it actually fixed?"*. This system embeds a newly reported
incident, retrieves the most similar historical incidents from a vector
index, and asks an LLM to synthesize a root-cause analysis — but only when
the retrieved evidence actually documents a real technical cause. If it
doesn't, the system says so explicitly instead of guessing. Every claim is
traceable to a real historical ticket ID.

---

## 2. The two data flows

**A. Ingestion (when a CSV is uploaded):**
```
CSV → validate (schema check) → clean (Jira markup, dedup) → search_text
    → embed (MiniLM, local) → FAISS index + metadata.pkl
```

**B. Query (when an engineer submits an incident):**
```
incident text → analyze → retrieve (FAISS top 10) → rerank (top 5)
    → evidence_check (deterministic gate)
        ├─ sufficient   → Groq LLM → validate → response
        └─ insufficient → "Not explicitly documented." → response
```

Both flows are implemented as a compiled **LangGraph** state machine
([backend/app/agent/graph.py](backend/app/agent/graph.py)) for the query
side; ingestion is a plain function pipeline
([backend/app/services/dataset_service.py](backend/app/services/dataset_service.py)).

---

## 3. Folder structure — what every file does

```
hackathon/
├── README.md                 — project overview, quickstart, architecture summary
├── PRESENTATION.md           — detailed Q&A-style writeup for judges
├── PROJECT_DEEP_DIVE.md      — this file
├── PPT_UPDATES.md            — exact slide content for the pitch deck
├── TEST_CASES.md             — verified example incidents with expected tickets/confidence
│
├── backend/
│   ├── app/
│   │   ├── main.py                     — FastAPI app factory: mounts all routers + CORS middleware
│   │   │
│   │   ├── core/
│   │   │   ├── config.py               — Pydantic Settings: Groq key/model, embedding model, CORS, log level
│   │   │   └── logger.py               — one-time root logging setup, shared `get_logger(name)`
│   │   │
│   │   ├── api/routes/
│   │   │   ├── health.py               — GET /api/health, liveness probe
│   │   │   ├── incidents.py            — POST /api/incidents/analyze, maps errors to HTTP status codes
│   │   │   ├── dataset.py              — POST /api/dataset/upload, 50MB guard, .csv check
│   │   │   └── evaluation.py           — GET /api/evaluation, reads evaluation/results.json
│   │   │
│   │   ├── models/
│   │   │   └── schemas.py              — RCAResponse (LLM output schema) + all HTTP request/response models
│   │   │
│   │   ├── preprocessing/
│   │   │   ├── validator.py            — checks required columns, missing values, duplicate ticket IDs
│   │   │   ├── cleaner.py              — strips Jira wiki markup, normalizes whitespace, drops duplicates
│   │   │   └── transformer.py          — builds the answer-free `search_text` (project+summary+description only)
│   │   │
│   │   ├── rag/
│   │   │   ├── embeddings.py           — loads MiniLM once, batched `embed_texts`, L2-normalized output
│   │   │   ├── vector_store.py         — FAISS `IndexFlatIP` wrapper: build / search / save / load
│   │   │   ├── retriever.py            — embeds a query, searches the store, returns `RetrievedIncident` list
│   │   │   ├── reranker.py             — 0.70/0.15/0.15 weighted rerank + technical-term extraction helpers
│   │   │   ├── prompts.py              — system prompt (8 hard rules) + evidence-packed user prompt builder
│   │   │   └── llm.py                  — Groq `ChatGroq` call bound to `RCAResponse` via structured output
│   │   │
│   │   ├── agent/
│   │   │   ├── state.py                — `RCAState` TypedDict threaded through the graph
│   │   │   ├── graph.py                — builds/compiles the LangGraph StateGraph + conditional routing
│   │   │   └── nodes/
│   │   │       ├── analyze.py          — normalize incident text, extract technical terms (no LLM)
│   │   │       ├── retrieve.py         — FAISS top-10 node (thin wrapper over rag/retriever.py)
│   │   │       ├── rerank.py           — top-10 → top-5 node (thin wrapper over rag/reranker.py)
│   │   │       ├── evidence_check.py   — 5-dimension deterministic alignment gate (component/symptom/
│   │   │       │                         mechanism/trigger/root-cause-quality) — decides LLM vs. fallback
│   │   │       ├── generate_rca.py     — the single LLM call node
│   │   │       └── validate.py         — citation check + mechanism-term grounding check (no LLM)
│   │   │
│   │   └── services/
│   │       ├── rca_service.py          — adapts the graph's final state to `AnalyzeResponse`
│   │       └── dataset_service.py      — full upload pipeline: parse → validate → clean → embed → index
│   │
│   ├── scripts/                        — CLI entrypoints, run via `uv run python -m scripts.<name>`
│   │   ├── validate_dataset.py         — CLI wrapper around preprocessing/validator.py
│   │   ├── preprocess.py               — raw CSV → validate → clean → processed CSV
│   │   ├── build_index.py              — processed CSV → embeddings → FAISS index + metadata.pkl
│   │   ├── evaluate.py                 — runs labeled queries through the real pipeline, writes results.json
│   │   ├── test_embeddings.py          — smoke test: embedding count / dimension / L2 normalization
│   │   ├── test_retrieval.py           — full pipeline test, 4 queries end-to-end with printed diagnostics
│   │   ├── test_reranker.py            — prints baseline FAISS top-5 vs. reranked top-5 side by side
│   │   ├── test_llm.py                 — isolated test of the Groq generation layer against retrieved evidence
│   │   └── test_graph.py               — runs several incidents through the full LangGraph workflow
│   │
│   ├── data/
│   │   ├── raw/incidents.csv           — read-only source: 3,000 rows, 8 Apache projects, 14 columns
│   │   ├── processed/incidents_clean.csv — cleaned + `search_text` column added
│   │   └── vectorstore/
│   │       ├── index.faiss             — FAISS vectors, confirmed 3,000 × 384-dim
│   │       └── metadata.pkl            — per-vector metadata dict, aligned to the index by row order
│   │
│   ├── evaluation/results.json         — latest measured metrics; source for GET /api/evaluation
│   ├── docs/evaluation.md              — narrative writeup of the evaluation methodology
│   ├── tests/                          — reserved for automated unit tests (currently empty)
│   ├── pyproject.toml / requirements.txt — Python dependencies, managed by `uv`
│   └── .env.example                    — template for GROQ_API_KEY, GROQ_MODEL, EMBEDDING_MODEL
│
└── frontend/
    ├── index.html / vite.config.js / package.json — Vite + React setup; dev server proxies /api to the backend
    └── src/
        ├── main.jsx                     — React root render
        ├── App.jsx                      — top-level layout, tab state, upload/analyze handlers
        ├── services/api.js              — every backend fetch call (analyze, upload, health, evaluation)
        │
        ├── hooks/
        │   ├── useBackendHealth.js      — polls GET /api/health on mount, exposes online/offline/checking
        │   └── useEvaluation.js         — fetches GET /api/evaluation on mount for the Evaluation tab
        │
        ├── lib/constants.js             — the `NOT_DOCUMENTED` sentinel + verified example incidents
        │
        └── components/
            ├── Header.jsx               — app title bar, hosts the health indicator
            ├── HealthIndicator.jsx      — colored dot + label for backend online/offline/checking
            ├── OfflineBanner.jsx        — shown when the backend is unreachable, with a retry button
            ├── DatasetPanel.jsx         — CSV upload control + post-upload indexing status
            ├── IncidentForm.jsx         — incident textarea, "Use example" cycling button, Analyze button
            ├── RcaSummary.jsx           — "AI Analysis" panel: summary, root cause, resolution, confidence, citations
            ├── SimilarIncidents.jsx     — "Historical Evidence" panel: list of IncidentCard, cited-by-AI badges
            ├── IncidentCard.jsx         — one retrieved incident: ticket ID, similarity meter, root cause, resolution
            ├── EvaluationPanel.jsx      — live benchmark metrics tab, color-coded stat tiles from useEvaluation
            └── ui/                      — generic presentational primitives, no business logic
                ├── Card.jsx             — `Card` + `Section` (the standard bordered panel-with-header used everywhere)
                ├── Badge.jsx            — colored pill + `ConfidenceBadge` (High/Medium/Low)
                ├── Pills.jsx            — `AiBadge`, `DataBadge`, `StatusPill`, `LatencyPill`
                ├── SimilarityMeter.jsx  — small 0–1 progress bar, color-graded (emerald/amber/slate)
                ├── Button.jsx           — styled button with loading/disabled states
                ├── Alert.jsx            — colored callout box (error/info variants)
                ├── EmptyState.jsx       — "nothing here yet" placeholder
                ├── Spinner.jsx          — loading spinner icon
                └── Tabs.jsx             — segmented control switching Analyze / Evaluation
```

---

## 4. The dataset (verified from the actual files on disk)

- **3,000 incidents**, exactly **375 from each of 8 Apache projects**:
  Cassandra, Flink, Hadoop, HBase, Kafka, Solr, Spark, ZooKeeper
- Source: public Zenodo dataset of real Apache Jira issues
- 14 columns: `ticket_id, project, summary, description, components, labels,
  comments, root_cause, resolution_status, resolution_notes,
  root_cause_source, resolution_source, evidence_quality, search_text`
- The **raw file is read-only** — uploads/rebuilds only ever write to
  `data/processed/` and `data/vectorstore/`, never touch `data/raw/incidents.csv`
- Index on disk: FAISS `IndexFlatIP`, confirmed **3,000 vectors, 384 dimensions**
  (matches MiniLM's output size), ~4.6 MB; `metadata.pkl` (~23 MB) holds the
  per-vector fields aligned by row index

**The one distinction to always get right when explaining this:**
`resolution_status` is the Jira workflow field (Fixed/Resolved/Closed/Done) —
it says a ticket was closed, not *how*. `resolution_notes` is the actual
technical fix text. The system treats only `resolution_notes` as evidence,
everywhere — embedding, prompting, and validation all deliberately exclude
`resolution_status`.

---

## 5. Ingestion pipeline, stage by stage

| Stage | File | What it does | Why |
|---|---|---|---|
| Validate | [validator.py](backend/app/preprocessing/validator.py) | Checks 7 required columns exist, counts missing values, flags duplicate rows and duplicate `ticket_id`s | Read-only — never invents or drops data silently; separates blocking errors from warnings |
| Clean | [cleaner.py](backend/app/preprocessing/cleaner.py) | Strips Jira wiki markup (`{{monospace}}`, `{code}` macros, `[~user]` mentions, `[text\|link]`), normalizes Unicode whitespace, drops exact and `ticket_id` duplicates | Non-destructive to meaning — technical identifiers, code, and the exact sentinel `"Not explicitly documented."` are preserved verbatim |
| Build `search_text` | [transformer.py](backend/app/preprocessing/transformer.py) | Concatenates only `Project + Summary + Description` into one field | **This is the core anti-leakage decision** — `root_cause` and `resolution_notes` are deliberately excluded from what gets embedded |
| Embed | [embeddings.py](backend/app/rag/embeddings.py) | Batched `SentenceTransformer` encode, `all-MiniLM-L6-v2`, L2-normalized, 384-dim, `float32` | Local, free, no data leaves the machine; normalization means FAISS inner product = cosine similarity |
| Index | [vector_store.py](backend/app/rag/vector_store.py) | `faiss.IndexFlatIP`, saved as `index.faiss` + `metadata.pkl` | Exact (not approximate) search — fine at 3K–100K scale; simple two-file persistence, no DB server needed |

**Why excluding the answer from the embedding matters (explain this if asked
"what's hard about RAG here"):** if you embed `root_cause`/`resolution` along
with the problem description, a query that happens to share vocabulary with
a *historical fix* — not the historical *problem* — can score artificially
high. That inflates retrieval metrics without the system actually being
better at finding the same failure. Keeping the embedded text answer-free
means a high similarity score genuinely means "similar problem," nothing else.

---

## 6. Query pipeline, node by node (LangGraph)

Compiled graph: `START → analyze → retrieve → rerank → evidence_check →
(generate_rca → validate | fallback) → END`
([graph.py](backend/app/agent/graph.py)).

### `analyze` — deterministic, no LLM
Trims/collapses whitespace, extracts technical terms (dotted identifiers,
snake_case, camelCase, ALL-CAPS acronyms) from the incident text for later
use. ([analyze.py](backend/app/agent/nodes/analyze.py))

### `retrieve` — FAISS top 10
Embeds the query using the **same three-field template** used for historical
incidents (`Project: / Summary: / Description:`, with project and summary
left blank for a freshly typed incident) so query and document vectors live
in the same space. Returns the 10 nearest neighbors by cosine similarity.
([retrieve.py](backend/app/agent/nodes/retrieve.py),
[retriever.py](backend/app/rag/retriever.py))

### `rerank` — top 10 → top 5, explainable
```
rerank_score = 0.70 × semantic (FAISS cosine)
             + 0.15 × technical-term overlap (query coverage)
             + 0.15 × keyword overlap (query coverage)
```
"Overlap" = fraction of the *query's* terms that also appear in the
candidate — an intuitive, non-black-box signal ("80% of the query's
technical terms show up in this incident"). Semantic dominates because
embeddings already capture synonyms (NPE ≈ NullPointerException); the other
two terms are precision nudges, not overrides.
([reranker.py](backend/app/rag/reranker.py))

### `evidence_check` — the anti-hallucination gate (deterministic, no LLM)
This is the most sophisticated part of the system and the one worth
explaining carefully. Similarity alone is **not** treated as proof of a
shared root cause. Instead, each of the top-5 candidates is scored across
**5 alignment dimensions**:

1. **Component** — same subsystem (consumer/broker, regionserver, namenode,
   taskmanager, znode, …) across all 8 projects
2. **Symptom** — same observed symptom vocabulary (lag, crash, timeout, leak, …)
3. **Mechanism** — shared technical terms (exception names, config keys)
4. **Trigger** — same triggering event (restart, rebalance, upgrade, …)
5. **Root-cause quality** — is the candidate's `root_cause` field actually a
   real, substantive explanation, or just the description repeated / the
   sentinel / too short to mean anything?

A candidate is "aligned" only if: similarity ≥ 0.45 (basic relevance floor —
rejects out-of-domain queries), it has a real root cause to ground on
(dimension 5), **and** either ≥ 2 of the other 4 dimensions are active, or
similarity is ≥ 0.60 on its own (strong enough to stand alone). If nothing
qualifies, the graph routes straight to `fallback` — **the LLM is never even
called.** ([evidence_check.py](backend/app/agent/nodes/evidence_check.py))

### `generate_rca` — the only non-deterministic step
Calls Groq (`openai/gpt-oss-120b` via LangChain `ChatGroq`, temperature 0)
with `with_structured_output(RCAResponse)` so the model is schema-constrained
— it can only return `root_cause`, `resolution`, `summary`,
`supporting_ticket_ids`, `confidence`. The system prompt hard-codes 8 rules
(evidence-only, no inventing details, similarity ≠ proof, symptom ≠ root
cause, never treat "Fixed/Closed" as resolution evidence, use the exact
sentinel when unsure). Evidence text is length-capped per field before being
sent to Groq to stay within free-tier token budgets — the *validator* still
checks against the full untruncated text.
([llm.py](backend/app/rag/llm.py), [prompts.py](backend/app/rag/prompts.py))

### `validate` — deterministic post-check on the LLM's output
Two checks, no LLM:
1. **Citation check** — any `supporting_ticket_ids` not actually in the
   retrieved evidence are silently dropped.
2. **Mechanism check** — extracts technical terms from the generated
   `root_cause` and verifies they appear in the cited evidence's description,
   root cause, or resolution notes (with abbreviation equivalence, e.g.
   NPE ↔ NullPointerException, and camelCase decomposition). If more than
   half the root cause's technical terms are unsupported, the whole answer is
   replaced with the sentinel and confidence is forced to `"low"`. Partial
   mismatches downgrade confidence instead of hard-failing.

This node is what catches an LLM that "sounds right" but cites a mechanism
none of the retrieved tickets actually mention.
([validate.py](backend/app/agent/nodes/validate.py))

### `fallback` — the abstention path
A tiny deterministic node, not a separate module — just returns
`root_cause = resolution = "Not explicitly documented."`, empty citations,
`confidence = "low"`. Reached whenever `evidence_check` says insufficient.

---

## 7. Why two anti-hallucination gates instead of one

- **Before generation** (`evidence_check`): stops the LLM from ever being
  asked to answer when the retrieved tickets don't actually document the
  same failure — cheaper and prevents the LLM from "trying its best" on bad
  evidence.
- **After generation** (`validate`): catches the case where evidence *was*
  sufficient but the LLM still invented a technical detail not present in
  any cited ticket, or cited a ticket it didn't really use.

Neither gate is itself an LLM call — both are plain Python heuristics, which
makes them fast, deterministic, and explainable to a judge (no "trust the
model" hand-waving).

---

## 8. API surface

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | Liveness probe |
| POST | `/api/incidents/analyze` | `{description}` → RCA + similar incidents |
| POST | `/api/dataset/upload` | Multipart CSV → validate/clean/embed/reindex |
| GET | `/api/evaluation` | Serves the latest `evaluation/results.json` to the frontend |

`/api/incidents/analyze` response: `summary, root_cause, resolution,
confidence, similar_incidents[], supporting_incidents[]` — where
`similar_incidents` is *all* retrieved evidence and `supporting_incidents`
is the subset the LLM actually cited (post-validation).
([schemas.py](backend/app/models/schemas.py))

---

## 9. Frontend structure

React + Vite + Tailwind, two tabs ([App.jsx](frontend/src/App.jsx)):

- **Analyze tab:** `DatasetPanel` (CSV upload) + `IncidentForm` (text input) →
  `RcaSummary` (AI-generated conclusion, clearly labeled "AI Analysis") +
  `SimilarIncidents` (raw retrieved tickets, labeled "Historical Evidence" —
  deliberately visually separated from the AI panel so a user never confuses
  a model's synthesis with a stored fact)
- **Evaluation tab:** `EvaluationPanel` — pulls `GET /api/evaluation` live and
  renders the benchmark metrics as color-coded stat tiles directly in the app
  (this is a real, working feature, not just a static doc — worth mentioning
  since it shows the eval isn't an afterthought)

The frontend never sees the Groq key — all LLM calls happen server-side.

---

## 10. Evaluation — what was actually measured

`backend/scripts/evaluate.py` runs 9 hand-written queries (one paraphrased
incident per Apache project, plus one deliberately out-of-domain "coffee
machine" query) through the **real, live pipeline** — not a mocked one — and
writes `evaluation/results.json`. That file is what both the pitch deck
should cite and what `/api/evaluation` actually serves to the running app.

| Metric | Result | Meaning |
|---|---|---|
| Recall@5 | 0.875 | correct ticket appeared in top 5 for 7/8 scored queries |
| MRR | 0.875 | correct ticket ranked #1 in 7/8 cases |
| Root-cause correctness | 0.67 | generated root cause matches gold (cosine ≥ 0.55) |
| Evidence-support rate | **1.0** | every citation the LLM made was grounded in real retrieved evidence |
| Hallucination rate | **0.0** | zero fabricated, unsupported claims across all cases |
| Abstention correctness | 1.0 | the out-of-domain query correctly triggered the fallback (similarity 0.26, below the 0.45 floor) |
| Embedding / retrieval latency | ~74 ms / ~54 ms mean | local, fast |
| Total RCA latency | ~12 s mean (up to ~24 s) | Groq call dominates; retrieval itself is fast |

The one retrieval miss was a Flink case; correctness/relevance metrics are
graded by cosine similarity against a single gold ticket over only 8 cases,
so they're noisy at this sample size — the grounding metrics (0.0
hallucination, 1.0 evidence support) are the more robust signal and the ones
worth leading with.

---

## 11. Anticipated hard questions

**"Why RAG instead of fine-tuning?"**
Historical incidents change daily; RAG updates by re-indexing (seconds, no
retraining) and is auditable — every answer cites a real ticket ID.
Fine-tuning bakes knowledge into opaque weights and hallucinates confidently
without citations.

**"Why do you need AI at all — why not just keyword search?"**
Keyword search can't bridge vocabulary gaps ("NPE" vs
"NullPointerException", "consumer stuck" vs "rebalance loop"). Embeddings
capture meaning; the LLM then synthesizes scattered evidence (description +
root cause + fix notes across several tickets) into one answer — something a
rule-based system can't do over free-form text.

**"How do you stop it from hallucinating?"**
Two deterministic, non-LLM gates around the one LLM call: `evidence_check`
before generation (5-dimension alignment, LLM never invoked if evidence is
weak), `validate` after generation (citation + mechanism-term grounding
check). Measured hallucination rate: 0.0 across the eval set.

**"What happens with no good match?"**
The graph routes to `fallback` and returns the exact string
`"Not explicitly documented."` for both root cause and resolution, empty
citations, low confidence — verified on the out-of-domain control query.

**"Can it scale?"**
`IndexFlatIP` handles tens of thousands of vectors comfortably on CPU; for
millions, swap to `IndexIVFFlat`/HNSW (the `VectorStore` class isolates that
change). FastAPI is async/stateless per request; model and index are loaded
once and shared across requests. Groq is the main latency dependency and is
itself horizontally scalable.

**"What would you improve with more time?"**
Hybrid retrieval (BM25 + dense) for exact identifiers, a managed vector DB
(Qdrant/pgvector) with project-level filtering, an engineer feedback loop to
tune reranker weights, streaming LLM responses, automated regression evals
in CI.

---

## 12. Key files, if someone asks to see the code

| Concern | File |
|---|---|
| LangGraph workflow definition | [backend/app/agent/graph.py](backend/app/agent/graph.py) |
| Anti-hallucination gate (pre) | [backend/app/agent/nodes/evidence_check.py](backend/app/agent/nodes/evidence_check.py) |
| Anti-hallucination gate (post) | [backend/app/agent/nodes/validate.py](backend/app/agent/nodes/validate.py) |
| Reranking formula | [backend/app/rag/reranker.py](backend/app/rag/reranker.py) |
| LLM prompt + guardrails | [backend/app/rag/prompts.py](backend/app/rag/prompts.py) |
| No-leakage embedding text | [backend/app/preprocessing/transformer.py](backend/app/preprocessing/transformer.py) |
| API contract | [backend/app/models/schemas.py](backend/app/models/schemas.py) |
| Evaluation harness | [backend/scripts/evaluate.py](backend/scripts/evaluate.py) |
| Measured results | [backend/evaluation/results.json](backend/evaluation/results.json) |
