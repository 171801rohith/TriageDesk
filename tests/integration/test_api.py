"""API tests against a real `triagedesk_test` Postgres with fake LLM + embeddings.

Each test runs inside a transaction that is rolled back afterwards (see
`db_session`), so tests can't see each other's data.
"""

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.kb.models import KbChunk
from app.main import app
from app.tickets.models import TriageRun
from app.tickets.router import get_workflow
from app.triage.prompts import PROMPT_VERSION
from app.triage.workflow import TriageWorkflow

pytestmark = pytest.mark.integration

TICKETS = "/api/v1/tickets"
ARTICLES = "/api/v1/kb/articles"
TICKET = {
    "customer_email": "sam@example.com",
    "subject": "Charged twice this month",
    "body": "Hi, my card was charged twice for the Pro plan on Sept 3. Please refund one.",
}


def _boom(_: object) -> None:
    raise TimeoutError("boom")


def _create(client: TestClient, **overrides: str) -> dict:
    response = client.post(TICKETS, json={**TICKET, **overrides})
    assert response.status_code == 201, response.text
    return response.json()


def test_create_ticket_returns_201(client: TestClient, db_session: Session) -> None:
    """POST /api/v1/tickets → 201 with triage result and a triage_runs row."""
    ticket = _create(client)

    assert ticket["status"] == "auto_ready"
    assert ticket["classification"]["category"] == "billing"
    assert ticket["cited_article_ids"] == [1]
    assert ticket["latest_run"]["status"] == "succeeded"
    run = db_session.scalars(select(TriageRun).where(TriageRun.ticket_id == ticket["id"])).one()
    assert set(run.step_timings) == {"classify", "retrieve", "draft", "guardrails"}
    assert run.prompt_version == PROMPT_VERSION


def test_get_missing_ticket_returns_404(client: TestClient) -> None:
    """GET /api/v1/tickets/999999 → 404 with {"detail": ...}."""
    response = client.get(f"{TICKETS}/999999")

    assert response.status_code == 404
    assert response.json() == {"detail": "Ticket 999999 not found"}


def test_review_edit_sets_final_reply_and_approves(client: TestClient) -> None:
    """review action=edit → final_reply set, status approved."""
    ticket = _create(client)

    response = client.post(
        f"{TICKETS}/{ticket['id']}/review", json={"action": "edit", "final_reply": "Refunded!"}
    )

    assert response.status_code == 200
    assert response.json()["status"] == "approved"
    assert response.json()["final_reply"] == "Refunded!"
    assert response.json()["reviewed_at"] is not None


def test_double_review_returns_409(client: TestClient) -> None:
    """Reviewing an already-approved ticket → 409."""
    ticket = _create(client)
    client.post(f"{TICKETS}/{ticket['id']}/review", json={"action": "approve"})

    response = client.post(f"{TICKETS}/{ticket['id']}/review", json={"action": "reject"})

    assert response.status_code == 409
    assert response.json() == {
        "detail": f"Ticket {ticket['id']} cannot be reviewed in status 'approved'"
    }


def test_llm_failure_still_returns_201_needs_review(
    client: TestClient, make_workflow: Callable[..., TriageWorkflow]
) -> None:
    """Failing classifier → 201, needs_review, run status=failed with error (FR-13)."""
    failing = make_workflow(classify=_boom, draft=_boom, search=lambda _: [])
    app.dependency_overrides[get_workflow] = lambda: failing

    ticket = _create(client)

    assert ticket["status"] == "needs_review"
    assert ticket["review_reasons"] == ["llm_error"]
    runs = client.get(f"{TICKETS}/{ticket['id']}/runs").json()
    assert [(r["status"], r["error"]) for r in runs] == [("failed", "TimeoutError: boom")]


def test_retriage_adds_a_run_and_shows_the_latest(
    client: TestClient, make_workflow: Callable[..., TriageWorkflow]
) -> None:
    """FR-15: re-run creates a new run; the ticket reflects the newest one."""
    ticket = _create(client)  # succeeds with the default fake
    app.dependency_overrides[get_workflow] = lambda: make_workflow(
        classify=_boom, draft=_boom, search=lambda _: []
    )

    response = client.post(f"{TICKETS}/{ticket['id']}/triage")

    assert response.status_code == 200
    assert response.json()["status"] == "needs_review"
    assert response.json()["classification"] is None  # no stale data from run 1
    runs = client.get(f"{TICKETS}/{ticket['id']}/runs").json()
    assert [r["status"] for r in runs] == ["succeeded", "failed"]


def test_list_filters_by_status_newest_first(
    client: TestClient, make_workflow: Callable[..., TriageWorkflow]
) -> None:
    """FR-16: ?status=needs_review returns only those tickets, newest first."""
    ready = _create(client)
    app.dependency_overrides[get_workflow] = lambda: make_workflow(
        classify=_boom, draft=_boom, search=lambda _: []
    )
    older, newer = _create(client), _create(client)

    listed = client.get(TICKETS, params={"status": "needs_review"}).json()

    assert [t["id"] for t in listed] == [newer["id"], older["id"]]
    assert ready["id"] not in {t["id"] for t in listed}


def test_stats_counts_by_status_category_and_provider(client: TestClient) -> None:
    """F9: /stats aggregates what the other endpoints created."""
    _create(client)
    rejected = _create(client)
    client.post(f"{TICKETS}/{rejected['id']}/review", json={"action": "reject"})

    stats = client.get("/api/v1/stats").json()

    assert stats["by_status"] == {"auto_ready": 1, "rejected": 1}
    assert stats["by_category"] == {"billing": 2}
    assert sum(p["runs"] for p in stats["by_provider"].values()) == 2


def test_kb_create_and_delete_cascades_chunks(client: TestClient, db_session: Session) -> None:
    """Create article (chunks stored) → delete → chunks gone."""
    content = "\n\n".join(f"Paragraph {i}. " + "Refunds take 5 days. " * 30 for i in range(3))
    created = client.post(
        ARTICLES, json={"title": "Refunds", "category": "billing", "content": content}
    )
    assert created.status_code == 201
    article_id = created.json()["id"]

    def chunk_count() -> int:
        stmt = select(func.count()).select_from(KbChunk).where(KbChunk.article_id == article_id)
        return db_session.scalar(stmt) or 0

    assert chunk_count() > 1
    assert client.delete(f"{ARTICLES}/{article_id}").status_code == 204
    assert chunk_count() == 0
    assert client.get(f"{ARTICLES}/{article_id}").status_code == 404
