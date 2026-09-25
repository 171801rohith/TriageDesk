"""Basic structured logging setup (NFR-5).

API keys must never be logged (NFR-6).
"""

import logging


def configure_logging(level: int | str = logging.INFO) -> None:
    """Configure root logging for the app.

    Minimal plain-text config so the app runs; replace with structured output.

    TODO: emit structured (key=value or JSON) log lines, e.g. via a custom
          `logging.Formatter`, and include a per-request id.
    """
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
