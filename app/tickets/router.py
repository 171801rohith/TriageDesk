"""Tickets + stats HTTP endpoints (requirements §5). No business logic here."""

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.kb import service as kb_service
from app.llm.providers import get_chat_model, get_embeddings
from app.tickets import service
from app.tickets.schemas import ReviewIn, RunOut, StatsOut, TicketIn, TicketOut, TicketStatus
from app.triage.workflow import TriageWorkflow, build_classifier, build_drafter

router = APIRouter(tags=["tickets"])

CLASSIFY_TEMPERATURE = 0.0
DRAFT_TEMPERATURE = 0.2


def get_workflow(db: Session = Depends(get_db)) -> TriageWorkflow:
    """Build the real workflow for this request. Tests override this dependency."""
    settings = get_settings()
    emb = get_embeddings()
    return TriageWorkflow(
        classifier=build_classifier(get_chat_model(CLASSIFY_TEMPERATURE)),
        drafter=build_drafter(get_chat_model(DRAFT_TEMPERATURE)),
        search_fn=lambda q: kb_service.search(db, q, settings.retrieval_k, emb),
        settings=settings,
    )


@router.post("/tickets", response_model=TicketOut, status_code=status.HTTP_201_CREATED)
def create_ticket(
    data: TicketIn,
    db: Session = Depends(get_db),
    workflow: TriageWorkflow = Depends(get_workflow),
) -> TicketOut:
    """Create a ticket and triage it synchronously (FR-7)."""
    return TicketOut.from_ticket(service.create_ticket(db, data, workflow))


@router.get("/tickets", response_model=list[TicketOut])
def list_tickets(
    status_: TicketStatus | None = Query(None, alias="status"),
    category: str | None = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> list[TicketOut]:
    """List tickets, newest first (FR-16)."""
    tickets = service.list_tickets(db, status_, category, limit, offset)
    return [TicketOut.from_ticket(t) for t in tickets]


@router.get("/tickets/{ticket_id}", response_model=TicketOut)
def get_ticket(ticket_id: int, db: Session = Depends(get_db)) -> TicketOut:
    """Ticket + latest triage result."""
    return TicketOut.from_ticket(service.get_ticket(db, ticket_id))


@router.post("/tickets/{ticket_id}/triage", response_model=TicketOut)
def retriage(
    ticket_id: int,
    db: Session = Depends(get_db),
    workflow: TriageWorkflow = Depends(get_workflow),
) -> TicketOut:
    """Re-run triage, creating a new run (FR-15)."""
    return TicketOut.from_ticket(service.retriage(db, ticket_id, workflow))


@router.post("/tickets/{ticket_id}/review", response_model=TicketOut)
def review(ticket_id: int, data: ReviewIn, db: Session = Depends(get_db)) -> TicketOut:
    """Approve / edit / reject a draft (FR-17, FR-18)."""
    return TicketOut.from_ticket(service.review(db, ticket_id, data))


@router.get("/tickets/{ticket_id}/runs", response_model=list[RunOut])
def list_runs(ticket_id: int, db: Session = Depends(get_db)) -> list[RunOut]:
    """All triage runs for a ticket (F7)."""
    return service.list_runs(db, ticket_id)


@router.get("/stats", response_model=StatsOut)
def stats(db: Session = Depends(get_db)) -> StatsOut:
    """Counts by status/category/provider and avg latency (F9)."""
    return service.get_stats(db)
