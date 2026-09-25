"""KB HTTP endpoints (requirements §5). No business logic — delegates to `kb.service`."""

from fastapi import APIRouter, Depends, Query, Response, status
from langchain_core.embeddings import Embeddings
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.kb import service
from app.kb.schemas import ArticleIn, ArticleOut, ReindexOut, SearchHit, SearchIn
from app.llm.providers import active_model_info, get_embeddings

router = APIRouter(prefix="/kb", tags=["kb"])


def get_embeddings_dep() -> Embeddings:
    """Embeddings dependency — tests override this with a fake."""
    return get_embeddings()


@router.post("/articles", response_model=ArticleOut, status_code=status.HTTP_201_CREATED)
def create_article(
    data: ArticleIn,
    db: Session = Depends(get_db),
    embeddings: Embeddings = Depends(get_embeddings_dep),
) -> ArticleOut:
    """Create an article; it is chunked and embedded immediately (F1)."""
    return service.create_article(db, data, embeddings)


@router.get("/articles", response_model=list[ArticleOut])
def list_articles(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> list[ArticleOut]:
    """List articles, paginated."""
    return service.list_articles(db, limit, offset)


@router.get("/articles/{article_id}", response_model=ArticleOut)
def get_article(article_id: int, db: Session = Depends(get_db)) -> ArticleOut:
    """Get one article (404 if missing)."""
    return service.get_article(db, article_id)


@router.delete("/articles/{article_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_article(article_id: int, db: Session = Depends(get_db)) -> Response:
    """Delete an article and its chunks (404 if missing)."""
    service.delete_article(db, article_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/search", response_model=list[SearchHit])
def search(
    data: SearchIn,
    db: Session = Depends(get_db),
    embeddings: Embeddings = Depends(get_embeddings_dep),
) -> list[SearchHit]:
    """Semantic search over KB chunks (F2)."""
    return service.search(db, data.query, data.k, embeddings)


@router.post("/reindex", response_model=ReindexOut)
def reindex(
    db: Session = Depends(get_db),
    embeddings: Embeddings = Depends(get_embeddings_dep),
) -> ReindexOut:
    """Re-embed all chunks with the current embedding model (FR-6)."""
    count = service.reindex(db, embeddings)
    return ReindexOut(
        reindexed_chunks=count,
        embedding_model=active_model_info()["embedding_model"],
    )
