"""Seed the KB from `data/kb_articles/*.md`.

File format: line 1 = title, line 2 = category, rest = content.
Idempotent: articles whose title already exists are skipped, so re-running is safe.

Usage:
    uv run python scripts/seed_kb.py
"""

from pathlib import Path

from sqlalchemy import select

from app.core.db import SessionLocal
from app.kb.models import KbArticle
from app.kb.schemas import ArticleIn
from app.kb.service import create_article
from app.llm.providers import active_model_info, get_embeddings

ARTICLES_DIR = Path(__file__).resolve().parent.parent / "data" / "kb_articles"


def parse_article_file(path: Path) -> ArticleIn:
    """Parse one markdown file into an `ArticleIn` (validation is pydantic's job).

    Raises:
        ValueError: the file has fewer than three lines.
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    if len(lines) < 3:
        raise ValueError(f"{path.name}: expected title, category and content lines")
    return ArticleIn(
        title=lines[0].lstrip("#").strip(),
        category=lines[1].strip(),
        content="\n".join(lines[2:]).strip(),
    )


def main() -> None:
    """Create every article not already in the KB, with the configured embeddings."""
    embeddings = get_embeddings()
    print(f"Embedding with {active_model_info()['embedding_model']}")

    with SessionLocal() as db:
        existing = set(db.scalars(select(KbArticle.title)))
        for path in sorted(ARTICLES_DIR.glob("*.md")):
            data = parse_article_file(path)
            if data.title in existing:
                print(f"  skip   {data.title}")
                continue
            article = create_article(db, data, embeddings)
            print(f"  added  #{article.id} {article.title} ({len(article.chunks)} chunks)")


if __name__ == "__main__":
    main()
