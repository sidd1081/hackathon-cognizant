"""Run several incidents through the RCA LangGraph workflow.

Usage (from the backend/ directory):

    uv run python -m scripts.test_graph

Requires a built FAISS index and GROQ_API_KEY in backend/.env. Each incident is
run end-to-end through the graph; the final state (routing, evidence, RCA,
validation) is printed.
"""

from __future__ import annotations

import sys
import textwrap

from app.agent.graph import run_rca_graph
from app.core.config import settings

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):  # pragma: no cover
    pass

INCIDENTS: list[str] = [
    # Strong documented match -> should route to generate + validate.
    "Restarting a Kafka connector that has no tasks returns an empty HTTP "
    "response body, which causes a NullPointerException in the Connect REST client.",
    # Well-covered topic -> should route to generate.
    "Consumer group keeps rebalancing repeatedly and never makes progress.",
    # Unrelated -> evidence_check should route to fallback (no LLM call).
    "The office coffee machine is leaking water onto the break-room floor.",
]


def _short(text: str, width: int = 100) -> str:
    return textwrap.shorten(" ".join(str(text).split()), width=width, placeholder=" ...")


def main() -> int:
    if not settings.groq_api_key:
        print("GROQ_API_KEY is not set. Add it to backend/.env and re-run.")
        return 1

    for i, incident in enumerate(INCIDENTS, start=1):
        print("=" * 100)
        print(f"INCIDENT {i}: {incident}")
        print("=" * 100)

        state = run_rca_graph(incident)

        print(f"  status:              {state.get('status')}")
        print(f"  evidence_sufficient: {state.get('evidence_sufficient')}")
        print(f"  evidence_reason:     {state.get('evidence_reason')}")

        evidence = state.get("evidence", [])
        print(f"  evidence (Top-{len(evidence)}):")
        for inc in evidence:
            print(f"    {inc.ticket_id:<12} sim={inc.similarity:.3f} score={inc.rerank_score:.3f}")

        rca = state.get("rca")
        if rca is not None:
            print("  --- RCA ---")
            print(f"    confidence:            {rca.confidence}")
            print(f"    root_cause:            {_short(rca.root_cause, 160)}")
            print(f"    resolution:            {_short(rca.resolution, 160)}")
            print(f"    supporting_ticket_ids: {rca.supporting_ticket_ids}")
            print(f"    summary:               {_short(rca.summary, 240)}")

        validation = state.get("validation", {})
        print(f"  validation issues:   {validation.get('issues', [])}")
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
