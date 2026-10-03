"""The fixed 4-step triage pipeline: classify → retrieve → draft → guardrails.

Explicit pipeline, not an agent (architecture.md §3.1, §5.4). Chains and the
search function are injected, so the workflow runs in tests with
`RunnableLambda` fakes and no network or DB.
"""

import logging
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager

from langchain_core.language_models import BaseChatModel
from langchain_core.runnables import Runnable

from app.core.config import Settings
from app.triage import guardrails
from app.triage.llm_schemas import Classification, DraftReply, RetrievedChunk, TriageResult
from app.triage.prompts import CLASSIFY_PROMPT, DRAFT_PROMPT

logger = logging.getLogger(__name__)

SearchFn = Callable[[str], list[RetrievedChunk]]


def build_classifier(chat_model: BaseChatModel) -> Runnable[dict, Classification]:
    """Compose `CLASSIFY_PROMPT | chat_model.with_structured_output(Classification)`.

    The result's `.invoke({"subject", "body"})` returns a validated `Classification`
    or raises — never free text to parse.
    """
    return CLASSIFY_PROMPT | chat_model.with_structured_output(Classification, method="json_schema")


def build_drafter(chat_model: BaseChatModel) -> Runnable[dict, DraftReply]:
    """Compose `DRAFT_PROMPT | chat_model.with_structured_output(DraftReply)`.

    Input keys: category, subject, body, passages.
    """
    return DRAFT_PROMPT | chat_model.with_structured_output(DraftReply, method="json_schema")


def _format_passages(retrieved: list[RetrievedChunk]) -> str:
    """Render chunks as `[article_id=3] Title\\n<text>` blocks for DRAFT_PROMPT.

    The id is in the text so the model can cite it; guardrails then check that
    every cited id really was retrieved.
    """
    return "\n\n".join(f"[article_id={c.article_id}] {c.title}\n{c.text}" for c in retrieved)


@contextmanager
def _timed(timings: dict[str, float], step: str) -> Iterator[None]:
    """Record a step's wall time in ms — also when it raises, so failures show where."""
    start = time.perf_counter()
    try:
        yield
    finally:
        timings[step] = round((time.perf_counter() - start) * 1000, 1)


class TriageWorkflow:
    """Runs the four triage steps in order and times each one."""

    def __init__(
        self,
        classifier: Runnable[dict, Classification],
        drafter: Runnable[dict, DraftReply],
        search_fn: SearchFn,
        settings: Settings,
    ) -> None:
        self.classifier = classifier
        self.drafter = drafter
        self.search_fn = search_fn
        self.settings = settings

    def run(self, subject: str, body: str) -> TriageResult:
        """Triage one ticket. Never raises for LLM failures (FR-13).

        Any exception — timeout, API error, invalid structured output, search
        failure — becomes `needs_review` + `llm_error`, keeping whatever the
        steps before the failure produced.
        """
        timings: dict[str, float] = {}
        classification: Classification | None = None
        retrieved: list[RetrievedChunk] = []
        draft: DraftReply | None = None

        try:
            with _timed(timings, "classify"):
                classification = self.classifier.invoke({"subject": subject, "body": body})

            with _timed(timings, "retrieve"):
                max_distance = self.settings.retrieval_max_distance
                retrieved = [
                    c for c in self.search_fn(f"{subject}\n{body}") if c.distance <= max_distance
                ]

            if retrieved:  # FR-11: nothing relevant → skip drafting entirely
                with _timed(timings, "draft"):
                    draft = self.drafter.invoke(
                        {
                            "category": classification.category,
                            "subject": subject,
                            "body": body,
                            "passages": _format_passages(retrieved),
                        }
                    )

            with _timed(timings, "guardrails"):
                status, reasons = guardrails.evaluate(
                    classification, draft, retrieved, self.settings.confidence_threshold
                )
        except Exception as exc:
            # No ticket text in logs (NFR-6); the request_id ties this line to its request.
            logger.exception("Triage failed")
            return TriageResult(
                status="needs_review",
                reasons=[guardrails.LLM_ERROR],
                classification=classification,
                draft=draft,
                retrieved=retrieved,
                step_timings=timings,
                error=f"{type(exc).__name__}: {exc}",
            )

        return TriageResult(
            status=status,
            reasons=reasons,
            classification=classification,
            draft=draft,
            retrieved=retrieved,
            step_timings=timings,
        )
