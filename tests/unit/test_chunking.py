"""KB chunking (FR-2). Pure function — no DB, no embeddings."""

from itertools import pairwise

from app.kb.service import CHUNK_SIZE, chunk_content


def _numbered_words(n: int) -> str:
    """'w0000 w0001 ...' — every word unique, so overlap can be checked exactly."""
    return " ".join(f"w{i:04d}" for i in range(n))


def test_long_text_produces_multiple_chunks() -> None:
    """Text well over 800 chars → more than one chunk."""
    text = _numbered_words(600)  # ~3600 chars

    assert len(chunk_content(text)) > 1


def test_chunks_do_not_exceed_chunk_size() -> None:
    """Every chunk is ≤ CHUNK_SIZE, even for a run with no whitespace to split on."""
    text = _numbered_words(600) + "\n\n" + "x" * 2000

    chunks = chunk_content(text)

    assert chunks
    assert all(len(c) <= CHUNK_SIZE for c in chunks)


def test_short_text_is_single_chunk() -> None:
    """Text under 800 chars → exactly one chunk equal to the input."""
    text = "To reset your password, open Settings and choose 'Forgot password'."

    assert chunk_content(text) == [text]


def test_consecutive_chunks_overlap() -> None:
    """The start of each chunk repeats the end of the previous one (FR-2 overlap)."""
    chunks = chunk_content(_numbered_words(600))

    for prev, nxt in pairwise(chunks):
        first_word = nxt.split()[0]
        assert first_word in prev.split()


def test_paragraph_boundaries_are_preferred() -> None:
    """Two paragraphs that each fit but not together are split exactly between them."""
    p1 = "Refunds. " + "a " * 300  # ~610 chars
    p2 = "Duplicate charges. " + "b " * 300
    text = f"{p1.strip()}\n\n{p2.strip()}"

    assert chunk_content(text) == [p1.strip(), p2.strip()]


def test_blank_content_gives_no_chunks() -> None:
    """Whitespace-only content → []; create_article must handle that case."""
    assert chunk_content("   \n\n  ") == []
