# Evaluation

This document describes how the RCA pipeline is evaluated, the test data used,
the metrics, the observed results, and the limitations of the methodology.

Everything here is produced by [`scripts/evaluate.py`](../scripts/evaluate.py),
which runs a hand-labeled test set through the **real** pipeline
(embeddings → FAISS → rerank → LangGraph → Groq). No numbers are hand-entered;
the machine-readable source of truth is
[`evaluation/results.json`](../evaluation/results.json).

Run it with:

```bash
uv run python -m scripts.evaluate
```

## Test methodology

1. A small, **hand-labeled test set** of representative incidents is defined in
   `scripts/evaluate.py`. Each case has:
   - a `query` — a paraphrase of a real incident (deliberately *not* a copy of a
     ticket title, so retrieval is non-trivial);
   - `relevant_ids` — the historical ticket IDs a support engineer would accept
     as correct matches (the retrieval ground truth);
   - `reference_id` — the single primary ticket whose documented `root_cause` /
     `resolution` serve as the **gold answer** for RCA quality.
2. The model and vector store are **warmed up** once before timing, so latency
   figures reflect steady-state (not the one-time model load).
3. For each case the harness runs, and times, three things:
   - `embed_text(query)` — embedding latency;
   - `two_stage_retrieve(query)` — retrieval latency (FAISS + rerank);
   - `run_rca_graph(query)` — the full LangGraph workflow (total RCA latency).
   Retrieval metrics are computed from the graph's reranked Top-5 (`evidence`),
   and RCA metrics from the graph's `rca` output.
4. Results (aggregates **and** every per-case detail) are written to
   `evaluation/results.json` for inspection.

The final case is intentionally **out of domain** (a coffee-machine leak) to
verify that the system abstains rather than fabricates.

## Dataset

- **Corpus:** the 300-record curated subset of the Apache Jira (Kafka) issue
  dataset, indexed as `data/vectorstore/index.faiss` (+ `metadata.pkl`).
- **Test set:** 8 hand-labeled queries (7 in-domain with known relevant tickets,
  1 out-of-domain). Ground-truth ticket IDs were verified to exist in the
  processed dataset before use.
- **Gold RCA answers:** the documented `root_cause` / `resolution` fields of each
  case's `reference_id`, read directly from `data/processed/incidents_clean.csv`.

## Metrics

### Retrieval (reranked Top-5 vs. hand-labeled relevant IDs)
- **Recall@5** = |relevant ∩ top5| / |relevant|
- **Precision@5** = |relevant ∩ top5| / 5
- **MRR** = mean reciprocal rank of the first relevant hit in the Top-5

Averaged over the 7 in-domain queries (the out-of-domain query has no relevant
set and is excluded from retrieval averages).

### RCA quality (automatic proxies — see *Limitations*)
- **root_cause_correctness** — share of cases judged correct. For a case with a
  documented gold cause, "correct" means `cosine(generated, gold) ≥ 0.55`
  (MiniLM embeddings). For a case whose gold cause is undocumented or
  out-of-domain, "correct" means the model **abstained** with exactly
  `"Not explicitly documented."`.
- **mean_root_cause_alignment** — mean cosine between the generated and gold root
  cause, over cases with a documented gold cause.
- **resolution_relevance** — mean cosine between the generated and gold
  resolution, over cases whose gold resolution is substantive.
- **evidence_support** — share of RCAs whose every cited ticket ID is present in
  the retrieved evidence (grounding / no dangling citations).
- **hallucination_rate** — share of RCAs that assert a concrete (non-sentinel)
  root cause while being **unsupported** (no citation, or a citation outside the
  evidence). An operational proxy for unsupported fabrication.
- **abstention_correct_rate** — of the cases that *should* abstain, the share
  that did.

### Performance (milliseconds, steady-state)
- **embedding**, **retrieval**, and **total_rca** latency (mean / median / min /
  max across cases).

## Results

From the recorded run in `evaluation/results.json`
(model: `openai/gpt-oss-120b`; embeddings: `all-MiniLM-L6-v2`; fetch_k=10,
top_k=5):

### Retrieval (n = 7)
| Metric | Value |
|---|---|
| Recall@5 | **0.93** |
| Precision@5 | **0.20** |
| MRR | **1.00** |

- MRR = 1.0: the first relevant ticket was ranked **#1** in every in-domain query.
- Precision@5 = 0.20 is the expected ceiling here: each query has ~1 relevant
  ticket, so at most 1 of 5 retrieved can be relevant (0.20).
- Recall@5 = 0.93 (not 1.0) is an honest miss: the `rebalance-loop` query listed
  two relevant tickets (`KAFKA-12890`, `KAFKA-12896`) and only `KAFKA-12890`
  (rank 1) made the Top-5, giving that query a recall of 0.5.

### RCA quality
| Metric | Value |
|---|---|
| root_cause_correctness | **1.00** |
| mean_root_cause_alignment | **0.88** |
| resolution_relevance (mean) | **0.56** |
| evidence_support | **1.00** |
| hallucination_rate | **0.00** |
| abstention_correct_rate | **1.00** |

- **No hallucinations** and **full evidence support**: every cited ticket came
  from the retrieved evidence; no case asserted an unsupported concrete cause.
- **Abstention works**: the out-of-domain coffee case returned
  `"Not explicitly documented."`. So did `consumer-cpu-broker-down` — its gold
  ticket (`KAFKA-10254`) has *no documented root cause*, so abstaining is the
  correct behavior, and the harness scores it accordingly (alignment `null`).
- **Resolution relevance is moderate (0.56)** because many historical
  resolutions in the corpus are terse (e.g., "Fixed") or are discussion
  snippets, so cosine against them is a weak signal (see *Limitations*).

### Performance (ms)
| Stage | mean | median | min | max |
|---|---|---|---|---|
| embedding | 38.1 | 13.2 | 8.0 | 88.5 |
| retrieval | 19.0 | 13.5 | 10.2 | 56.2 |
| total RCA | 8283.8 | 7219.4 | 16.2 | 19000.0 |

- Total RCA latency is dominated by the Groq LLM call (~7–19 s).
- The `min` total RCA of ~16 ms is the out-of-domain case: `evidence_check`
  routed it to the deterministic fallback, so **no LLM call was made** — a
  concrete illustration of keeping cheap decisions out of the LLM.
- The embedding `max` (88 ms) is the first timed call; the median (~13 ms) is
  representative.

## Limitations

- **RCA quality is measured automatically, not by human graders.** Root-cause
  correctness and resolution relevance are **embedding-cosine proxies** against a
  single hand-labeled reference ticket. High cosine indicates semantic overlap,
  not verified factual correctness; a human review would be more authoritative.
- **Small test set (8 cases).** Aggregates are indicative, not statistically
  robust. Absolute numbers (e.g., Recall@5 = 0.93) should be read as directional.
- **Single relevant ticket per query (mostly).** This caps Precision@5 at 0.20
  and makes recall sensitive to individual misses.
- **Noisy gold resolutions.** Historical `resolution` text is often terse
  ("Fixed") or conversational, which depresses and adds noise to the resolution
  relevance metric.
- **hallucination_rate is a proxy.** It detects *unsupported* assertions
  (missing/invalid citations), not subtle factual errors within a
  well-cited-but-wrong explanation. It is a lower bound on true hallucination.
- **Ground-truth relevance labels are the author's judgments**, derived from
  reading the dataset — reasonable for a prototype but not independently
  adjudicated.
- **Latency depends on the Groq endpoint** and will vary with network and model
  load; the figures are a snapshot from one run on `openai/gpt-oss-120b`.
