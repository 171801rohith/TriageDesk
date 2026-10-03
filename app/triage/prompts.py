"""Prompt templates for the two LLM steps, versioned together.

`PROMPT_VERSION` is stored on every `triage_runs` row — bump it whenever
any prompt wording changes.
"""

from langchain_core.prompts import ChatPromptTemplate

# v1.1: draft prompt states the confidence range (hermes3 once returned 2 → the
#       whole draft failed validation).
# v1.2: says what `reply` is for (hermes3 once wrote "Based on article_id=7 ...,
#       confidence=1.0" as the reply, which passed every guardrail).
# Classification wording is unchanged since v1, so the v1 eval numbers still apply.
PROMPT_VERSION = "v1.2"

# Tried and rejected (eval, hermes3:8b): a "v2" with per-category definitions and a
# four-level priority rubric scored priority 62% vs 67% for this one-liner. Measure
# with scripts/eval_triage.py before changing; see README "Evaluation".
CLASSIFY_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            (
                "You are a support triage assistant. Classify the ticket. "
                "Use 'urgent' only for outages, security issues, or data loss."
            ),
        ),
        ("human", "Subject: {subject}\n\nBody:\n{body}"),
    ]
)

# `passages` is formatted as `[article_id=3] Title\n<text>` blocks so the model can cite ids.
DRAFT_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            (
                "You write replies for a support team. Use ONLY the passages below. "
                "`reply` is the message the customer will read: greet them, answer "
                "their question in plain sentences, and keep ids and scores out of it. "
                "Cite the article ids you used. If the passages don't answer the "
                "question, say what's missing and give low confidence.\n"
                "confidence is a decimal from 0.0 (passages don't answer it) to 1.0 "
                "(passages fully answer it); never above 1.0.\n\n{passages}"
            ),
        ),
        ("human", "Category: {category}\nSubject: {subject}\n\n{body}"),
    ]
)
