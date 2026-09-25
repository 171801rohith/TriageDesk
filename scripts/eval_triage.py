"""Offline classification eval on `data/eval_tickets.jsonl` for the active provider (F9).

Each line: {"subject": ..., "body": ..., "category": "billing", "priority": "medium"}
No DB needed — only the classifier chain is exercised.

Usage:
    python scripts/eval_triage.py
"""

from dataclasses import dataclass
from pathlib import Path

EVAL_FILE = Path(__file__).resolve().parent.parent / "data" / "eval_tickets.jsonl"


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
    total: int
    category_accuracy: float
    priority_accuracy: float
    avg_latency_ms: float
    mistakes: list[str]


def load_eval_tickets(path: Path = EVAL_FILE) -> list[EvalTicket]:
    """Read the JSONL file into `EvalTicket`s.

    TODO: implement.
    """
    raise NotImplementedError("load_eval_tickets")


def run_eval(tickets: list[EvalTicket]) -> EvalReport:
    """Classify every ticket with `build_classifier(get_chat_model(0))` and score it.

    TODO: time each call, compare category/priority, collect a confusion list of mistakes.
    """
    raise NotImplementedError("run_eval")


def print_report(report: EvalReport) -> None:
    """Print per-field accuracy, mistakes and average latency.

    TODO: implement.
    """
    raise NotImplementedError("print_report")


def main() -> None:
    """Entry point."""
    print_report(run_eval(load_eval_tickets()))


if __name__ == "__main__":
    main()
