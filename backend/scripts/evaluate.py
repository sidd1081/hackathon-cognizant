"""End-to-end evaluation of the RCA pipeline.

Runs a hand-labeled test set through the REAL pipeline (hybrid retrieval:
FAISS + BM25 -> RRF fusion -> rerank -> LangGraph -> Groq) and measures
retrieval quality, RCA quality, and latency. Nothing is fabricated: every
number is computed from an actual run and every per-case detail is written
to evaluation/results.json for inspection.

Metric definitions (see docs/evaluation.md for the full write-up):

Retrieval (vs. hand-labeled relevant ticket IDs, over the reranked Top-5):
  * recall@5     = |relevant ∩ top5| / |relevant|
  * precision@5  = |relevant ∩ top5| / 5
  * MRR          = mean reciprocal rank of the first relevant hit in the Top-5

RCA (automatic proxies — NOT human grading; each case has a hand-labeled
reference ticket whose documented root_cause/resolution is the "gold" answer):
  * root_cause_correctness = share of cases where the generated root cause is
      correct: for cases with a documented gold cause, cosine(generated, gold)
      >= threshold; for cases whose gold is undocumented/out-of-domain, correct
      means the model abstained with exactly "Not explicitly documented.".
  * resolution_relevance   = mean cosine(generated resolution, gold resolution),
      over cases whose gold resolution is substantive.
  * evidence_support       = share of RCAs whose every cited ticket is present
      in the retrieved evidence (grounding check).
  * hallucination_rate     = share of RCAs that assert a concrete (non-sentinel)
      root cause while being unsupported (no citation, or a citation outside the
      evidence). Operational proxy for unsupported fabrication.

Performance (steady-state; model preloaded): embedding, retrieval, and total
RCA latency in milliseconds.
"""

from __future__ import annotations

import json
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):  # pragma: no cover
    pass

from app.agent.graph import run_rca_graph
from app.core.config import settings
from app.models.schemas import NOT_DOCUMENTED
from app.rag.embeddings import embed_text, embed_texts, get_embedding_model
from app.rag.hybrid_retriever import DEFAULT_PER_SOURCE_K, hybrid_retrieve
from app.rag.reranker import DEFAULT_FETCH_K, DEFAULT_FINAL_K
from app.rag.retriever import get_bm25_store, get_vector_store

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROCESSED_PATH = _BACKEND_ROOT / "data" / "processed" / "incidents_clean.csv"
RESULTS_PATH = _BACKEND_ROOT / "evaluation" / "results.json"

# Cosine threshold above which a generated root cause is counted "correct"
# against the gold documented root cause (MiniLM embeddings).
CORRECTNESS_THRESHOLD = 0.55

# Hand-labeled test set, grounded in the current dataset (data/processed/
# incidents_clean.csv). Queries are paraphrases (not copied ticket titles);
# `relevant_ids` are the historical tickets a support engineer would accept as
# matches; `reference_id` is the primary ticket used as the gold RCA answer.
# Every reference ticket is present in the corpus and has a documented root cause
# and resolution notes. Cases span all 8 Apache projects; the final case is
# intentionally out-of-domain to test abstention.
TEST_SET: list[dict] = [
    {
        "id": "kafka-keyvalueiterator-leak",
        "query": "A Kafka Streams application leaks resources because "
        "KeyValueIterator objects returned from state store queries are never "
        "closed after they are used.",
        "relevant_ids": ["KAFKA-13122"],
        "reference_id": "KAFKA-13122",
    },
    {
        "id": "flink-entrypoint-shutdown-lock",
        "query": "A Flink cluster entrypoint fails to shut down after an "
        "uncaught exception because a thread join call keeps holding the "
        "shutdown lock, so the process hangs instead of exiting.",
        "relevant_ids": ["FLINK-23406"],
        "reference_id": "FLINK-23406",
    },
    {
        "id": "spark-yarnclustersuite-noclassdef",
        "query": "Running the Spark YarnClusterSuite integration tests throws "
        "NoClassDefFoundError unless the hadoop-3.2 build profile is explicitly "
        "activated.",
        "relevant_ids": ["SPARK-36067"],
        "reference_id": "SPARK-36067",
    },
    {
        "id": "hbase-bufferedmutator-executor-leak",
        "query": "Repeatedly calling Connection.getBufferedMutator for a table "
        "leaks thread pool executors and never releases them.",
        "relevant_ids": ["HBASE-26088"],
        "reference_id": "HBASE-26088",
    },
    {
        "id": "cassandra-pending-ranges-shutdown-peer",
        "query": "When a moving node crashes hard during a range movement, "
        "stale pending ranges remain for the shutdown peer and block a "
        "subsequent node replacement.",
        "relevant_ids": ["CASSANDRA-16796"],
        "reference_id": "CASSANDRA-16796",
    },
    {
        "id": "solr-grouped-query-renamed-key-npe",
        "query": "A distributed grouped query in Solr throws a "
        "NullPointerException when the unique key field has been renamed.",
        "relevant_ids": ["SOLR-15273"],
        "reference_id": "SOLR-15273",
    },
    {
        "id": "zookeeper-listsubtreebfs-root",
        "query": "Calling ZkUtil listSubTreeBFS on the root path throws an "
        "IllegalArgumentException because an invalid path with an empty node "
        "name is generated.",
        "relevant_ids": ["ZOOKEEPER-4325"],
        "reference_id": "ZOOKEEPER-4325",
    },
    {
        "id": "hadoop-auth-jetty-server-dependency",
        "query": "The hadoop-auth module should drop its jetty-server "
        "dependency because Jetty prevents loading jetty-server classes inside "
        "web applications.",
        "relevant_ids": ["HADOOP-17621"],
        "reference_id": "HADOOP-17621",
    },
    {
        "id": "out-of-domain-coffee",
        "query": "The office coffee machine is leaking water onto the "
        "break-room floor.",
        "relevant_ids": [],
        "reference_id": None,
    },
]


def _cosine(text_a: str, text_b: str) -> float:
    """Cosine similarity of two texts via normalized MiniLM embeddings."""
    embs = embed_texts([text_a, text_b])
    return float(np.dot(embs[0], embs[1]))


def _is_sentinel(text: str) -> bool:
    return (text or "").strip() == NOT_DOCUMENTED


def _summ(values: list[float]) -> dict:
    """Summary stats for a list of numbers (rounded)."""
    if not values:
        return {"mean": None, "median": None, "min": None, "max": None, "n": 0}
    return {
        "mean": round(statistics.fmean(values), 2),
        "median": round(statistics.median(values), 2),
        "min": round(min(values), 2),
        "max": round(max(values), 2),
        "n": len(values),
    }


def main() -> int:
    if not PROCESSED_PATH.is_file():
        print(f"Processed dataset not found: {PROCESSED_PATH}")
        print("Run `uv run python -m scripts.preprocess` first.")
        return 1
    if not settings.groq_api_key:
        print("GROQ_API_KEY is not set; cannot evaluate RCA generation.")
        return 1

    df = pd.read_csv(PROCESSED_PATH, dtype=str, keep_default_na=False)
    by_id = {row["ticket_id"]: row for _, row in df.iterrows()}

    # Warm up so latencies reflect steady-state (exclude one-time model load).
    print("Warming up model, vector store, and BM25 index…")
    get_embedding_model()
    get_vector_store()
    try:
        get_bm25_store()
    except Exception:
        print("  (BM25 index not available — hybrid retrieval will fall back to FAISS-only)")
    embed_text("warmup")

    cases: list[dict] = []
    emb_latencies: list[float] = []
    ret_latencies: list[float] = []
    rca_latencies: list[float] = []

    for spec in TEST_SET:
        query = spec["query"]
        relevant = list(spec["relevant_ids"])
        ref_id = spec["reference_id"]
        print(f"\n[{spec['id']}] {query[:70]}…")

        # --- latency: embedding, retrieval, full graph ---
        t0 = time.perf_counter()
        embed_text(query)
        emb_ms = (time.perf_counter() - t0) * 1000

        t0 = time.perf_counter()
        hybrid_retrieve(query, top_k=DEFAULT_FETCH_K)
        ret_ms = (time.perf_counter() - t0) * 1000

        t0 = time.perf_counter()
        state = run_rca_graph(query)
        rca_ms = (time.perf_counter() - t0) * 1000

        emb_latencies.append(emb_ms)
        ret_latencies.append(ret_ms)
        rca_latencies.append(rca_ms)

        evidence = state.get("evidence", [])
        retrieved_ids = [e.ticket_id for e in evidence]
        top5 = retrieved_ids[:5]
        rca = state["rca"]

        # --- retrieval metrics (only when a relevant set is defined) ---
        recall = precision = rr = None
        if relevant:
            rel = set(relevant)
            hits = rel & set(top5)
            recall = len(hits) / len(rel)
            precision = len(hits) / len(top5) if top5 else 0.0
            rr = 0.0
            for rank, tid in enumerate(top5, start=1):
                if tid in rel:
                    rr = 1.0 / rank
                    break

        # --- RCA metrics ---
        gen_rc = rca.root_cause
        gen_res = rca.resolution
        gen_is_sentinel = _is_sentinel(gen_rc)

        ref_row = by_id.get(ref_id) if ref_id else None
        ref_rc = ref_row["root_cause"] if ref_row is not None else ""
        ref_res = ref_row["resolution_notes"] if ref_row is not None else ""
        gold_documented = bool(ref_id) and bool(ref_rc.strip()) and not _is_sentinel(ref_rc)

        if not gold_documented:
            # Expected behavior is abstention (undocumented / out-of-domain).
            expected = "abstain"
            rc_alignment = None
            root_correct = gen_is_sentinel
        else:
            expected = "documented"
            rc_alignment = 0.0 if gen_is_sentinel else round(_cosine(gen_rc, ref_rc), 4)
            root_correct = (not gen_is_sentinel) and rc_alignment >= CORRECTNESS_THRESHOLD

        res_substantive = (
            bool(ref_res.strip()) and not _is_sentinel(ref_res) and len(ref_res.strip()) >= 12
        )
        if res_substantive and gen_res.strip() and not _is_sentinel(gen_res):
            res_relevance = round(_cosine(gen_res, ref_res), 4)
        else:
            res_relevance = None

        evidence_ids = set(retrieved_ids)
        supporting = list(rca.supporting_ticket_ids)
        cited_in_evidence = all(t in evidence_ids for t in supporting)
        hallucination = (not gen_is_sentinel) and (
            len(supporting) == 0 or not cited_in_evidence
        )

        cases.append(
            {
                "id": spec["id"],
                "query": query,
                "relevant_ids": relevant,
                "reference_id": ref_id,
                "retrieved_top5": top5,
                "recall_at_5": None if recall is None else round(recall, 4),
                "precision_at_5": None if precision is None else round(precision, 4),
                "reciprocal_rank": None if rr is None else round(rr, 4),
                "expected": expected,
                "generated_root_cause_is_sentinel": gen_is_sentinel,
                "root_cause_alignment": rc_alignment,
                "root_cause_correct": bool(root_correct),
                "resolution_relevance": res_relevance,
                "supporting_ticket_ids": supporting,
                "evidence_support": bool(cited_in_evidence),
                "hallucination_flag": bool(hallucination),
                "confidence": rca.confidence,
                "status": state.get("status"),
                "latency_ms": {
                    "embedding": round(emb_ms, 2),
                    "retrieval": round(ret_ms, 2),
                    "total_rca": round(rca_ms, 2),
                },
            }
        )

    # --- aggregate ---
    scored = [c for c in cases if c["recall_at_5"] is not None]
    recalls = [c["recall_at_5"] for c in scored]
    precisions = [c["precision_at_5"] for c in scored]
    rrs = [c["reciprocal_rank"] for c in scored]

    alignments = [c["root_cause_alignment"] for c in cases if c["root_cause_alignment"] is not None]
    resolutions = [c["resolution_relevance"] for c in cases if c["resolution_relevance"] is not None]
    abstain_cases = [c for c in cases if c["expected"] == "abstain"]

    def rate(flags: list[bool]) -> float:
        return round(sum(1 for f in flags if f) / len(flags), 4) if flags else None

    results = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "config": {
            "embedding_model": settings.embedding_model,
            "groq_model": settings.groq_model,
            "retrieval_mode": "hybrid (FAISS + BM25 → RRF)",
            "per_source_k": DEFAULT_PER_SOURCE_K,
            "fetch_k": DEFAULT_FETCH_K,
            "top_k": DEFAULT_FINAL_K,
            "num_cases": len(cases),
            "correctness_threshold": CORRECTNESS_THRESHOLD,
        },
        "retrieval": {
            "num_scored_queries": len(scored),
            "recall_at_5": round(statistics.fmean(recalls), 4) if recalls else None,
            "precision_at_5": round(statistics.fmean(precisions), 4) if precisions else None,
            "mrr": round(statistics.fmean(rrs), 4) if rrs else None,
        },
        "rca": {
            "root_cause_correctness": rate([c["root_cause_correct"] for c in cases]),
            "mean_root_cause_alignment": round(statistics.fmean(alignments), 4) if alignments else None,
            "resolution_relevance_mean": round(statistics.fmean(resolutions), 4) if resolutions else None,
            "evidence_support_rate": rate([c["evidence_support"] for c in cases]),
            "hallucination_rate": rate([c["hallucination_flag"] for c in cases]),
            "abstention_correct_rate": rate([c["generated_root_cause_is_sentinel"] for c in abstain_cases]),
        },
        "performance_ms": {
            "embedding": _summ(emb_latencies),
            "retrieval": _summ(ret_latencies),
            "total_rca": _summ(rca_latencies),
        },
        "cases": cases,
    }

    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(results, indent=2), encoding="utf-8")

    # --- console summary ---
    print("\n" + "=" * 64)
    print(" EVALUATION SUMMARY")
    print("=" * 64)
    r = results["retrieval"]
    print(f" Retrieval  (n={r['num_scored_queries']}): "
          f"Recall@5={r['recall_at_5']}  Precision@5={r['precision_at_5']}  MRR={r['mrr']}")
    q = results["rca"]
    print(f" RCA        : root_cause_correctness={q['root_cause_correctness']}  "
          f"mean_alignment={q['mean_root_cause_alignment']}")
    print(f"              resolution_relevance={q['resolution_relevance_mean']}  "
          f"evidence_support={q['evidence_support_rate']}")
    print(f"              hallucination_rate={q['hallucination_rate']}  "
          f"abstention_correct={q['abstention_correct_rate']}")
    p = results["performance_ms"]
    print(f" Latency ms : embedding(mean={p['embedding']['mean']})  "
          f"retrieval(mean={p['retrieval']['mean']})  total_rca(mean={p['total_rca']['mean']})")
    print("=" * 64)
    print(f"Saved: {RESULTS_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
