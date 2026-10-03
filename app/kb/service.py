"""KB service: article CRUD, chunking, embedding and vector search.

Raises `app.core.exceptions` errors — never `HTTPException`.
`embeddings` is always injected so tests can pass `DeterministicFakeEmbedding`.
"""

from langchain_core.embeddings import Embeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.exceptions import NotFound
from app.kb.models import KbArticle, KbChunk
from app.kb.schemas import ArticleIn, SearchHit
from app.llm.providers import active_model_info

CHUNK_SIZE = 800  # FR-2
CHUNK_OVERLAP = 100  # FR-2
REINDEX_BATCH_SIZE = 50

# Stateless and safe to share across requests, so build it once.
# Tries "\n\n", then "\n", then " ", then "" — paragraphs stay whole when they fit.
_splitter = RecursiveCharacterTextSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)


def chunk_content(content: str) -> list[str]:
    """Split article content into ≤800-char chunks with ~100-char overlap (FR-2).

    Returns an empty list for blank content; the caller decides whether that's an error.
    """
    return _splitter.split_text(content)


def create_article(db: Session, data: ArticleIn, embeddings: Embeddings) -> KbArticle:
    """Insert an article and its embedded chunks in one transaction (architecture §4.2).

    Embeds *before* touching the DB: the slow network call never holds a
    transaction open, and if it fails nothing has been written.
    """
    texts = chunk_content(data.content)
    vectors = embeddings.embed_documents(texts)  # ONE batched call for all chunks
    embedding_model = active_model_info()["embedding_model"]  # FR-2, filtered on by FR-5

    article = KbArticle(
        title=data.title,
        category=data.category,
        content=data.content,
        chunks=[
            KbChunk(chunk_index=i, text=text, embedding=vector, embedding_model=embedding_model)
            # strict: a provider returning fewer vectors than texts must fail loudly
            for i, (text, vector) in enumerate(zip(texts, vectors, strict=True))
        ],
    )
    db.add(article)
    db.commit()
    db.refresh(article)  # load server defaults (id is set already; created_at is not)
    return article


def list_articles(db: Session, limit: int, offset: int) -> list[KbArticle]:
    """Return articles oldest first, paginated."""
    stmt = select(KbArticle).order_by(KbArticle.id).limit(limit).offset(offset)
    return list(db.scalars(stmt))


def get_article(db: Session, article_id: int) -> KbArticle:
    """Return one article.

    Raises:
        NotFound: if the article does not exist.
    """
    article = db.get(KbArticle, article_id)
    if article is None:
        raise NotFound(f"Article {article_id} not found")
    return article


def delete_article(db: Session, article_id: int) -> None:
    """Delete an article; its chunks are removed by ON DELETE CASCADE (FR-3).

    `passive_deletes=True` on the relationship means SQLAlchemy does not load the
    chunks first — Postgres deletes them in the same statement.

    Raises:
        NotFound: if the article does not exist.
    """
    db.delete(get_article(db, article_id))
    db.commit()


def search(db: Session, query: str, k: int, embeddings: Embeddings) -> list[SearchHit]:
    """Top-k chunks by cosine distance, current embedding model only (FR-4, FR-5).

    No distance threshold here — `/kb/search` shows raw neighbours for debugging;
    the triage workflow applies `RETRIEVAL_MAX_DISTANCE` itself (FR-9).
    """
    query_vector = embeddings.embed_query(query)
    # `<=>` in SQL: cosine distance, 0 = same direction, 2 = opposite.
    distance = KbChunk.embedding.cosine_distance(query_vector).label("distance")
    stmt = (
        # Named columns, not the KbChunk entity: never ship 768 floats back per row.
        select(
            KbChunk.id.label("chunk_id"),
            KbChunk.article_id,
            KbArticle.title,
            KbChunk.text,
            distance,
        )
        .join(KbArticle)
        .where(KbChunk.embedding_model == active_model_info()["embedding_model"])
        .order_by(distance)
        .limit(k)
    )
    return [SearchHit.model_validate(row._mapping) for row in db.execute(stmt)]


def reindex(db: Session, embeddings: Embeddings) -> int:
    """Re-embed every chunk with the current embedding model (FR-6).

    Commits after each batch, so no transaction stays open across an embedding
    call and a failure keeps the batches already done. A half-finished reindex is
    safe: search only sees chunks tagged with the current model, and re-running
    simply redoes all of them.

    Returns:
        Number of chunks re-embedded.
    """
    embedding_model = active_model_info()["embedding_model"]
    rows = db.execute(select(KbChunk.id, KbChunk.text).order_by(KbChunk.id)).all()
    db.commit()  # end the read transaction before the first network call

    for start in range(0, len(rows), REINDEX_BATCH_SIZE):
        batch = rows[start : start + REINDEX_BATCH_SIZE]
        vectors = embeddings.embed_documents([row.text for row in batch])
        # ORM "bulk UPDATE by primary key": one executemany for the whole batch.
        db.execute(
            update(KbChunk),
            [
                {"id": row.id, "embedding": vector, "embedding_model": embedding_model}
                for row, vector in zip(batch, vectors, strict=True)
            ],
        )
        db.commit()

    return len(rows)
