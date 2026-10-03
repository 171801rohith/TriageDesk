"""TriageWorkflow with `RunnableLambda` fakes — no network, no DB."""

from collections.abc import Callable

import pytest

from app.triage import guardrails
from app.triage.llm_schemas import Classification, DraftReply, RetrievedChunk
from app.triage.workflow import TriageWorkflow

MakeWorkflow = Callable[..., TriageWorkflow]


def _boom(_: object) -> None:
    raise TimeoutError("boom")


@pytest.fixture
def billing(make_classification: Callable[..., Classification]) -> Classification:
    return make_classification()


@pytest.fixture
def chunk(make_chunk: Callable[..., RetrievedChunk]) -> RetrievedChunk:
    return make_chunk(article_id=1, distance=0.2)


@pytest.fixture
def good_draft(make_draft: Callable[..., DraftReply]) -> DraftReply:
    return make_draft(cited_article_ids=[1], confidence=0.9)


def test_happy_path_is_auto_ready(
    make_workflow: MakeWorkflow,
    billing: Classification,
    chunk: RetrievedChunk,
    good_draft: DraftReply,
) -> None:
    """Good classification + relevant chunk + confident cited draft → auto_ready."""
    drafter_inputs: list[dict] = []

    def draft(inp: dict) -> DraftReply:
        drafter_inputs.append(inp)
        return good_draft

    wf = make_workflow(classify=lambda _: billing, draft=draft, search=lambda _: [chunk])

    result = wf.run("Charged twice", "Please refund one.")

    assert (result.status, result.reasons, result.error) == ("auto_ready", [], None)
    assert result.classification == billing
    assert result.draft == good_draft
    assert result.retrieved == [chunk]
    # The drafter sees the passage with its citable id and the classified category.
    assert "[article_id=1]" in drafter_inputs[0]["passages"]
    assert drafter_inputs[0]["category"] == "billing"


def test_urgent_ticket_needs_review(
    make_workflow: MakeWorkflow,
    make_classification: Callable[..., Classification],
    chunk: RetrievedChunk,
    good_draft: DraftReply,
) -> None:
    """Classifier returns priority=urgent → needs_review."""
    urgent = make_classification(priority="urgent")
    wf = make_workflow(
        classify=lambda _: urgent, draft=lambda _: good_draft, search=lambda _: [chunk]
    )

    result = wf.run("URGENT: production is down", "All users affected.")

    assert result.status == "needs_review"
    assert result.reasons == [guardrails.URGENT_PRIORITY]


def test_empty_search_skips_draft(
    make_workflow: MakeWorkflow,
    make_chunk: Callable[..., RetrievedChunk],
    billing: Classification,
) -> None:
    """No chunk under the distance threshold → drafter never called, "no_relevant_kb"."""
    far = make_chunk(distance=0.9)  # above the 0.5 threshold → filtered out
    calls: list[dict] = []
    wf = make_workflow(classify=lambda _: billing, draft=calls.append, search=lambda _: [far])

    result = wf.run("Gift cards in Brazil?", "Do you sell them?")

    assert calls == []
    assert result.draft is None
    assert result.retrieved == []
    assert result.reasons == [guardrails.NO_RELEVANT_KB]
    assert "draft" not in result.step_timings


def test_classifier_error_is_llm_error(make_workflow: MakeWorkflow, chunk: RetrievedChunk) -> None:
    """Classifier raises → needs_review, "llm_error", error message recorded, no exception."""
    wf = make_workflow(classify=_boom, draft=_boom, search=lambda _: [chunk])

    result = wf.run("Anything", "Anything")

    assert result.status == "needs_review"
    assert result.reasons == [guardrails.LLM_ERROR]
    assert result.error == "TimeoutError: boom"
    assert result.classification is None
    assert "classify" in result.step_timings  # failed step is still timed


def test_drafter_error_keeps_earlier_results(
    make_workflow: MakeWorkflow, billing: Classification, chunk: RetrievedChunk
) -> None:
    """A late failure still returns the classification and retrieved chunks for the audit log."""
    wf = make_workflow(classify=lambda _: billing, draft=_boom, search=lambda _: [chunk])

    result = wf.run("Charged twice", "Please refund one.")

    assert result.reasons == [guardrails.LLM_ERROR]
    assert result.classification == billing
    assert result.retrieved == [chunk]
    assert result.draft is None


def test_citation_not_in_retrieved_is_unknown_citation(
    make_workflow: MakeWorkflow,
    make_draft: Callable[..., DraftReply],
    billing: Classification,
    chunk: RetrievedChunk,
) -> None:
    """Draft cites an article that wasn't retrieved → "unknown_citation"."""
    hallucinated = make_draft(cited_article_ids=[1, 99])
    wf = make_workflow(
        classify=lambda _: billing, draft=lambda _: hallucinated, search=lambda _: [chunk]
    )

    result = wf.run("Charged twice", "Please refund one.")

    assert result.reasons == [guardrails.UNKNOWN_CITATION]


def test_step_timings_recorded(
    make_workflow: MakeWorkflow,
    billing: Classification,
    chunk: RetrievedChunk,
    good_draft: DraftReply,
) -> None:
    """Each executed step has a non-negative entry in step_timings (ms)."""
    wf = make_workflow(
        classify=lambda _: billing, draft=lambda _: good_draft, search=lambda _: [chunk]
    )

    timings = wf.run("Charged twice", "Please refund one.").step_timings

    assert set(timings) == {"classify", "retrieve", "draft", "guardrails"}
    assert all(ms >= 0 for ms in timings.values())
