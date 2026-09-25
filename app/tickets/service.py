"""Tickets service: creation + triage, re-triage, review, listing and stats.

Owns the ticket lifecycle (architecture.md §4.3). Calls the workflow but knows
nothing about LLM providers. Raises `NotFound` / `Conflict`, never `HTTPException`.
"""

from sqlalchemy.orm import Session

from app.tickets.models import Ticket, TriageRun
from app.tickets.schemas import ReviewIn, StatsOut, TicketIn, TicketStatus
from app.triage.workflow import TriageWorkflow


def create_ticket(db: Session, data: TicketIn, workflow: TriageWorkflow) -> Ticket:
    """Persist a `pending` ticket, run triage synchronously, commit (FR-7).

    TODO: insert Ticket → db.flush() (to get the id) → _apply_triage → commit.
    """
    raise NotImplementedError("create_ticket")


def retriage(db: Session, ticket_id: int, workflow: TriageWorkflow) -> Ticket:
    """Re-run the workflow on an existing ticket, creating a new run (FR-15).

    Raises:
        NotFound: if the ticket does not exist.

    TODO: load ticket, set status back to `pending`, _apply_triage, commit.
    """
    raise NotImplementedError("retriage")


def _apply_triage(db: Session, ticket: Ticket, workflow: TriageWorkflow) -> TriageRun:
    """Run the workflow, store a `TriageRun`, copy latest results onto the ticket.

    Shared by `create_ticket` and `retriage`.

    TODO:
        - result = workflow.run(ticket.subject, ticket.body)
        - TriageRun(... active_model_info(), PROMPT_VERSION, model_dump() of outputs,
          step_timings, latency_ms, error, status="failed" if result.error else "succeeded")
        - copy status/classification/draft/reasons onto the ticket
    """
    raise NotImplementedError("_apply_triage")


def get_ticket(db: Session, ticket_id: int) -> Ticket:
    """Return one ticket.

    Raises:
        NotFound: if the ticket does not exist.

    TODO: implement lookup.
    """
    raise NotImplementedError("get_ticket")


def list_tickets(
    db: Session,
    status: TicketStatus | None,
    category: str | None,
    limit: int,
    offset: int,
) -> list[Ticket]:
    """List tickets newest first, optionally filtered (FR-16).

    TODO: select with optional filters, ORDER BY created_at DESC, limit/offset.
    """
    raise NotImplementedError("list_tickets")


def list_runs(db: Session, ticket_id: int) -> list[TriageRun]:
    """All triage runs for a ticket, oldest first.

    Raises:
        NotFound: if the ticket does not exist.

    TODO: implement.
    """
    raise NotImplementedError("list_runs")


def review(db: Session, ticket_id: int, data: ReviewIn) -> Ticket:
    """Approve / edit / reject a draft (FR-17, FR-18).

    Raises:
        NotFound: if the ticket does not exist.
        Conflict: if status is not in `REVIEWABLE_STATUSES`.

    TODO:
        - approve → final_reply = draft_reply; status approved
        - edit    → final_reply = data.final_reply; status approved
        - reject  → status rejected; review_note = data.note
        - set reviewed_at; commit
    """
    raise NotImplementedError("review")


def get_stats(db: Session) -> StatsOut:
    """Counts by status and category; run count + avg latency by provider (F9).

    TODO: GROUP BY queries on tickets and triage_runs.
    """
    raise NotImplementedError("get_stats")
