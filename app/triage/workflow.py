"""The fixed 4-step triage pipeline: classify → retrieve → draft → guardrails.

Explicit pipeline, not an agent (architecture.md §3.1, §5.4). Chains and the
search function are injected, so the workflow runs in tests with
`RunnableLambda` fakes and no network or DB.
"""

import logging
from collections.abc import Callable

from langchain_core.language_models import BaseChatModel
from langchain_core.runnables import Runnable

from app.core.config import Settings
from app.triage import guardrails  # noqa: F401  (used by the TODO implementation)
from app.triage.llm_schemas import Classification, DraftReply, RetrievedChunk, TriageResult
from app.triage.prompts import CLASSIFY_PROMPT, DRAFT_PROMPT  # noqa: F401

logger = logging.getLogger(__name__)

SearchFn = Callable[[str], list[RetrievedChunk]]


def build_classifier(chat_model: BaseChatModel) -> Runnable[dict, Classification]:
    """Compose `CLASSIFY_PROMPT | chat_model.with_structured_output(Classification)`.

    TODO: use `method="json_schema"`.
    """
    raise NotImplementedError("build_classifier")


def build_drafter(chat_model: BaseChatModel) -> Runnable[dict, DraftReply]:
    """Compose `DRAFT_PROMPT | chat_model.with_structured_output(DraftReply)`.

    TODO: use `method="json_schema"`.
    """
    raise NotImplementedError("build_drafter")


def _format_passages(retrieved: list[RetrievedChunk]) -> str:
    """Render chunks as `[article_id=3] Title\\n<text>` blocks for DRAFT_PROMPT.

    TODO: implement.
    """
    raise NotImplementedError("_format_passages")


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

        TODO (implement_1.md Phase 5d), timing each step with `time.perf_counter()`:
            1. classification = self.classifier.invoke({"subject": ..., "body": ...})
            2. retrieved = [c for c in self.search_fn(subject + "\\n" + body)
                            if c.distance <= self.settings.retrieval_max_distance]
            3. draft = self.drafter.invoke({...passages...}) if retrieved else None
            4. status, reasons = guardrails.evaluate(..., self.settings.confidence_threshold)
            On any exception: log it and return
            TriageResult(status="needs_review", reasons=[guardrails.LLM_ERROR], error=str(e), ...)
        """
        raise NotImplementedError("TriageWorkflow.run")
