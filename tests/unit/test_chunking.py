"""KB chunking (FR-2)."""

import pytest

TODO = pytest.mark.skip(reason="TODO: implement kb.service.chunk_content first")


@TODO
def test_long_text_produces_multiple_chunks() -> None:
    """Text well over 800 chars → more than one chunk."""


@TODO
def test_chunks_do_not_exceed_chunk_size() -> None:
    """Every chunk is ≤ CHUNK_SIZE characters."""


@TODO
def test_short_text_is_single_chunk() -> None:
    """Text under 800 chars → exactly one chunk equal to the input."""
