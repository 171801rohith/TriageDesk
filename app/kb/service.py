"""KB service: article CRUD, chunking, embedding and vector search.

Raises `app.core.exceptions` errors — never `HTTPException`.
`embeddings` is always injected so tests can pass `DeterministicFakeEmbedding`.
"""

from langchain_core.embeddings import Embeddings
from sqlalchemy.orm import Session

from app.kb.models import KbArticle
from app.kb.schemas import ArticleIn, SearchHit

CHUNK_SIZE = 800  # FR-2
CHUNK_OVERLAP = 100  # FR-2
REINDEX_BATCH_SIZE = 50


def chunk_content(content: str) -> list[str]:
    """Split article content into ~800-char chunks with ~100-char overlap (FR-2).

    TODO: `RecursiveCharacterTextSplitter(chunk_size=CHUNK_SIZE,
          chunk_overlap=CHUNK_OVERLAP).split_text(content)` from `langchain_text_splitters`.
    """
    raise NotImplementedError("chunk_content")


def create_article(db: Session, data: ArticleIn, embeddings: Embeddings) -> KbArticle:
    """Insert an article and its embedded chunks in one transaction (architecture §4.2).

    TODO:
        - chunks = chunk_content(data.content)
        - vectors = embeddings.embed_documents(chunks)   # ONE batched call
        - add KbArticle + KbChunk rows (with current embedding model name)
        - db.commit() once; return the article
    """
    raise NotImplementedError("create_article")


def list_articles(db: Session, limit: int, offset: int) -> list[KbArticle]:
    """Return articles, paginated.

    TODO: select KbArticle ordered by id/created_at with limit/offset.
    """
    raise NotImplementedError("list_articles")


def get_article(db: Session, article_id: int) -> KbArticle:
    """Return one article.

    Raises:
        NotFound: if the article does not exist.

    TODO: implement lookup.
    """
    raise NotImplementedError("get_article")


def delete_article(db: Session, article_id: int) -> None:
    """Delete an article; its chunks are removed by ON DELETE CASCADE (FR-3).

    Raises:
        NotFound: if the article does not exist.

    TODO: implement delete + commit.
    """
    raise NotImplementedError("delete_article")


def search(db: Session, query: str, k: int, embeddings: Embeddings) -> list[SearchHit]:
    """Top-k chunks by cosine distance, current embedding model only (FR-4, FR-5).

    TODO (implement_1.md Phase 4):
        q = embeddings.embed_query(query)
        distance = KbChunk.embedding.cosine_distance(q).label("distance")
        select(KbChunk, KbArticle.title, distance).join(KbArticle)
            .where(KbChunk.embedding_model == <current embed model>)
            .order_by(distance).limit(k)
        → map rows to SearchHit
    """
    raise NotImplementedError("search")


def reindex(db: Session, embeddings: Embeddings) -> int:
    """Re-embed every chunk with the current embedding model (FR-6).

    Returns:
        Number of chunks re-embedded.

    TODO: iterate chunks in batches of REINDEX_BATCH_SIZE, `embed_documents`,
          update `embedding` + `embedding_model`, commit.
    """
    raise NotImplementedError("reindex")
