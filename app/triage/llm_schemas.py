"""Contracts with the LLM (architecture.md §5.3) plus the workflow's result type.

`Field(description=...)` text is sent to the model as part of the JSON schema,
so it is effectively part of the prompt.
"""

from typing import Literal

from pydantic import BaseModel, Field

# Allowed dependency: triage → kb. One definition of a retrieved chunk.
from app.kb.schemas import SearchHit as RetrievedChunk

Category = Literal["billing", "technical", "account", "shipping", "other"]
Priority = Literal["low", "medium", "high", "urgent"]
Sentiment = Literal["positive", "neutral", "negative"]
TriageStatus = Literal["auto_ready", "needs_review"]


class Classification(BaseModel):
    """Output of step 1 (FR-8). Enums are enforced by the `Literal` types."""

    category: Category
    priority: Priority
    sentiment: Sentiment
    summary: str = Field(max_length=200, description="One sentence summary of the issue")
    language: str = Field(description="ISO 639-1 code, e.g. 'en'")


class DraftReply(BaseModel):
    """Output of step 3 (FR-10)."""

    reply: str = Field(
        description="The complete message to send to the customer, written to them. "
        "No article ids or scores in it."
    )
    cited_article_ids: list[int] = Field(description="IDs of passages actually used")
    confidence: float = Field(
        ge=0.0, le=1.0, description="Decimal from 0.0 to 1.0: how fully the passages answer it"
    )
    missing_info: str | None = None


class TriageResult(BaseModel):
    """Everything one workflow run produced; persisted as a `triage_runs` row."""

    status: TriageStatus
    reasons: list[str] = Field(default_factory=list)
    classification: Classification | None = None
    draft: DraftReply | None = None
    retrieved: list[RetrievedChunk] = Field(default_factory=list)
    step_timings: dict[str, float] = Field(
        default_factory=dict, description="Milliseconds per step"
    )
    error: str | None = None


__all__ = [
    "Category",
    "Classification",
    "DraftReply",
    "Priority",
    "RetrievedChunk",
    "Sentiment",
    "TriageResult",
    "TriageStatus",
]
