"""`GET /health`: DB connectivity + active provider and model names (FR-20)."""

import logging
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.llm.providers import active_model_info

router = APIRouter(tags=["health"])


class HealthOut(BaseModel):
    """Health payload, e.g. `{"db": "ok", "provider": "gemini", ...}`."""

    db: Literal["ok", "error"]
    provider: str
    chat_model: str
    embedding_model: str


logger = logging.getLogger(__name__)


def check_db(db: Session) -> Literal["ok", "error"]:
    """Return "ok" if the database answers `SELECT 1`, "error" otherwise."""
    try:
        db.execute(text("SELECT 1"))
        return "ok"
    except Exception:
        logger.exception("Database health check failed")
        return "error"


@router.get("/health", response_model=HealthOut)
def health(db: Session = Depends(get_db)) -> HealthOut:
    """Report DB status and the active LLM provider/models."""
    return HealthOut(db=check_db(db), **active_model_info())
