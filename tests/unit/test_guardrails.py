"""One test per FR-12 rule plus an all-clear case. Pure Python, no LLM."""

from collections.abc import Callable

import pytest

from app.triage import guardrails
from app.triage.guardrails import evaluate
from app.triage.llm_schemas import Classification, DraftReply, RetrievedChunk

THRESHOLD = 0.7

MakeCls = Callable[..., Classification]
MakeDraft = Callable[..., DraftReply]
MakeChunk = Callable[..., RetrievedChunk]


def test_all_clear_is_auto_ready(
    make_classification: MakeCls, make_draft: MakeDraft, make_chunk: MakeChunk
) -> None:
    """Medium priority, confident draft citing a retrieved article → auto_ready, no reasons."""
    status, reasons = evaluate(make_classification(), make_draft(), [make_chunk()], THRESHOLD)

    assert (status, reasons) == ("auto_ready", [])


@pytest.mark.parametrize(
    ("priority", "sentiment", "expected"),
    [
        ("urgent", "neutral", [guardrails.URGENT_PRIORITY]),
        ("high", "negative", [guardrails.NEGATIVE_HIGH_PRIORITY]),
        ("high", "neutral", []),  # high alone is fine
        ("medium", "negative", []),  # negative alone is fine
    ],
)
def test_priority_and_sentiment_rules(
    make_classification: MakeCls,
    make_draft: MakeDraft,
    make_chunk: MakeChunk,
    priority: str,
    sentiment: str,
    expected: list[str],
) -> None:
    """urgent → urgent_priority; negative AND high → negative_high_priority."""
    cls = make_classification(priority=priority, sentiment=sentiment)

    _, reasons = evaluate(cls, make_draft(), [make_chunk()], THRESHOLD)

    assert reasons == expected


def test_low_confidence_needs_review(
    make_classification: MakeCls, make_draft: MakeDraft, make_chunk: MakeChunk
) -> None:
    """confidence below threshold → "low_confidence"; exactly at threshold passes."""
    _, below = evaluate(make_classification(), make_draft(confidence=0.69), [make_chunk()], 0.7)
    _, at = evaluate(make_classification(), make_draft(confidence=0.7), [make_chunk()], 0.7)

    assert below == [guardrails.LOW_CONFIDENCE]
    assert at == []


def test_unknown_citation_needs_review(
    make_classification: MakeCls, make_draft: MakeDraft, make_chunk: MakeChunk
) -> None:
    """Cited id not among retrieved article ids → "unknown_citation"."""
    draft = make_draft(cited_article_ids=[1, 99])

    status, reasons = evaluate(make_classification(), draft, [make_chunk(article_id=1)], THRESHOLD)

    assert status == "needs_review"
    assert reasons == [guardrails.UNKNOWN_CITATION]


@pytest.mark.parametrize(
    "overrides",
    [{"reply": "   "}, {"cited_article_ids": []}],
    ids=["blank-reply", "no-citations"],
)
def test_empty_reply_or_no_citations_needs_review(
    make_classification: MakeCls,
    make_draft: MakeDraft,
    make_chunk: MakeChunk,
    overrides: dict[str, object],
) -> None:
    """Empty reply or empty cited_article_ids → "empty_reply"."""
    _, reasons = evaluate(make_classification(), make_draft(**overrides), [make_chunk()], THRESHOLD)

    assert reasons == [guardrails.EMPTY_REPLY]


def test_no_draft_is_no_relevant_kb(make_classification: MakeCls) -> None:
    """draft=None and nothing retrieved → only "no_relevant_kb" (not empty_reply too)."""
    status, reasons = evaluate(make_classification(), None, [], THRESHOLD)

    assert (status, reasons) == ("needs_review", [guardrails.NO_RELEVANT_KB])


def test_multiple_reasons_are_all_reported(
    make_classification: MakeCls, make_draft: MakeDraft, make_chunk: MakeChunk
) -> None:
    """Several rules firing at once → every reason is listed, in rule order."""
    cls = make_classification(priority="urgent")
    draft = make_draft(confidence=0.2, cited_article_ids=[42])

    _, reasons = evaluate(cls, draft, [make_chunk(article_id=1)], THRESHOLD)

    assert reasons == [
        guardrails.URGENT_PRIORITY,
        guardrails.LOW_CONFIDENCE,
        guardrails.UNKNOWN_CITATION,
    ]
