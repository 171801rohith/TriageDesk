"""Structured key=value logging with a per-request id (NFR-5).

Every line looks like:
    ts=2026-10-03T10:15:02 level=INFO logger=app.request request_id=3f9c1a msg="request" ...

The request id lives in a ContextVar, so log lines written anywhere while a
request is handled (services, workflow) carry it — FastAPI runs sync endpoints
in a worker thread, and that thread inherits the context.

Never log request bodies or secrets: tickets contain customer text and
`Settings.google_api_key` is a SecretStr (NFR-6).
"""

import logging
from contextvars import ContextVar

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

# Attributes every LogRecord has; anything else came from `extra=` and is printed.
_STANDARD_ATTRS = set(logging.makeLogRecord({}).__dict__) | {"message", "asctime", "request_id"}


class _RequestIdFilter(logging.Filter):
    """Stamp the current request id (or "-") onto every record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


class KeyValueFormatter(logging.Formatter):
    """`key=value` lines: greppable by humans, parseable by log tools."""

    def format(self, record: logging.LogRecord) -> str:
        fields = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "request_id": getattr(record, "request_id", "-"),
            "msg": record.getMessage(),
        }
        fields |= {k: v for k, v in record.__dict__.items() if k not in _STANDARD_ATTRS}
        line = " ".join(f"{key}={_quote(value)}" for key, value in fields.items())
        if record.exc_info:
            line += "\n" + self.formatException(record.exc_info)
        return line


def _quote(value: object) -> str:
    text = str(value)
    if not text or any(ch in text for ch in ' ="'):
        return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return text


def configure_logging(level: int | str = logging.INFO) -> None:
    """Install the key=value handler on the root logger (safe to call repeatedly)."""
    root = logging.getLogger()
    root.setLevel(level)
    if any(getattr(h, "_triagedesk", False) for h in root.handlers):
        return  # already configured, e.g. create_app() called twice in tests

    handler = logging.StreamHandler()
    handler.setFormatter(KeyValueFormatter())
    handler.addFilter(_RequestIdFilter())
    handler._triagedesk = True  # type: ignore[attr-defined]
    root.addHandler(handler)
