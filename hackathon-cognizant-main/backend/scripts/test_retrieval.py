"""Full pipeline test for the RCA system.

Usage (from the backend/ directory):

    uv run python -m scripts.test_retrieval

Runs 4 test queries through the complete pipeline:
    analyze -> retrieve -> rerank -> evidence_check -> generate/fallback -> validate

Reports for each test:
    * Top 5 evidence (ticket_id, similarity, description)
    * Evidence decision (sufficient/insufficient + reason)
    * RCA generated or fallback
    * root_cause, resolution, confidence, supporting_ticket_ids
"""

from __future__ import annotations

import sys
import textwrap

from app.agent.graph import run_rca_graph

# Force UTF-8 output so printing never crashes on Windows.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

# The 4 required test queries.
QUERIES: list[str] = [
    # TEST 1: consumer lag after broker restart — should NOT generate unsupported RCA
    "Kafka consumers stop processing messages after a broker restart and "
    "consumer lag continues increasing.",
    # TEST 2: connector restart NPE + empty response — should match KAFKA-13139
    "After restarting a Kafka connector without restarting its tasks, the REST "
    "API returns HTTP 200 with an empty response body and the client throws a "
    "NullPointerException.",
    # TEST 3: under-replicated partitions after broker failure
    "Several Kafka partitions are under-replicated after a broker failure and "
    "replicas are not catching up after the broker recovers.",
    # TEST 4: completely unrelated payroll query — should fallback immediately
    "The payroll application cannot generate PDF salary slips.",
]

_WRAP = 120
_SEP = "=" * 120
_SUB = "-" * 80


def _short(text: str, width: int = _WRAP) -> str:
    collapsed = " ".join(str(text).split())
    return textwrap.shorten(collapsed, width=width, placeholder=" ...")


def main() -> int:
    for q_index, query in enumerate(QUERIES, start=1):
        print(f"\n{_SEP}")
        print(f"TEST {q_index}: {query}")
        print(_SEP)

        state = run_rca_graph(query)

        # --- Top 5 evidence ---
        evidence = state.get("evidence", [])
        print(f"\n  Top {len(evidence)} Evidence:")
        if not evidence:
            print("    (none)")
        else:
            for inc in evidence:
                print(
                    f"    #{inc.rank}  {inc.ticket_id}  "
                    f"similarity={inc.similarity:.4f}  "
                    f"rerank={inc.rerank_score:.4f}"
                )
                print(f"        desc: {_short(inc.description)}")

        # --- Evidence decision ---
        print(f"\n  {_SUB}")
        sufficient = state.get("evidence_sufficient", False)
        reason = state.get("evidence_reason", "")
        decision = "SUFFICIENT" if sufficient else "INSUFFICIENT"
        print(f"  Evidence Decision: {decision}")
        print(f"  Reason: {reason}")

        # --- RCA output ---
        print(f"\n  {_SUB}")
        status = state.get("status", "unknown")
        rca = state.get("rca")
        if status == "insufficient_evidence":
            print("  RCA: FALLBACK (insufficient evidence)")
        else:
            print("  RCA: GENERATED")

        if rca:
            print(f"  Root Cause:    {_short(rca.root_cause)}")
            print(f"  Resolution:    {_short(rca.resolution)}")
            print(f"  Confidence:    {rca.confidence}")
            print(f"  Supporting:    {rca.supporting_ticket_ids}")
            print(f"  Summary:       {_short(rca.summary)}")

        # --- Validation ---
        validation = state.get("validation", {})
        if validation:
            print(f"\n  {_SUB}")
            print(f"  Validation:")
            print(f"    mechanism_valid:       {validation.get('mechanism_valid', 'N/A')}")
            print(f"    root_cause_documented: {validation.get('root_cause_documented', 'N/A')}")
            print(f"    removed_citations:     {validation.get('removed_citations', [])}")
            issues = validation.get("issues", [])
            if issues:
                print(f"    issues ({len(issues)}):")
                for issue in issues:
                    print(f"      - {issue}")
            else:
                print("    issues: none")

        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
