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

    With no draft, only NO_RELEVANT_KB is reported for the draft rules: the
    draft-quality checks are about a draft that exists, not one that was skipped.
    """
    reasons: list[str] = []

    if classification.priority == "urgent":
        reasons.append(URGENT_PRIORITY)
    if classification.sentiment == "negative" and classification.priority == "high":
        reasons.append(NEGATIVE_HIGH_PRIORITY)

    if draft is None:
        reasons.append(NO_RELEVANT_KB)
    else:
        if draft.confidence < confidence_threshold:
            reasons.append(LOW_CONFIDENCE)
        retrieved_ids = {chunk.article_id for chunk in retrieved}
        if any(article_id not in retrieved_ids for article_id in draft.cited_article_ids):
            reasons.append(UNKNOWN_CITATION)  # possible hallucinated citation
        if not draft.reply.strip() or not draft.cited_article_ids:
            reasons.append(EMPTY_REPLY)

    return ("needs_review" if reasons else "auto_ready"), reasons
