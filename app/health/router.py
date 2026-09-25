"""`GET /health`: DB connectivity + active provider and model names (FR-20)."""

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
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


def check_db(db: Session) -> Literal["ok", "error"]:
    """Return "ok" if the database answers, "error" otherwise.

    TODO: execute `SELECT 1`; catch exceptions and return "error".
    """
    raise NotImplementedError("check_db")


@router.get("/health", response_model=HealthOut)
def health(db: Session = Depends(get_db)) -> HealthOut:
    """Report DB status and the active LLM provider/models."""
    return HealthOut(db=check_db(db), **active_model_info())
