"""FastAPI application: routers under `/api/v1`, request logging, domain-exception handlers,
and the web UI (static files) at `/`.
"""

import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path

from fastapi import FastAPI, Request, Response, status
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.core.exceptions import Conflict, NotFound
from app.core.logging import configure_logging, request_id_var
from app.health.router import router as health_router
from app.kb.router import router as kb_router
from app.tickets.router import router as tickets_router

API_PREFIX = "/api/v1"
REQUEST_ID_HEADER = "X-Request-ID"
STATIC_DIR = Path(__file__).parent / "static"

logger = logging.getLogger("app.request")


def _error(status_code: int, exc: Exception) -> JSONResponse:
    """Uniform error body: `{"detail": "..."}` (requirements §5)."""
    return JSONResponse(status_code=status_code, content={"detail": str(exc)})


async def _log_requests(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """One structured line per request with method, path, status and duration (NFR-5).

    Reuses an incoming X-Request-ID (so a caller can correlate) or makes one, and
    echoes it back in the response header.
    """
    request_id = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex[:12]
    token = request_id_var.set(request_id)
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception(
            "request failed", extra={"method": request.method, "path": request.url.path}
        )
        raise
    else:
        response.headers[REQUEST_ID_HEADER] = request_id
        logger.info(
            "request",
            extra={
                "method": request.method,
                "path": request.url.path,  # path only: query strings could carry customer data
                "status": response.status_code,
                "duration_ms": round((time.perf_counter() - start) * 1000, 1),
            },
        )
        return response
    finally:
        request_id_var.reset(token)


def create_app() -> FastAPI:
    """Build the FastAPI app and wire routers, middleware and exception handlers."""
    configure_logging()
    app = FastAPI(title="TriageDesk")
    app.middleware("http")(_log_requests)

    app.include_router(health_router, prefix=API_PREFIX)
    app.include_router(kb_router, prefix=API_PREFIX)
    app.include_router(tickets_router, prefix=API_PREFIX)

    @app.exception_handler(NotFound)
    def _not_found(_: Request, exc: NotFound) -> JSONResponse:
        return _error(status.HTTP_404_NOT_FOUND, exc)

    @app.exception_handler(Conflict)
    def _conflict(_: Request, exc: Conflict) -> JSONResponse:
        return _error(status.HTTP_409_CONFLICT, exc)

    # Mounted LAST: routes match in order, so /api/v1/*, /docs and /openapi.json win
    # and everything else falls through to the UI (index.html for "/").
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="web")
    return app


app = create_app()
