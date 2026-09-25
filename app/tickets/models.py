"""Ticket ORM models: `Ticket` (current state) and `TriageRun` (history/audit).

The latest run's results are copied onto the ticket so the review queue needs
no join (architecture.md §6).
"""

from datetime import datetime
from typing import Any, get_args

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.tickets.schemas import TicketStatus
from app.triage.llm_schemas import Category, Priority

RUN_STATUSES = ("succeeded", "failed")


def _in_check(column: str, values: tuple[str, ...]) -> str:
    """Build a `col IN ('a', 'b')` CHECK expression (VARCHAR + CHECK, not PG enums)."""
    quoted = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({quoted})"


class Ticket(Base):
    """A customer support ticket and its latest triage result."""

    __tablename__ = "tickets"
    __table_args__ = (
        CheckConstraint(_in_check("status", get_args(TicketStatus)), name="status"),
        CheckConstraint(_in_check("category", get_args(Category)), name="category"),
        CheckConstraint(_in_check("priority", get_args(Priority)), name="priority"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_email: Mapped[str] = mapped_column(String(320))
    subject: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="pending", server_default="pending")

    # Copied from the latest triage run
    category: Mapped[str | None] = mapped_column(String(20), index=True)
    priority: Mapped[str | None] = mapped_column(String(20))
    sentiment: Mapped[str | None] = mapped_column(String(20))
    summary: Mapped[str | None] = mapped_column(Text)
    draft_reply: Mapped[str | None] = mapped_column(Text)
    cited_article_ids: Mapped[list[int]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )
    confidence: Mapped[float | None] = mapped_column(Float)
    review_reasons: Mapped[list[str]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )

    # Human review
    final_reply: Mapped[str | None] = mapped_column(Text)
    review_note: Mapped[str | None] = mapped_column(Text)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    runs: Mapped[list["TriageRun"]] = relationship(back_populates="ticket", order_by="TriageRun.id")


class TriageRun(Base):
    """One execution of the triage workflow (FR-14, F7)."""

    __tablename__ = "triage_runs"
    __table_args__ = (CheckConstraint(_in_check("status", RUN_STATUSES), name="status"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"), index=True)
    status: Mapped[str] = mapped_column(String(20))
    provider: Mapped[str] = mapped_column(String(20))
    chat_model: Mapped[str] = mapped_column(String(100))
    embedding_model: Mapped[str] = mapped_column(String(100))
    prompt_version: Mapped[str] = mapped_column(String(20))
    classification: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    retrieved: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )  # chunk ids + distances
    draft: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    step_timings: Mapped[dict[str, float]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )  # ms per step
    latency_ms: Mapped[int] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    ticket: Mapped[Ticket] = relationship(back_populates="runs")


# Review queue: WHERE status = ? ORDER BY created_at DESC
Index("ix_tickets_status_created_at", Ticket.status, Ticket.created_at.desc())
