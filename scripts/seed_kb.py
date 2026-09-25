"""Seed the KB from `data/kb_articles/*.md`.

File format: line 1 = title, line 2 = category, rest = content.

Usage:
    python scripts/seed_kb.py
"""

from pathlib import Path

from app.kb.schemas import ArticleIn

ARTICLES_DIR = Path(__file__).resolve().parent.parent / "data" / "kb_articles"


def parse_article_file(path: Path) -> ArticleIn:
    """Parse one markdown file into an `ArticleIn`.

    TODO: split lines → title, category, content (strip leading `#` from the title if used).
    """
    raise NotImplementedError("parse_article_file")


def main() -> None:
    """Create every article via `kb.service.create_article` with real embeddings.

    TODO: open `SessionLocal()`, `get_embeddings()`, loop over sorted *.md files,
          call create_article, print what was created.
    """
    raise NotImplementedError("seed_kb.main")


if __name__ == "__main__":
    main()
