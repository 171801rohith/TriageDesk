"""Shared fixtures: fake LLM chains, fake embeddings, test DB session, API client.

Unit tests need no network, no API keys and no DB (NFR-7). Integration tests
use a real `triagedesk_test` Postgres database with fake LLM/embeddings.
"""

import os

# Must be set before any `app.*` import: `app.core.db` builds the engine at import time.
os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg://triage:triage@localhost:5434/triagedesk_test"
)

from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient
from langchain_core.embeddings import DeterministicFakeEmbedding, Embeddings
from langchain_core.runnables import RunnableLambda
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.kb.models import EMBEDDING_DIM
from app.triage.llm_schemas import Classification, DraftReply, RetrievedChunk
from app.triage.workflow import TriageWorkflow


@pytest.fixture
def fake_embeddings() -> Embeddings:
    """Deterministic 768-d embeddings, no network."""
    return DeterministicFakeEmbedding(size=EMBEDDING_DIM)


@pytest.fixture
def make_classification() -> Callable[..., Classification]:
    """Factory for a valid `Classification`; override any field via kwargs."""

    def _make(**overrides: object) -> Classification:
        fields: dict[str, object] = {
            "category": "billing",
            "priority": "medium",
            "sentiment": "neutral",
            "summary": "Customer reports a duplicate charge.",
            "language": "en",
        }
        fields.update(overrides)
        return Classification.model_validate(fields)

    return _make


@pytest.fixture
def make_draft() -> Callable[..., DraftReply]:
    """Factory for a valid `DraftReply`; override any field via kwargs."""

    def _make(**overrides: object) -> DraftReply:
        fields: dict[str, object] = {
            "reply": "We've refunded the duplicate charge.",
            "cited_article_ids": [1],
            "confidence": 0.9,
        }
        fields.update(overrides)
        return DraftReply.model_validate(fields)

    return _make


@pytest.fixture
def make_chunk() -> Callable[..., RetrievedChunk]:
    """Factory for a `RetrievedChunk`; override any field via kwargs."""

    def _make(**overrides: object) -> RetrievedChunk:
        fields: dict[str, object] = {
            "chunk_id": 1,
            "article_id": 1,
            "title": "Duplicate charges",
            "text": "If you were charged twice, we refund the duplicate within 5 days.",
            "distance": 0.2,
        }
        fields.update(overrides)
        return RetrievedChunk.model_validate(fields)

    return _make


@pytest.fixture
def make_workflow() -> Callable[..., TriageWorkflow]:
    """Build a `TriageWorkflow` from plain callables wrapped in `RunnableLambda`.

    Example: ``make_workflow(classify=lambda _: cls, draft=lambda _: d, search=lambda q: [])``
    """

    def _make(
        classify: Callable[[dict], Classification],
        draft: Callable[[dict], DraftReply],
        search: Callable[[str], list[RetrievedChunk]],
    ) -> TriageWorkflow:
        return TriageWorkflow(
            classifier=RunnableLambda(classify),
            drafter=RunnableLambda(draft),
            search_fn=search,
            settings=get_settings(),
        )

    return _make


@pytest.fixture(scope="session")
def migrated_test_db() -> Iterator[None]:
    """Run `alembic upgrade head` against `triagedesk_test` once per session.

    TODO: invoke alembic programmatically (`alembic.command.upgrade(cfg, "head")`).
    """
    pytest.skip("TODO: test database setup not implemented")
    yield


@pytest.fixture
def db_session(migrated_test_db: None) -> Iterator[Session]:
    """A session wrapped in a transaction that is rolled back after each test.

    TODO: open connection + outer transaction, bind a Session to it, roll back at teardown.
    """
    pytest.skip("TODO: transactional test session not implemented")
    yield  # type: ignore[misc]


@pytest.fixture
def client(db_session: Session, fake_embeddings: Embeddings) -> Iterator[TestClient]:
    """`TestClient` with DB, embeddings and workflow dependencies overridden.

    TODO: also override `get_workflow` with a fake-backed TriageWorkflow.
    """
    from app.core.db import get_db
    from app.kb.router import get_embeddings_dep
    from app.main import app

    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_embeddings_dep] = lambda: fake_embeddings
    try:
        with TestClient(app) as c:
            yield c
    finally:
        app.dependency_overrides.clear()
