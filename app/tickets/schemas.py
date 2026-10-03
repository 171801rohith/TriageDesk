"""Pydantic request/response models for the tickets API (requirements §5)."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from app.triage.llm_schemas import Classification

if TYPE_CHECKING:
    from app.tickets.models import Ticket

TicketStatus = Literal["pending", "auto_ready", "needs_review", "approved", "rejected"]
ReviewAction = Literal["approve", "edit", "reject"]
REVIEWABLE_STATUSES: frozenset[str] = frozenset({"auto_ready", "needs_review"})  # FR-18


class TicketIn(BaseModel):
    """Body of `POST /tickets` (F3)."""

    customer_email: EmailStr
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=10_000)


class RunSummary(BaseModel):
    """Compact view of the latest run embedded in `TicketOut.latest_run`."""

    id: int
    provider: str
    model: str
    latency_ms: int
    status: Literal["succeeded", "failed"]


class RunOut(BaseModel):
    """Full triage run for `GET /tickets/{id}/runs` (F7)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    ticket_id: int
    status: Literal["succeeded", "failed"]
    provider: str
    chat_model: str
    embedding_model: str
    prompt_version: str
    classification: dict[str, Any] | None
    retrieved: list[dict[str, Any]]
    draft: dict[str, Any] | None
    step_timings: dict[str, float]
    latency_ms: int
    error: str | None
    created_at: datetime


class TicketOut(BaseModel):
    """Ticket plus its latest triage result (shape of the requirements §5 example)."""

    id: int
    status: TicketStatus
    customer_email: EmailStr
    subject: str
    body: str
    classification: Classification | None = None
    draft_reply: str | None = None
    cited_article_ids: list[int] = Field(default_factory=list)
    confidence: float | None = None
    review_reasons: list[str] = Field(default_factory=list)
    final_reply: str | None = None
    review_note: str | None = None
    reviewed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    latest_run: RunSummary | None = None

    @classmethod
    def from_ticket(cls, ticket: Ticket) -> TicketOut:
        """Map the ORM ticket (flat columns + runs) to the nested API shape.

        `classification` comes from the latest run's stored JSON rather than the
        flat columns: it is the only place `language` is kept, and the flat
        columns are copies of that same run anyway (FR-15).
        """
        latest = ticket.runs[-1] if ticket.runs else None
        classification = (
            Classification.model_validate(latest.classification)
            if latest is not None and latest.classification is not None
            else None
        )
        latest_run = (
            RunSummary(
                id=latest.id,
                provider=latest.provider,
                model=latest.chat_model,
                latency_ms=latest.latency_ms,
                status=latest.status,
            )
            if latest is not None
            else None
        )
        return cls(
            id=ticket.id,
            status=ticket.status,
            customer_email=ticket.customer_email,
            subject=ticket.subject,
            body=ticket.body,
            classification=classification,
            draft_reply=ticket.draft_reply,
            cited_article_ids=ticket.cited_article_ids,
            confidence=ticket.confidence,
            review_reasons=ticket.review_reasons,
            final_reply=ticket.final_reply,
            review_note=ticket.review_note,
            reviewed_at=ticket.reviewed_at,
            created_at=ticket.created_at,
            updated_at=ticket.updated_at,
            latest_run=latest_run,
        )


class ReviewIn(BaseModel):
    """Body of `POST /tickets/{id}/review` (FR-17)."""

    action: ReviewAction
    final_reply: str | None = None
    note: str | None = None

    @model_validator(mode="after")
    def _edit_requires_final_reply(self) -> ReviewIn:
        """`edit` must carry a non-empty `final_reply` (FR-17) — otherwise 422."""
        if self.action == "edit" and not (self.final_reply and self.final_reply.strip()):
            raise ValueError("final_reply is required when action is 'edit'")
        return self


class ProviderStats(BaseModel):
    """Per-provider aggregate over `triage_runs`."""

    runs: int
    avg_latency_ms: float | None


class StatsOut(BaseModel):
    """Response of `GET /stats` (F9)."""

    by_status: dict[str, int]
    by_category: dict[str, int]
    by_provider: dict[str, ProviderStats]
