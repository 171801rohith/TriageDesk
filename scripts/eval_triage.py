"""Offline classification eval on `data/eval_tickets.jsonl` for the active provider (F9).

Each line: {"subject": ..., "body": ..., "category": "billing", "priority": "medium"}
No DB needed — only the classifier chain is exercised, exactly as the API builds it.

Priority rubric used for the labels (keep new tickets consistent with it):
    low     question / how-to / feedback, nothing is broken
    medium  one user has a problem, but a workaround or normal process exists
    high    one user is blocked, money is wrong, or the customer is escalating
    urgent  outage, security incident or data loss (same rule as CLASSIFY_PROMPT)

Usage:
    uv run python scripts/eval_triage.py            # whole set
    uv run python scripts/eval_triage.py --limit 5  # quick smoke run
"""

import argparse
import json
import logging
import re
import statistics
import time
from dataclasses import dataclass
from pathlib import Path

from app.llm.providers import active_model_info, get_chat_model
from app.triage.prompts import PROMPT_VERSION
from app.triage.workflow import build_classifier

EVAL_FILE = Path(__file__).resolve().parent.parent / "data" / "eval_tickets.jsonl"
ISO_639_1 = re.compile(r"^[a-z]{2}$")


@dataclass(frozen=True)
class EvalTicket:
    """One labelled ticket."""

    subject: str
    body: str
    category: str
    priority: str


@dataclass(frozen=True)
class EvalReport:
    """Aggregate results printed at the end."""

    provider: str
    chat_model: str
    prompt_version: str
    total: int
    category_accuracy: float
    priority_accuracy: float
    errors: int
    non_iso_language: int
    avg_latency_ms: float
    median_latency_ms: float
    mistakes: list[str]


def load_eval_tickets(path: Path = EVAL_FILE) -> list[EvalTicket]:
    """Read the JSONL file into `EvalTicket`s (blank lines are ignored)."""
    with path.open(encoding="utf-8") as f:
        return [EvalTicket(**json.loads(line)) for line in f if line.strip()]


def run_eval(tickets: list[EvalTicket]) -> EvalReport:
    """Classify every ticket with `build_classifier(get_chat_model(0))` and score it.

    A call that raises (timeout, invalid structured output) counts as wrong on
    both fields — in production that ticket would land in `needs_review`.
    """
    classifier = build_classifier(get_chat_model(0))
    category_ok = priority_ok = errors = non_iso = 0
    latencies: list[float] = []
    mistakes: list[str] = []

    for i, ticket in enumerate(tickets, 1):
        start = time.perf_counter()
        try:
            got = classifier.invoke({"subject": ticket.subject, "body": ticket.body})
        except Exception as exc:  # noqa: BLE001 — scoring a failure, not handling it
            errors += 1
            mistakes.append(f"#{i} {ticket.subject!r}: ERROR {type(exc).__name__}: {exc}")
            continue
        finally:
            latencies.append((time.perf_counter() - start) * 1000)

        category_ok += got.category == ticket.category
        priority_ok += got.priority == ticket.priority
        non_iso += not ISO_639_1.match(got.language)
        for field in ("category", "priority"):
            expected, actual = getattr(ticket, field), getattr(got, field)
            if expected != actual:
                mistakes.append(f"#{i} {ticket.subject!r}: {field} {expected} -> {actual}")
        print(f"  {i:>2}/{len(tickets)}  {latencies[-1] / 1000:5.1f}s  {ticket.subject}")

    info = active_model_info()
    total = len(tickets)
    return EvalReport(
        provider=info["provider"],
        chat_model=info["chat_model"],
        prompt_version=PROMPT_VERSION,
        total=total,
        category_accuracy=category_ok / total,
        priority_accuracy=priority_ok / total,
        errors=errors,
        non_iso_language=non_iso,
        avg_latency_ms=statistics.fmean(latencies),
        median_latency_ms=statistics.median(latencies),
        mistakes=mistakes,
    )


def print_report(report: EvalReport) -> None:
    """Print per-field accuracy, mistakes, latency, and a README-ready table row."""
    r = report
    print(f"\n{r.provider} / {r.chat_model} / prompt {r.prompt_version} - {r.total} tickets")
    print(f"  category accuracy  {r.category_accuracy:6.1%}")
    print(f"  priority accuracy  {r.priority_accuracy:6.1%}")
    print(f"  errors             {r.errors}")
    print(f"  non-ISO language   {r.non_iso_language}")
    print(
        f"  latency avg/median {r.avg_latency_ms / 1000:.1f}s / {r.median_latency_ms / 1000:.1f}s"
    )
    print("\nMistakes:" if r.mistakes else "\nNo mistakes.")
    for line in r.mistakes:
        print(f"  {line}")
    print(
        "\nREADME row:\n"
        f"| {r.provider} | {r.chat_model} | {r.prompt_version} | {r.category_accuracy:.0%} "
        f"| {r.priority_accuracy:.0%} | {r.median_latency_ms / 1000:.1f} s |"
    )


def main() -> None:
    """Entry point."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--limit", type=int, help="only evaluate the first N tickets")
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING)  # keep httpx request logs out of the report
    tickets = load_eval_tickets()[: args.limit]
    print_report(run_eval(tickets))


if __name__ == "__main__":
    main()
