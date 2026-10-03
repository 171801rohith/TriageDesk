"""Pydantic request/response models for the KB API (requirements §5, FR-1/FR-4)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ArticleIn(BaseModel):
    """Body of `POST /kb/articles` (FR-1).

    Whitespace is stripped before `min_length` is checked, so a blank title or
    content is a 422 here and never reaches the service as a zero-chunk article.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=200)
    category: str = Field(min_length=1, max_length=50)
    content: str = Field(min_length=1, description="Plain text / markdown")


class ArticleOut(BaseModel):
    """An article as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    category: str
    content: str
    created_at: datetime


class SearchIn(BaseModel):
    """Body of `POST /kb/search`."""

    query: str = Field(min_length=1)
    k: int = Field(default=4, ge=1, le=50)


class SearchHit(BaseModel):
    """One retrieved chunk (FR-4). Also used by triage as `RetrievedChunk`."""

    model_config = ConfigDict(from_attributes=True)

    chunk_id: int
    article_id: int
    title: str
    text: str
    distance: float = Field(description="Cosine distance; 0 = identical")


class ReindexOut(BaseModel):
    """Result of `POST /kb/reindex` (FR-6)."""

    reindexed_chunks: int
    embedding_model: str
