"""Deterministic business rules that decide `auto_ready` vs `needs_review` (FR-12).

Pure function, no LLM, no I/O — so it is fully unit-testable.
"""

from app.triage.llm_schemas import Classification, DraftReply, RetrievedChunk, TriageStatus

# Reason codes stored in `tickets.review_reasons` / `TriageResult.reasons`.
URGENT_PRIORITY = "urgent_priority"
NEGATIVE_HIGH_PRIORITY = "negative_high_priority"
LOW_CONFIDENCE = "low_confidence"
UNKNOWN_CITATION = "unknown_citation"
EMPTY_REPLY = "empty_reply"
NO_RELEVANT_KB = "no_relevant_kb"
LLM_ERROR = "llm_error"  # set by the workflow, not by `evaluate`


def evaluate(
    classification: Classification,
    draft: DraftReply | None,
    retrieved: list[RetrievedChunk],
    confidence_threshold: float,
) -> tuple[TriageStatus, list[str]]:
    """Apply every FR-12 rule and collect all triggered reasons.

    Args:
        classification: Step 1 output.
        draft: Step 3 output, or None when drafting was skipped (FR-11).
        retrieved: Chunks that passed the distance filter in step 2.
        confidence_threshold: `Settings.confidence_threshold`.

    Returns:
        ``("needs_review", reasons)`` if any rule fired, else ``("auto_ready", [])``.

    TODO: one `if` per rule, appending a reason code each time:
        - priority == "urgent"                         → URGENT_PRIORITY
        - sentiment == "negative" and priority == "high" → NEGATIVE_HIGH_PRIORITY
        - draft is None (no chunk passed threshold)    → NO_RELEVANT_KB
        - draft.confidence < confidence_threshold      → LOW_CONFIDENCE
        - any cited id not in {c.article_id for c in retrieved} → UNKNOWN_CITATION
        - draft.reply empty or no citations            → EMPTY_REPLY
    """
    raise NotImplementedError("guardrails.evaluate")
