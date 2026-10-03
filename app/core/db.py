"""SQLAlchemy engine, session factory, declarative Base and the `get_db` dependency.

Sync SQLAlchemy + plain `def` endpoints (architecture.md §3.6): FastAPI runs them
in a threadpool, so blocking DB calls don't freeze the event loop.
"""

from collections.abc import Iterator

from sqlalchemy import MetaData, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings

# Stable constraint/index names make Alembic autogenerate diffs predictable.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

# connect_timeout: fail in 5s instead of hanging when the port accepts but no
# Postgres answers (seen with Docker Desktop when the db container is stopped).
engine = create_engine(
    get_settings().database_url,
    pool_pre_ping=True,
    connect_args={"connect_timeout": 5},
)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    """Declarative base for all ORM models. `Base.metadata` is Alembic's target."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def get_db() -> Iterator[Session]:
    """FastAPI dependency: one session per request, always closed afterwards."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
