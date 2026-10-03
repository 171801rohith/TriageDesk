"""Tickets service: creation + triage, re-triage, review, listing and stats.

Owns the ticket lifecycle (architecture.md §4.3). Calls the workflow but knows
nothing about LLM providers. Raises `NotFound` / `Conflict`, never `HTTPException`.
"""

import time
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.exceptions import Conflict, NotFound
from app.llm.providers import active_model_info
from app.tickets.models import Ticket, TriageRun
from app.tickets.schemas import (
    REVIEWABLE_STATUSES,
    ProviderStats,
    ReviewIn,
    StatsOut,
    TicketIn,
    TicketStatus,
)
from app.triage.prompts import PROMPT_VERSION
from app.triage.workflow import TriageWorkflow

# auto_ready/needs_review → pending (architecture §4.3); `pending` too, to rescue a
# ticket stuck after a crash mid-triage. approved/rejected are final.
RETRIAGEABLE_STATUSES: frozenset[str] = REVIEWABLE_STATUSES | {"pending"}


def create_ticket(db: Session, data: TicketIn, workflow: TriageWorkflow) -> Ticket:
    """Persist a `pending` ticket, run triage synchronously, commit (FR-7).

    The ticket is *committed* before triage, not just flushed: a crash mid-triage
    leaves it saved as `pending` (re-runnable), and no transaction stays open
    across the slow LLM calls.
    """
    ticket = Ticket(
        customer_email=data.customer_email,
        subject=data.subject,
        body=data.body,
        status="pending",
    )
    db.add(ticket)
    db.commit()

    _apply_triage(db, ticket, workflow)
    db.commit()
    db.refresh(ticket)  # load server-side values (created_at, updated_at)
    return ticket


def retriage(db: Session, ticket_id: int, workflow: TriageWorkflow) -> Ticket:
    """Re-run the workflow on an existing ticket, creating a new run (FR-15).

    Raises:
        NotFound: if the ticket does not exist.
        Conflict: if the ticket was already approved or rejected.
    """
    ticket = get_ticket(db, ticket_id)
    if ticket.status not in RETRIAGEABLE_STATUSES:
        raise Conflict(f"Ticket {ticket_id} cannot be re-triaged in status '{ticket.status}'")

    ticket.status = "pending"
    db.commit()

    _apply_triage(db, ticket, workflow)
    db.commit()
    db.refresh(ticket)
    return ticket


def _apply_triage(db: Session, ticket: Ticket, workflow: TriageWorkflow) -> TriageRun:
    """Run the workflow, store a `TriageRun`, copy latest results onto the ticket.

    Shared by `create_ticket` and `retriage`. Does not commit — the caller does.
    Every field is overwritten, including with None, so the ticket always shows
    exactly the latest run (FR-15) and never a mix of old and new results.
    """
    start = time.perf_counter()
    result = workflow.run(ticket.subject, ticket.body)
    latency_ms = round((time.perf_counter() - start) * 1000)

    classification, draft = result.classification, result.draft
    run = TriageRun(
        ticket=ticket,  # also appends to ticket.runs, so the response sees it
        status="failed" if result.error else "succeeded",
        **active_model_info(),  # provider, chat_model, embedding_model
        prompt_version=PROMPT_VERSION,
        classification=classification.model_dump() if classification else None,
        # Audit needs ids + distances, not the chunk text (that's in kb_chunks).
        retrieved=[
            {"chunk_id": c.chunk_id, "article_id": c.article_id, "distance": c.distance}
            for c in result.retrieved
        ],
        draft=draft.model_dump() if draft else None,
        step_timings=result.step_timings,
        latency_ms=latency_ms,
        error=result.error,
    )
    db.add(run)

    ticket.status = result.status
    ticket.category = classification.category if classification else None
    ticket.priority = classification.priority if classification else None
    ticket.sentiment = classification.sentiment if classification else None
    ticket.summary = classification.summary if classification else None
    ticket.draft_reply = draft.reply if draft else None
    ticket.cited_article_ids = draft.cited_article_ids if draft else []
    ticket.confidence = draft.confidence if draft else None
    ticket.review_reasons = result.reasons
    return run


def get_ticket(db: Session, ticket_id: int) -> Ticket:
    """Return one ticket.

    Raises:
        NotFound: if the ticket does not exist.
    """
    ticket = db.get(Ticket, ticket_id)
    if ticket is None:
        raise NotFound(f"Ticket {ticket_id} not found")
    return ticket


def list_tickets(
    db: Session,
    status: TicketStatus | None,
    category: str | None,
    limit: int,
    offset: int,
) -> list[Ticket]:
    """List tickets newest first, optionally filtered (FR-16).

    `selectinload` fetches all listed tickets' runs in ONE extra query; without it,
    `TicketOut.from_ticket` would lazy-load runs once per ticket (N+1 queries).
    """
    stmt = select(Ticket).options(selectinload(Ticket.runs))
    if status is not None:
        stmt = stmt.where(Ticket.status == status)
    if category is not None:
        stmt = stmt.where(Ticket.category == category)
    # id breaks ties between equal timestamps, so pages never overlap or skip rows.
    stmt = stmt.order_by(Ticket.created_at.desc(), Ticket.id.desc()).limit(limit).offset(offset)
    return list(db.scalars(stmt))


def list_runs(db: Session, ticket_id: int) -> list[TriageRun]:
    """All triage runs for a ticket, oldest first.

    Raises:
        NotFound: if the ticket does not exist.
    """
    return list(get_ticket(db, ticket_id).runs)  # relationship is ordered by run id


def review(db: Session, ticket_id: int, data: ReviewIn) -> Ticket:
    """Approve / edit / reject a draft (FR-17, FR-18).

    The row is locked (`SELECT ... FOR UPDATE`) so two reviewers clicking at the
    same moment can't both pass the status check; the second waits, then gets 409.

    Raises:
        NotFound: if the ticket does not exist.
        Conflict: if status is not in `REVIEWABLE_STATUSES`, or `approve` is used
            on a ticket that has no draft (use `edit` to write the reply).
    """
    ticket = db.get(Ticket, ticket_id, with_for_update=True)
    if ticket is None:
        raise NotFound(f"Ticket {ticket_id} not found")
    if ticket.status not in REVIEWABLE_STATUSES:
        raise Conflict(f"Ticket {ticket_id} cannot be reviewed in status '{ticket.status}'")

    match data.action:
        case "approve":
            if not ticket.draft_reply:
                raise Conflict(f"Ticket {ticket_id} has no draft to approve; use 'edit'")
            ticket.final_reply = ticket.draft_reply
            ticket.status = "approved"
        case "edit":
            ticket.final_reply = data.final_reply  # non-empty, enforced by ReviewIn
            ticket.status = "approved"
        case "reject":
            ticket.status = "rejected"

    ticket.review_note = data.note
    ticket.reviewed_at = datetime.now(UTC)
    db.commit()
    db.refresh(ticket)
    return ticket


def get_stats(db: Session) -> StatsOut:
    """Counts by status and category; run count + avg latency by provider (F9).

    Three GROUP BY queries — the database aggregates, Python never loads rows.
    Average latency only counts succeeded runs: a refused connection fails in
    milliseconds and would make a broken provider look fast.
    """
    by_status = db.execute(select(Ticket.status, func.count()).group_by(Ticket.status))
    by_category = db.execute(
        select(Ticket.category, func.count())
        .where(Ticket.category.is_not(None))  # pending / failed-before-classify tickets
        .group_by(Ticket.category)
    )
    by_provider = db.execute(
        select(
            TriageRun.provider,
            func.count(),
            func.avg(TriageRun.latency_ms).filter(TriageRun.status == "succeeded"),
        ).group_by(TriageRun.provider)
    )
    return StatsOut(
        by_status={status: count for status, count in by_status},
        by_category={category: count for category, count in by_category},
        by_provider={
            provider: ProviderStats(
                runs=runs, avg_latency_ms=None if avg is None else round(float(avg), 1)
            )
            for provider, runs, avg in by_provider
        },
    )
