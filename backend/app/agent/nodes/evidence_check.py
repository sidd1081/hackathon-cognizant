"""evidence_check node: multi-dimensional evidence alignment gate.

No LLM. Similarity score alone is NOT sufficient to establish causal evidence.
The gate evaluates 5 dimensions of alignment between the query and each
retrieved evidence candidate:

    1. Component alignment  — same subsystem across the 8 Apache projects
       (consumer/broker, regionserver, namenode, taskmanager, znode, ...)?
    2. Symptom alignment    — similar observed symptoms (lag, error, crash, etc.)?
    3. Mechanism alignment  — similar technical cause (exception, config, etc.)?
    4. Trigger alignment    — similar triggering event (restart, rebalance, etc.)?
    5. Root cause quality   — does the evidence have a real, non-trivial root cause?

Evidence is considered sufficient only when at least one retrieved item is
"aligned":
    * similarity >= MIN_SIMILARITY (basic relevance floor; rejects
      out-of-domain queries), AND
    * the evidence has a documented, quality root cause to ground on, AND
    * either >= MIN_ALIGNED_DIMENSIONS alignment dimensions agree, OR the
      semantic match is strong on its own (similarity >= STRONG_SIMILARITY).

The corpus spans 8 Apache projects, so component alignment is one contributing
signal — NOT a hard, project-specific requirement (a single hard-coded
subsystem vocabulary cannot gate every project's incidents). Topical alignment
is instead established by the combination of similarity, multi-dimensional
overlap, and a real root cause.

Otherwise the workflow routes to the fallback — the LLM is never called.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.agent.state import RCAState
from app.core.logger import get_logger
from app.models.schemas import NOT_DOCUMENTED

logger = get_logger(__name__)

# --- Thresholds ---------------------------------------------------------------
# Basic relevance floor. Anything below this is treated as out-of-domain and the
# workflow abstains without calling the LLM. Calibrated so genuinely unrelated
# queries (e.g. a leaking coffee machine ~0.26) are rejected while true matches
# across all 8 projects (>= ~0.65) pass.
MIN_SIMILARITY = 0.45
# A semantic match this strong is, on its own, enough topical alignment even if
# the lexical overlap dimensions happen to be sparse (e.g. a well-paraphrased
# query that shares few exact tokens with the historical description).
STRONG_SIMILARITY = 0.60
MIN_ALIGNED_DIMENSIONS = 2

# --- Term dictionaries --------------------------------------------------------
# Component/subsystem terms across the 8 Apache projects in the corpus (Kafka,
# Flink, Spark, HBase, Cassandra, Solr, Hadoop, ZooKeeper). This is one
# contributing alignment signal, not a hard gate, so broad coverage is safe.
COMPONENT_TERMS: frozenset[str] = frozenset({
    # Kafka
    "consumer", "producer", "broker", "connector", "connect",
    "streams", "stream", "partition", "topic", "replica",
    "controller", "kraft", "raft",
    "offset", "rebalance", "coordinator",
    "fetcher", "sender", "interceptor", "serializer", "deserializer",
    "adminclient",
    # Flink
    "flink", "jobmanager", "taskmanager", "checkpoint", "savepoint",
    "watermark", "operator", "akka", "entrypoint", "slot",
    # Spark
    "spark", "executor", "driver", "rdd", "dataframe", "dataset",
    "shuffle", "catalyst", "stage", "yarn",
    # HBase
    "hbase", "regionserver", "region", "hfile", "wal", "memstore",
    "compaction", "mutator", "master",
    # Cassandra
    "cassandra", "gossip", "sstable", "memtable", "keyspace",
    "tombstone", "repair", "ring", "node",
    # Solr
    "solr", "core", "collection", "shard", "index", "query", "luke",
    # Hadoop / HDFS / YARN
    "hadoop", "hdfs", "namenode", "datanode", "mapreduce",
    "resourcemanager", "nodemanager", "jetty",
    # ZooKeeper
    "zookeeper", "znode", "quorum", "ensemble", "leader", "follower",
    "watcher", "session", "election",
    # cross-cutting subsystems
    "group", "admin", "server", "client", "thread",
})

# Symptom terms: what the user observes.
SYMPTOM_TERMS: frozenset[str] = frozenset({
    "stop", "stopped", "fail", "failed", "failure", "failing",
    "error", "exception", "crash", "crashed", "hang", "hanging", "hung",
    "timeout", "lag", "lagging", "slow", "stuck", "unresponsive",
    "unavailable", "unreachable", "down", "offline",
    "rejected", "refused", "denied", "dropped",
    "corrupt", "corrupted", "lost", "missing", "empty",
    "null", "npe", "nullpointerexception",
    "oom", "outofmemory", "leak", "leaking",
    "broken", "flaky", "inconsistent", "mismatch",
    "increasing", "growing", "accumulating",
    "500", "503", "404", "200",
})

# Trigger terms: events that cause the issue.
TRIGGER_TERMS: frozenset[str] = frozenset({
    "restart", "restarted", "restarting",
    "rebalance", "rebalancing",
    "upgrade", "upgraded", "upgrading", "update", "updated",
    "reassign", "reassignment", "reassigning",
    "recover", "recovery", "recovering",
    "shutdown", "failover", "rollback",
    "deploy", "deployment", "redeploy",
    "scale", "scaling", "resize",
    "config", "configuration", "reconfigure",
    "migrate", "migration",
})

# Technical mechanism terms: exception/error names, patterns.
_TECH_PATTERNS = (
    re.compile(r"\b\w+(?:\.\w+)+\b"),           # dotted identifiers
    re.compile(r"\b\w*_\w+\b"),                  # snake_case
    re.compile(r"\b[A-Za-z]*[a-z][A-Z]\w*\b"),   # camelCase/PascalCase
    re.compile(r"\b[A-Z]{2,}\b"),                # ALL-CAPS acronyms
)

_WORD = re.compile(r"[A-Za-z0-9]+")


# --- Helpers ------------------------------------------------------------------

def _extract_words(text: str) -> set[str]:
    """Extract lowercased words from text."""
    return {m.lower() for m in _WORD.findall(text)}


def _extract_technical(text: str) -> set[str]:
    """Extract lowercased technical terms from text."""
    terms: set[str] = set()
    for pattern in _TECH_PATTERNS:
        for match in pattern.findall(text):
            if len(match) > 1:
                terms.add(match.lower())
    return terms


def _overlap(query_terms: set[str], candidate_terms: set[str]) -> float:
    """Fraction of query terms found in the candidate."""
    if not query_terms:
        return 0.0
    return len(query_terms & candidate_terms) / len(query_terms)


@dataclass
class AlignmentScore:
    """Multi-dimensional alignment between query and one evidence item."""
    ticket_id: str
    similarity: float
    component: float
    symptom: float
    mechanism: float
    trigger: float
    root_cause_quality: float

    @property
    def active_dimensions(self) -> int:
        """Count of dimensions with score > 0."""
        return sum(1 for s in (
            self.component, self.symptom, self.mechanism,
            self.trigger, self.root_cause_quality,
        ) if s > 0)

    @property
    def is_aligned(self) -> bool:
        """Check project-agnostic multi-dimensional alignment.

        Requires basic relevance and a documented, quality root cause to ground
        on, then accepts either multi-signal agreement (>= MIN_ALIGNED_DIMENSIONS
        dimensions active) OR a strong standalone semantic match. Component is
        one of the counted dimensions, not a hard, project-specific requirement.
        """
        if self.similarity < MIN_SIMILARITY:
            return False
        if self.root_cause_quality <= 0:
            return False
        return (
            self.active_dimensions >= MIN_ALIGNED_DIMENSIONS
            or self.similarity >= STRONG_SIMILARITY
        )


def _root_cause_quality(root_cause: str, description: str) -> float:
    """Score the quality of a root cause field.

    Returns 0.0 if:
    - root cause is the sentinel
    - root cause is empty
    - root cause is just the description repeated (no real analysis)
    - root cause is too short (< 20 chars) to be a real technical explanation

    Returns 1.0 for a substantive, distinct root cause.
    Returns 0.5 for a short but non-trivial root cause.
    """
    rc = root_cause.strip()
    if not rc or rc == NOT_DOCUMENTED:
        return 0.0

    # If root_cause is essentially the description repeated, it's not useful.
    desc_stripped = description.strip()
    if rc == desc_stripped:
        return 0.0
    # Check if root cause is just the first sentence of the description.
    first_sentence = desc_stripped.split(".")[0].strip() + "."
    if rc == first_sentence or rc.rstrip(".") == first_sentence.rstrip("."):
        return 0.0

    # Very short root causes are probably not real technical explanations.
    if len(rc) < 20:
        return 0.3
    if len(rc) < 50:
        return 0.5
    return 1.0


def _score_alignment(
    query_words: set[str],
    query_technical: set[str],
    query_components: set[str],
    query_symptoms: set[str],
    query_triggers: set[str],
    candidate,
) -> AlignmentScore:
    """Compute alignment between the query and one evidence candidate."""
    desc = candidate.description or ""
    desc_words = _extract_words(desc)
    desc_technical = _extract_technical(desc)

    # Component alignment: what fraction of query components appear in evidence?
    desc_components = desc_words & COMPONENT_TERMS
    component = _overlap(query_components, desc_components)

    # Symptom alignment
    desc_symptoms = desc_words & SYMPTOM_TERMS
    symptom = _overlap(query_symptoms, desc_symptoms)

    # Mechanism alignment: shared technical terms (exception names, configs, etc.)
    mechanism = _overlap(query_technical, desc_technical)

    # Trigger alignment
    desc_triggers = desc_words & TRIGGER_TERMS
    trigger = _overlap(query_triggers, desc_triggers)

    # Root cause quality
    rc_quality = _root_cause_quality(
        candidate.root_cause or "", candidate.description or ""
    )

    return AlignmentScore(
        ticket_id=candidate.ticket_id,
        similarity=float(candidate.similarity) if candidate.similarity is not None else 0.0,
        component=component,
        symptom=symptom,
        mechanism=mechanism,
        trigger=trigger,
        root_cause_quality=rc_quality,
    )


# --- Main node ----------------------------------------------------------------

def evidence_check_node(state: RCAState) -> dict:
    evidence = state.get("evidence", [])

    if not evidence:
        reason = "No historical incidents were retrieved."
        logger.info("evidence_check: insufficient (%s)", reason)
        return {"evidence_sufficient": False, "evidence_reason": reason}

    # Extract query dimensions once.
    query = state.get("normalized_incident", "")
    query_words = _extract_words(query)
    query_technical = _extract_technical(query)
    query_components = query_words & COMPONENT_TERMS
    query_symptoms = query_words & SYMPTOM_TERMS
    query_triggers = query_words & TRIGGER_TERMS

    top_similarity = max(
        (item.similarity if item.similarity is not None else 0.0)
        for item in evidence
    )

    # Quick exit: if similarity is below threshold, nothing can align.
    if top_similarity < MIN_SIMILARITY:
        reason = (
            f"Top similarity {top_similarity:.3f} < {MIN_SIMILARITY}; "
            "no sufficiently similar historical incident."
        )
        logger.info("evidence_check: insufficient (%s)", reason)
        return {"evidence_sufficient": False, "evidence_reason": reason}

    # Score each evidence item across all dimensions.
    scores: list[AlignmentScore] = []
    for item in evidence:
        score = _score_alignment(
            query_words, query_technical, query_components,
            query_symptoms, query_triggers, item,
        )
        scores.append(score)
        logger.debug(
            "evidence_check alignment %s: component=%.2f symptom=%.2f "
            "mechanism=%.2f trigger=%.2f rc_quality=%.2f dims=%d aligned=%s",
            score.ticket_id, score.component, score.symptom,
            score.mechanism, score.trigger, score.root_cause_quality,
            score.active_dimensions, score.is_aligned,
        )

    aligned = [s for s in scores if s.is_aligned]

    if aligned:
        best = max(aligned, key=lambda s: s.similarity)
        reason = (
            f"{len(aligned)} evidence item(s) are aligned. "
            f"Best: {best.ticket_id} (similarity={best.similarity:.3f}, "
            f"component={best.component:.2f}, symptom={best.symptom:.2f}, "
            f"mechanism={best.mechanism:.2f}, trigger={best.trigger:.2f}, "
            f"rc_quality={best.root_cause_quality:.1f}, "
            f"dims={best.active_dimensions})."
        )
        logger.info("evidence_check: sufficient (%s)", reason)
        return {"evidence_sufficient": True, "evidence_reason": reason}

    # Build an explanatory reason for why alignment failed.
    best_score = max(scores, key=lambda s: s.similarity)
    issues: list[str] = []

    has_quality_rc = any(s.root_cause_quality > 0 for s in scores)
    if not has_quality_rc:
        issues.append("no evidence has a documented, quality root cause")
    if (
        best_score.active_dimensions < MIN_ALIGNED_DIMENSIONS
        and best_score.similarity < STRONG_SIMILARITY
    ):
        issues.append(
            f"only {best_score.active_dimensions} alignment dimension(s) active "
            f"(need >= {MIN_ALIGNED_DIMENSIONS}) and similarity "
            f"{best_score.similarity:.3f} < {STRONG_SIMILARITY} (not a strong "
            "standalone match)"
        )
    if not issues:
        issues.append("no evidence item met the combined alignment criteria")

    reason = (
        f"Similarity {top_similarity:.3f} >= {MIN_SIMILARITY} but evidence "
        f"alignment is insufficient: {'; '.join(issues)}. "
        f"Causal mechanism does not match the reported incident."
    )
    logger.info("evidence_check: insufficient (%s)", reason)
    return {"evidence_sufficient": False, "evidence_reason": reason}
