"""TriageWorkflow with `RunnableLambda` fakes — no network, no DB."""

import pytest

TODO = pytest.mark.skip(reason="TODO: implement TriageWorkflow.run first")


@TODO
def test_happy_path_is_auto_ready() -> None:
    """Good classification + relevant chunk + confident cited draft → auto_ready."""


@TODO
def test_urgent_ticket_needs_review() -> None:
    """Classifier returns priority=urgent → needs_review."""


@TODO
def test_empty_search_skips_draft() -> None:
    """No chunk under the distance threshold → drafter never called, "no_relevant_kb"."""


@TODO
def test_classifier_error_is_llm_error() -> None:
    """Classifier raises → needs_review, "llm_error", error message recorded, no exception."""


@TODO
def test_citation_not_in_retrieved_is_unknown_citation() -> None:
    """Draft cites an article that wasn't retrieved → "unknown_citation"."""


@TODO
def test_step_timings_recorded() -> None:
    """Each executed step has an entry in step_timings."""
