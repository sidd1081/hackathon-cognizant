"""Independent test of the Groq RCA generation layer.

Usage (from the backend/ directory):

    uv run python -m scripts.test_llm

Requires GROQ_API_KEY in backend/.env and a built FAISS index
(`uv run python -m scripts.build_index`). Retrieves evidence with the two-stage
retriever, then asks Groq for a structured RCA.

Two cases are exercised:
  1. A real technical incident  -> expect a grounded RCA with supporting tickets.
  2. An unrelated incident       -> expect root_cause == "Not explicitly documented."
"""

from __future__ import annotations

import sys
import textwrap

from app.core.config import settings
from app.models.schemas import NOT_DOCUMENTED, RCAResponse
from app.rag.llm import generate_rca
from app.rag.reranker import two_stage_retrieve

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):  # pragma: no cover
    pass

CASES: list[tuple[str, str]] = [
    (
        "strong documented match (expect grounded RCA)",
        "Restarting a Kafka connector that has no tasks returns an empty HTTP "
        "response body, which causes a NullPointerException in the Connect REST "
        "client.",
    ),
    (
        "related but insufficient evidence (expect honest 'not documented')",
        "Kafka Streams application throws a NullPointerException while restoring "
        "its state store after a restart.",
    ),
    (
        "unrelated incident (guardrail)",
        "The office coffee machine is leaking water onto the break-room floor.",
    ),
]


def _short(text: str, width: int = 90) -> str:
    return textwrap.shorten(" ".join(str(text).split()), width=width, placeholder=" ...")


def _print_response(resp: RCAResponse) -> None:
    print(f"  confidence:            {resp.confidence}")
    print(f"  root_cause:            {resp.root_cause}")
    print(f"  resolution:            {_short(resp.resolution, 200)}")
    print(f"  supporting_ticket_ids: {resp.supporting_ticket_ids}")
    print(f"  summary:               {_short(resp.summary, 300)}")


def main() -> int:
    if not settings.groq_api_key:
        print("GROQ_API_KEY is not set. Add it to backend/.env and re-run:")
        print("  GROQ_API_KEY=your_key_here")
        return 1

    print(f"Groq model: {settings.groq_model} (temperature={settings.llm_temperature})\n")

    for label, incident in CASES:
        print("=" * 92)
        print(f"CASE: {label}")
        print(f"NEW INCIDENT: {incident}")
        print("=" * 92)

        evidence = two_stage_retrieve(incident, fetch_k=10, final_k=5)
        print("\n  Evidence (reranked Top-5):")
        for inc in evidence:
            print(
                f"    {inc.ticket_id:<12} sim={inc.similarity:.3f}  "
                f"{_short(inc.description, 70)}"
            )

        print("\n  --- Groq RCA ---")
        resp = generate_rca(incident, evidence)
        _print_response(resp)

        if "unrelated" in label:
            ok = resp.root_cause == NOT_DOCUMENTED
            print(
                f"\n  guardrail check (root_cause == '{NOT_DOCUMENTED}'): "
                f"{'PASS' if ok else 'FAIL'}"
            )
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
