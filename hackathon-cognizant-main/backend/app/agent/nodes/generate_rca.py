"""generate_rca node: the single LLM step.

Reuses the Groq service (``app.rag.llm.generate_rca``); the prompt/guardrails
live there, not here. Only reached when evidence_check deemed evidence sufficient.
"""

from __future__ import annotations

from app.agent.state import RCAState
from app.core.logger import get_logger
from app.rag.llm import generate_rca

logger = get_logger(__name__)


def generate_rca_node(state: RCAState) -> dict:
    incident = state["normalized_incident"]
    evidence = state.get("evidence", [])
    rca = generate_rca(incident, evidence)
    logger.info("generate_rca: confidence=%s", rca.confidence)
    return {"rca": rca}
