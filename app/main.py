"""FastAPI application: routers under `/api/v1` and domain-exception handlers."""

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.core.exceptions import Conflict, NotFound
from app.core.logging import configure_logging
from app.health.router import router as health_router
from app.kb.router import router as kb_router
from app.tickets.router import router as tickets_router

API_PREFIX = "/api/v1"


def _error(status_code: int, exc: Exception) -> JSONResponse:
    """Uniform error body: `{"detail": "..."}` (requirements §5)."""
    return JSONResponse(status_code=status_code, content={"detail": str(exc)})


def create_app() -> FastAPI:
    """Build the FastAPI app and wire routers + exception handlers."""
    configure_logging()
    app = FastAPI(title="TriageDesk")

    app.include_router(health_router, prefix=API_PREFIX)
    app.include_router(kb_router, prefix=API_PREFIX)
    app.include_router(tickets_router, prefix=API_PREFIX)

    @app.exception_handler(NotFound)
    def _not_found(_: Request, exc: NotFound) -> JSONResponse:
        return _error(status.HTTP_404_NOT_FOUND, exc)

    @app.exception_handler(Conflict)
    def _conflict(_: Request, exc: Conflict) -> JSONResponse:
        return _error(status.HTTP_409_CONFLICT, exc)

    # Scaffolding aid: stubs raise NotImplementedError → 501 instead of a bare 500.
    # TODO: remove once all stubs are implemented.
    @app.exception_handler(NotImplementedError)
    def _not_implemented(_: Request, exc: NotImplementedError) -> JSONResponse:
        return _error(status.HTTP_501_NOT_IMPLEMENTED, exc)

    # TODO: per-request structured logging middleware (NFR-5).
    return app


app = create_app()


