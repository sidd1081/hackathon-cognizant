"""Pydantic schemas for the RCA assistant.

``RCAResponse`` is the structured output the Groq LLM must return. Field
descriptions double as instructions to the model when used with LangChain's
``with_structured_output``. The ``Analyze*`` models are the public HTTP
request/response contract for the FastAPI endpoint.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

# The exact string that must be emitted when a technical root cause cannot be
# established from the evidence.
NOT_DOCUMENTED = "Not explicitly documented."

ConfidenceLevel = Literal["low", "medium", "high"]


class RCAResponse(BaseModel):
    """Structured root-cause-analysis result grounded in retrieved evidence."""

    root_cause: str = Field(
        description=(
            "The single most likely TECHNICAL root cause, supported ONLY by the "
            "provided evidence. If the evidence does not clearly establish a "
            "technical root cause, this MUST be exactly 'Not explicitly "
            "documented.' and nothing else."
        )
    )
    resolution: str = Field(
        description=(
            "A recommended resolution grounded in the historical resolutions in "
            "the evidence. If no resolution can be supported by the evidence, "
            "this MUST be exactly 'Not explicitly documented.'"
        )
    )
    summary: str = Field(
        description=(
            "A concise (2-4 sentence) root-cause-analysis summary written for a "
            "support engineer. Do not introduce facts absent from the evidence."
        )
    )
    supporting_ticket_ids: list[str] = Field(
        default_factory=list,
        description=(
            "Ticket IDs of the historical incidents actually relied upon to reach "
            "this conclusion. Empty list if none were sufficient."
        ),
    )
    confidence: ConfidenceLevel = Field(
        description=(
            "How well the evidence supports the conclusion: 'low', 'medium', or "
            "'high'. High similarity alone is NOT high confidence."
        )
    )


# --- HTTP API contract -------------------------------------------------------

# Confidence as presented in the API response (title-cased).
ApiConfidence = Literal["Low", "Medium", "High"]


class AnalyzeRequest(BaseModel):
    """Request body for POST /api/incidents/analyze."""

    description: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=10000)
    ] = Field(description="The newly reported incident, in free text.")


class SimilarIncident(BaseModel):
    """A historical incident surfaced during retrieval, with retrieval metadata."""

    ticket_id: str
    similarity: float | None = Field(
        default=None,
        description="FAISS cosine similarity (null for BM25-only hits).",
    )
    description: str
    root_cause: str
    resolution: str

    # ── Hybrid retrieval metadata ────────────────────────────────────────────
    match_type: str = Field(
        default="semantic",
        description="How this result was found: 'semantic', 'keyword', or 'semantic+keyword'.",
    )
    hybrid_rank: int = Field(
        default=0,
        description="Final position after RRF fusion (1-based).",
    )
    bm25_score: float | None = Field(
        default=None,
        description="BM25 score (null if not retrieved by BM25).",
    )
    rrf_score: float | None = Field(
        default=None,
        description="Reciprocal Rank Fusion score.",
    )
    faiss_rank: int | None = Field(
        default=None,
        description="Rank from FAISS semantic search (null if BM25-only).",
    )
    bm25_rank: int | None = Field(
        default=None,
        description="Rank from BM25 keyword search (null if FAISS-only).",
    )


class AnalyzeResponse(BaseModel):
    """Response body for POST /api/incidents/analyze."""

    summary: str
    root_cause: str
    resolution: str
    confidence: ApiConfidence
    similar_incidents: list[SimilarIncident] = Field(
        default_factory=list,
        description="All historical incidents retrieved as evidence (reranked Top-K).",
    )
    supporting_incidents: list[SimilarIncident] = Field(
        default_factory=list,
        description="The subset of similar incidents the RCA actually relied upon.",
    )


class DatasetUploadResponse(BaseModel):
    """Response body for POST /api/dataset/upload."""

    status: str = Field(description="Overall processing status, e.g. 'success'.")
    message: str
    records: int = Field(description="Number of incident records indexed.")
    duplicates_removed: int = Field(
        default=0, description="Rows dropped as duplicates during cleaning."
    )
    embedding_dimension: int = Field(description="Dimension of the stored vectors.")
    index_status: str = Field(description="State of the FAISS index, e.g. 'ready'.")


class EvaluationResponse(BaseModel):
    """Headline metrics from the latest offline evaluation run.

    Sourced from ``evaluation/results.json`` (produced by
    ``scripts/evaluate.py``). All metric fields are optional so a partial or
    older results file still renders on the dashboard.
    """

    generated_at: str | None = Field(
        default=None, description="ISO timestamp of the evaluation run."
    )
    num_cases: int = Field(default=0, description="Number of evaluated cases.")
    embedding_model: str | None = None
    groq_model: str | None = None
    top_k: int | None = None

    # Retrieval quality
    recall_at_5: float | None = None
    precision_at_5: float | None = None
    mrr: float | None = None

    # RCA quality
    root_cause_correctness: float | None = None
    mean_root_cause_alignment: float | None = None
    resolution_relevance: float | None = None
    evidence_support_rate: float | None = None
    hallucination_rate: float | None = None
    abstention_correct_rate: float | None = None

    # Performance (steady-state means, milliseconds)
    embedding_latency_ms: float | None = None
    retrieval_latency_ms: float | None = None
    total_rca_latency_ms: float | None = None


# --- Auth ---------------------------------------------------------------------

# A pragmatic email constraint (avoids the extra email-validator dependency):
# trimmed, lowercased at the service layer, must contain one "@" with text on
# both sides. Full RFC validation is unnecessary for this app.
Email = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=3, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
    ),
]
Password = Annotated[str, StringConstraints(min_length=8, max_length=128)]
Name = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)
]


class SignupRequest(BaseModel):
    """Request body for POST /api/auth/signup."""

    name: Name = Field(description="Display name.")
    email: Email = Field(description="Login email (case-insensitive).")
    password: Password = Field(description="At least 8 characters.")


class LoginRequest(BaseModel):
    """Request body for POST /api/auth/login."""

    email: Email
    password: Annotated[str, StringConstraints(min_length=1, max_length=128)]


class UserOut(BaseModel):
    """Public representation of a user (never includes the password hash)."""

    id: int
    name: str
    email: str


class AuthResponse(BaseModel):
    """Response body for signup/login: a bearer token plus the user."""

    access_token: str
    token_type: str = "bearer"
    user: UserOut
