"""Lightweight, explainable reranking for two-stage retrieval.

    New incident  ->  FAISS Top 10  ->  rerank  ->  final Top 5

FAISS gives a strong *semantic* candidate set, but pure cosine similarity can
miss that two incidents share the exact same exception name, config key, or
class. The reranker nudges the ordering using three transparent signals, all in
``[0, 1]`` and combined with fixed, visible weights (no LLM, no hidden model):

    rerank_score = W_SEMANTIC   * semantic          (FAISS cosine)
                 + W_TECHNICAL  * technical_overlap  (shared technical terms)
                 + W_KEYWORD    * keyword_overlap    (shared content words)

"overlap" is *query coverage*: the fraction of the query's terms that also
appear in the candidate incident. It is intuitive to explain to a judge:
"80% of the query's technical terms show up in this incident."
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from app.core.logger import get_logger
from app.rag.retriever import RetrievedIncident, retrieve_similar_incidents

logger = get_logger(__name__)

# --- Tunable, visible weights (sum to 1.0) -----------------------------------
# Semantic is the PRIMARY signal (the embedding already handles synonyms, e.g.
# "NPE" ~ "NullPointerException"), so it dominates and the reranker refines
# rather than overturns FAISS. Technical-term and keyword overlaps are equal,
# smaller precision boosts (<=15% each) — enough to promote incidents that
# share an exact exception name or config key, but not enough for a single
# lexical hit to dethrone a clearly stronger semantic match.
W_SEMANTIC = 0.70
W_TECHNICAL = 0.15
W_KEYWORD = 0.15

# Two-stage defaults: fetch a wider net from FAISS, then keep the best few.
# With per-field truncation in the prompt (see app/rag/prompts.py), five
# incidents assemble to ~2.8k tokens — comfortably within the Groq free-tier
# 8k tokens/request budget. Truncation, not the incident count, is what keeps
# the request small even when historical descriptions are multi-KB stack traces.
DEFAULT_FETCH_K = 10
DEFAULT_FINAL_K = 5

# --- Tokenization -------------------------------------------------------------
_WORD = re.compile(r"[A-Za-z0-9]+")

# Technical-looking tokens: dotted identifiers, snake_case, camelCase/PascalCase,
# and ALL-CAPS acronyms. These are the high-signal terms in incident text.
_TECH_PATTERNS = (
    re.compile(r"\b\w+(?:\.\w+)+\b"),           # org.apache.kafka, RestClient.java, max.poll.interval.ms
    re.compile(r"\b\w*_\w+\b"),                 # __consumer_offsets, state_dir
    re.compile(r"\b[A-Za-z]*[a-z][A-Z]\w*\b"),  # NullPointerException, InterBrokerSendThread
    re.compile(r"\b[A-Z]{2,}\b"),               # SSL, TLS, NPE, RPC, KIP
)

# Small, generic English stopword set (kept short and readable on purpose).
_STOPWORDS = frozenset(
    """
    a an and are as at be by for from has have in into is it its of on or that
    the to was were will with when after before during while not no does do did
    this these those there their they them then than which who whom what why how
    can could should would may might must been being about over under again more
    most some such only own same so up out if but because we you your our i me my
    """.split()
)


def _keyword_tokens(text: str) -> set[str]:
    """Lowercase content words (stopwords and very short tokens removed)."""
    tokens = set()
    for match in _WORD.findall(text):
        low = match.lower()
        if len(low) > 2 and low not in _STOPWORDS:
            tokens.add(low)
    return tokens


def technical_terms(text: str) -> set[str]:
    """Extract lowercased technical terms (identifiers, acronyms, etc.)."""
    terms: set[str] = set()
    for pattern in _TECH_PATTERNS:
        for match in pattern.findall(text):
            if len(match) > 1:
                terms.add(match.lower())
    return terms


def _coverage(query_terms: set[str], candidate_terms: set[str]) -> float:
    """Fraction of query terms found in the candidate (0.0 if query is empty)."""
    if not query_terms:
        return 0.0
    return len(query_terms & candidate_terms) / len(query_terms)


@dataclass
class RerankedIncident:
    """A reranked hit, carrying the composite score and its explainable parts.

    Retrieval metadata from the hybrid retriever (``bm25_score``,
    ``rrf_score``, ``faiss_rank``, ``bm25_rank``, ``match_type``,
    ``hybrid_rank``) is preserved verbatim — the reranker never overwrites
    or recalculates these upstream scores.
    """

    rank: int
    ticket_id: str
    project: str
    summary: str
    description: str
    root_cause: str
    resolution_status: str
    resolution_notes: str
    similarity: float | None   # original FAISS cosine (None for BM25-only)
    keyword_overlap: float
    technical_overlap: float
    rerank_score: float        # final weighted blend
    matched_technical: list[str]

    # ── Preserved hybrid retrieval metadata ──────────────────────────────────
    bm25_score: float | None = None
    rrf_score: float | None = None
    faiss_rank: int | None = None
    bm25_rank: int | None = None
    match_type: str = "semantic"
    hybrid_rank: int = 0

    @property
    def resolution(self) -> str:
        """Compatibility alias for technical resolution evidence only."""
        return self.resolution_notes

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["resolution"] = self.resolution_notes
        return payload


def _candidate_text(incident: RetrievedIncident) -> str:
    """Return the text used for term matching during reranking.

    Only the incident description is used for lexical overlap. Root cause and
    technical-resolution notes are metadata returned after retrieval, not
    signals for ranking.
    """
    return incident.description


def rerank(
    query: str,
    candidates: list[RetrievedIncident],
    top_k: int = DEFAULT_FINAL_K,
) -> list[RerankedIncident]:
    """Rerank FAISS candidates with the semantic + technical + keyword blend."""
    if top_k <= 0:
        raise ValueError(f"top_k must be positive, got {top_k}")

    query_keywords = _keyword_tokens(query)
    query_technical = technical_terms(query)

    reranked: list[RerankedIncident] = []
    for cand in candidates:
        text = _candidate_text(cand)
        cand_keywords = _keyword_tokens(text)
        cand_technical = technical_terms(text)

        keyword_overlap = _coverage(query_keywords, cand_keywords)
        technical_overlap = _coverage(query_technical, cand_technical)
        semantic = float(cand.similarity) if cand.similarity is not None else 0.0

        score = (
            W_SEMANTIC * semantic
            + W_TECHNICAL * technical_overlap
            + W_KEYWORD * keyword_overlap
        )

        reranked.append(
            RerankedIncident(
                rank=0,  # assigned after sorting
                ticket_id=cand.ticket_id,
                project=cand.project,
                summary=cand.summary,
                description=cand.description,
                root_cause=cand.root_cause,
                resolution_status=cand.resolution_status,
                resolution_notes=cand.resolution_notes,
                similarity=cand.similarity,  # preserve None for BM25-only
                keyword_overlap=keyword_overlap,
                technical_overlap=technical_overlap,
                rerank_score=score,
                matched_technical=sorted(query_technical & cand_technical),
                # Pass through retrieval metadata verbatim
                bm25_score=cand.bm25_score,
                rrf_score=cand.rrf_score,
                faiss_rank=cand.faiss_rank,
                bm25_rank=cand.bm25_rank,
                match_type=cand.match_type,
                hybrid_rank=cand.hybrid_rank,
            )
        )

    # Sort by composite score (desc); ties broken by original FAISS similarity.
    reranked.sort(
        key=lambda r: (r.rerank_score, r.similarity if r.similarity is not None else 0.0),
        reverse=True,
    )
    top = reranked[:top_k]
    for new_rank, item in enumerate(top, start=1):
        item.rank = new_rank
    return top


def two_stage_retrieve(
    query: str,
    fetch_k: int = DEFAULT_FETCH_K,
    final_k: int = DEFAULT_FINAL_K,
) -> list[RerankedIncident]:
    """Full two-stage retrieval: FAISS Top-``fetch_k`` then rerank to ``final_k``."""
    if fetch_k < final_k:
        raise ValueError(
            f"fetch_k ({fetch_k}) must be >= final_k ({final_k})."
        )
    candidates = retrieve_similar_incidents(query, top_k=fetch_k)
    result = rerank(query, candidates, top_k=final_k)
    logger.info(
        "Two-stage retrieval: %d FAISS candidates -> %d reranked",
        len(candidates),
        len(result),
    )
    return result
