"""Compare baseline FAISS Top-5 against reranked Top-5 (two-stage retrieval).

Usage (from the backend/ directory):

    uv run python -m scripts.test_reranker

For each query it prints:
    * BASELINE : FAISS Top-5 (semantic only)
    * RERANKED : FAISS Top-10 -> rerank -> Top-5 (semantic + technical + keyword)
plus a short note on how the ordering changed. Requires the FAISS index
(run `uv run python -m scripts.build_index` first).
"""

from __future__ import annotations

import sys
import textwrap

from app.rag.reranker import (
    DEFAULT_FETCH_K,
    W_KEYWORD,
    W_SEMANTIC,
    W_TECHNICAL,
    two_stage_retrieve,
)
from app.rag.retriever import retrieve_similar_incidents

# Historical text may contain non-cp1252 characters; force UTF-8 on Windows.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):  # pragma: no cover
    pass

# Queries: a mix of plain-language and technical-term-heavy incidents, so the
# effect of the technical-overlap signal is visible.
QUERIES: list[str] = [
    "Kafka consumers stopped processing messages after a broker restart.",
    "NullPointerException when restarting a connector returns an empty response body.",
    "Consumer group keeps rebalancing repeatedly and never makes progress.",
    "Producer fails with TimeoutException related to max.poll.interval.ms configuration.",
    "Kafka Streams NullPointerException while restoring the state store from state.dir.",
    "SSL/TLS handshake fails between broker and client with certificate errors.",
]


def _short(text: str, width: int = 68) -> str:
    return textwrap.shorten(" ".join(str(text).split()), width=width, placeholder=" ...")


def main() -> int:
    print(
        f"Reranker weights: semantic={W_SEMANTIC}  technical={W_TECHNICAL}  "
        f"keyword={W_KEYWORD}   (FAISS fetch_k={DEFAULT_FETCH_K})\n"
    )

    for i, query in enumerate(QUERIES, start=1):
        print("#" * 96)
        print(f"QUERY {i}: {query}")
        print("#" * 96)

        baseline = retrieve_similar_incidents(query, top_k=5)
        reranked = two_stage_retrieve(query, fetch_k=DEFAULT_FETCH_K, final_k=5)

        print("\n  BASELINE  (FAISS Top-5, semantic only)")
        for inc in baseline:
            print(
                f"    #{inc.rank}  {inc.ticket_id:<12} sim={inc.similarity:.4f}  "
                f"{_short(inc.description)}"
            )

        print("\n  RERANKED  (two-stage Top-5)")
        for inc in reranked:
            terms = ", ".join(inc.matched_technical[:4]) if inc.matched_technical else "-"
            print(
                f"    #{inc.rank}  {inc.ticket_id:<12} score={inc.rerank_score:.4f}  "
                f"[sem={inc.similarity:.3f} tech={inc.technical_overlap:.2f} "
                f"kw={inc.keyword_overlap:.2f}]"
            )
            print(f"          matched technical terms: {terms}")

        base_ids = [inc.ticket_id for inc in baseline]
        rerank_ids = [inc.ticket_id for inc in reranked]
        if base_ids == rerank_ids:
            change = "unchanged"
        else:
            promoted = [t for t in rerank_ids if t not in base_ids]
            change = (
                f"order changed; newly promoted into Top-5: "
                f"{', '.join(promoted) if promoted else '(reordering only)'}"
            )
        print(f"\n  => {change}\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
