"""API tests against a real `triagedesk_test` Postgres with fake LLM + embeddings."""

import pytest

pytestmark = pytest.mark.integration

TODO = pytest.mark.skip(reason="TODO: implement services + test DB fixtures first")


@TODO
def test_create_ticket_returns_201() -> None:
    """POST /api/v1/tickets → 201 with triage result and a triage_runs row."""


@TODO
def test_get_missing_ticket_returns_404() -> None:
    """GET /api/v1/tickets/999999 → 404 with {"detail": ...}."""


@TODO
def test_review_edit_sets_final_reply_and_approves() -> None:
    """review action=edit → final_reply set, status approved."""


@TODO
def test_double_review_returns_409() -> None:
    """Reviewing an already-approved ticket → 409."""


@TODO
def test_llm_failure_still_returns_201_needs_review() -> None:
    """Failing classifier → 201, needs_review, run status=failed with error (FR-13)."""


@TODO
def test_kb_create_and_delete_cascades_chunks() -> None:
    """Create article (chunks stored) → delete → chunks gone."""
