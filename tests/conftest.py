"""Shared fixtures: fake LLM chains, fake embeddings, test DB session, API client.

Unit tests need no network, no API keys and no DB (NFR-7). Integration tests
use a real `triagedesk_test` Postgres database with fake LLM/embeddings.
"""

import os

# Must be set before any `app.*` import: `app.core.db` builds the engine at import time.
# Forced (not setdefault) so a DATABASE_URL in your shell can never point tests at dev data.
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://triage:triage@localhost:5434/triagedesk_test"
)
os.environ["DATABASE_URL"] = TEST_DATABASE_URL

from collections.abc import Callable, Iterator

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from langchain_core.embeddings import DeterministicFakeEmbedding, Embeddings
from langchain_core.runnables import RunnableLambda
from sqlalchemy import create_engine, make_url, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from alembic import command
from app.core.config import Settings, get_settings
from app.kb.models import EMBEDDING_DIM
from app.triage.llm_schemas import Classification, DraftReply, RetrievedChunk
from app.triage.workflow import TriageWorkflow

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


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
def test_settings() -> Settings:
    """Settings pinned to the documented defaults, so tuning `.env` can't break tests."""
    return get_settings().model_copy(
        update={"retrieval_max_distance": 0.5, "confidence_threshold": 0.7}
    )


@pytest.fixture
def make_workflow(test_settings: Settings) -> Callable[..., TriageWorkflow]:
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
            settings=test_settings,
        )

    return _make


@pytest.fixture(scope="session")
def migrated_test_db() -> None:
    """Create `triagedesk_test` if missing and `alembic upgrade head` it, once per session.

    Skips (not fails) the integration tests when Postgres isn't reachable, so the
    unit suite still runs on a machine without Docker.
    """
    url = make_url(TEST_DATABASE_URL)
    if not url.database or not url.database.endswith("_test"):
        pytest.exit(f"Refusing to run integration tests against {url.database!r}", returncode=2)

    # CREATE DATABASE can't run inside a transaction → AUTOCOMMIT, on the `postgres` db.
    admin = create_engine(
        url.set(database="postgres"),
        isolation_level="AUTOCOMMIT",
        connect_args={"connect_timeout": 5},  # fail fast → skip, never hang
    )
    try:
        with admin.connect() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": url.database}
            ).scalar()
            if not exists:
                conn.execute(text(f'CREATE DATABASE "{url.database}"'))
    except OperationalError as exc:
        pytest.skip(f"Postgres not reachable for integration tests: {exc.orig}")
    finally:
        admin.dispose()

    # env.py reads the URL from get_settings(), which already sees TEST_DATABASE_URL.
    command.upgrade(Config(os.path.join(ROOT, "alembic.ini")), "head")


@pytest.fixture
def db_session(migrated_test_db: None) -> Iterator[Session]:
    """A session inside one outer transaction that is rolled back after each test.

    `join_transaction_mode="create_savepoint"` turns the services' own `commit()`
    calls into SAVEPOINT releases, so code under test commits normally while
    nothing it writes outlives the test.
    """
    from app.core.db import engine

    connection = engine.connect()
    outer = connection.begin()
    session = Session(
        bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False
    )
    try:
        yield session
    finally:
        session.close()
        outer.rollback()
        connection.close()


@pytest.fixture
def fake_workflow(
    make_workflow: Callable[..., TriageWorkflow],
    make_classification: Callable[..., Classification],
    make_draft: Callable[..., DraftReply],
    make_chunk: Callable[..., RetrievedChunk],
) -> TriageWorkflow:
    """A workflow whose every step succeeds: billing, article 1 retrieved and cited."""
    return make_workflow(
        classify=lambda _: make_classification(),
        draft=lambda _: make_draft(cited_article_ids=[1]),
        search=lambda _: [make_chunk(article_id=1)],
    )


@pytest.fixture
def client(
    db_session: Session, fake_embeddings: Embeddings, fake_workflow: TriageWorkflow
) -> Iterator[TestClient]:
    """`TestClient` with DB, embeddings and workflow dependencies overridden.

    Swap the workflow inside a test with
    ``app.dependency_overrides[get_workflow] = lambda: other_workflow``.
    """
    from app.core.db import get_db
    from app.kb.router import get_embeddings_dep
    from app.main import app
    from app.tickets.router import get_workflow

    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_embeddings_dep] = lambda: fake_embeddings
    app.dependency_overrides[get_workflow] = lambda: fake_workflow
    try:
        with TestClient(app) as c:
            yield c
    finally:
        app.dependency_overrides.clear()
