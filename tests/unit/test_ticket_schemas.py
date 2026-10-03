"""Ticket API schemas: ReviewIn validation and ORM → TicketOut mapping. No DB."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.tickets.models import Ticket, TriageRun
from app.tickets.schemas import ReviewIn, TicketOut

NOW = datetime(2026, 10, 2, tzinfo=UTC)


def _ticket(**overrides: object) -> Ticket:
    """A transient (never saved) Ticket with the fields the DB would normally fill."""
    fields: dict[str, object] = {
        "id": 42,
        "customer_email": "sam@example.com",
        "subject": "Charged twice this month",
        "body": "Please refund one.",
        "status": "needs_review",
        "cited_article_ids": [],
        "review_reasons": ["no_relevant_kb"],
        "created_at": NOW,
        "updated_at": NOW,
    }
    fields.update(overrides)
    return Ticket(**fields)


def _run(**overrides: object) -> TriageRun:
    fields: dict[str, object] = {
        "id": 57,
        "status": "succeeded",
        "provider": "ollama",
        "chat_model": "hermes3:8b",
        "embedding_model": "nomic-embed-text",
        "prompt_version": "v1",
        "classification": {
            "category": "billing",
            "priority": "medium",
            "sentiment": "negative",
            "summary": "Duplicate charge.",
            "language": "en",
        },
        "latency_ms": 4120,
    }
    fields.update(overrides)
    return TriageRun(**fields)


@pytest.mark.parametrize("final_reply", [None, "", "   "])
def test_edit_without_final_reply_is_rejected(final_reply: str | None) -> None:
    with pytest.raises(ValidationError, match="final_reply is required"):
        ReviewIn(action="edit", final_reply=final_reply)


@pytest.mark.parametrize(
    "body",
    [
        {"action": "edit", "final_reply": "We've refunded it."},
        {"action": "approve"},
        {"action": "reject", "note": "Spam"},
    ],
)
def test_valid_reviews_are_accepted(body: dict[str, str]) -> None:
    assert ReviewIn.model_validate(body).action == body["action"]


def test_unknown_action_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ReviewIn.model_validate({"action": "send"})


def test_from_ticket_without_runs() -> None:
    """A brand-new ticket has no classification and no latest_run."""
    out = TicketOut.from_ticket(_ticket(runs=[]))

    assert out.classification is None
    assert out.latest_run is None
    assert out.review_reasons == ["no_relevant_kb"]


def test_from_ticket_uses_latest_run() -> None:
    """classification (incl. language) and latest_run come from the newest run."""
    old = _run(id=1, chat_model="old-model")
    new = _run(id=57)

    out = TicketOut.from_ticket(_ticket(runs=[old, new]))

    assert out.classification is not None
    assert (out.classification.category, out.classification.language) == ("billing", "en")
    assert out.latest_run is not None
    assert out.latest_run.model_dump() == {
        "id": 57,
        "provider": "ollama",
        "model": "hermes3:8b",
        "latency_ms": 4120,
        "status": "succeeded",
    }


def test_from_ticket_failed_run_without_classification() -> None:
    """A run that failed before classifying → classification None, latest_run still shown."""
    out = TicketOut.from_ticket(_ticket(runs=[_run(status="failed", classification=None)]))

    assert out.classification is None
    assert out.latest_run is not None
    assert out.latest_run.status == "failed"
