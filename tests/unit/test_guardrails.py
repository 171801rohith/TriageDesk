"""One test per FR-12 rule plus an all-clear case. Pure Python, no LLM."""

import pytest

TODO = pytest.mark.skip(reason="TODO: implement guardrails.evaluate first")


@TODO
def test_all_clear_is_auto_ready() -> None:
    """Medium priority, confident draft citing a retrieved article → auto_ready, no reasons."""


@TODO
def test_urgent_priority_needs_review() -> None:
    """priority=urgent → needs_review with "urgent_priority"."""


@TODO
def test_negative_and_high_priority_needs_review() -> None:
    """sentiment=negative and priority=high → "negative_high_priority"."""


@TODO
def test_low_confidence_needs_review() -> None:
    """confidence below threshold → "low_confidence"."""


@TODO
def test_unknown_citation_needs_review() -> None:
    """Cited id not among retrieved article ids → "unknown_citation"."""


@TODO
def test_empty_reply_or_no_citations_needs_review() -> None:
    """Empty reply or empty cited_article_ids → "empty_reply"."""


@TODO
def test_no_draft_is_no_relevant_kb() -> None:
    """draft=None and nothing retrieved → "no_relevant_kb"."""


@TODO
def test_multiple_reasons_are_all_reported() -> None:
    """Several rules firing at once → every reason is listed."""
