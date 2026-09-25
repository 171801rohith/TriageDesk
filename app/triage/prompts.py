"""Prompt templates for the two LLM steps, versioned together.

`PROMPT_VERSION` is stored on every `triage_runs` row — bump it whenever
any prompt wording changes.
"""

from langchain_core.prompts import ChatPromptTemplate

PROMPT_VERSION = "v1"

# TODO: refine wording (these are the starting points from implement_1.md §5c).
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
                "Cite the article ids you used. If the passages don't answer the "
                "question, say what's missing and give low confidence.\n\n{passages}"
            ),
        ),
        ("human", "Category: {category}\nSubject: {subject}\n\n{body}"),
    ]
)
