"""FastAPI application factory: routers, static SPA mount, error envelopes."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from tts import __version__
from tts.api import ROUTERS
from tts.api.errors import AppError, error_envelope
from tts.config import Settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup hook placeholder; later tasks attach bootstrap work here."""
    settings: Settings = app.state.settings
    logger.info("tts %s starting on %s:%s", __version__, settings.host, settings.port)
    yield
    logger.info("tts stopped")


def _frontend_dist_dir() -> Path | None:
    """Locate the built frontend, in the repo checkout or the installed wheel."""
    candidates = (
        Path(__file__).resolve().parents[2] / "frontend" / "dist",
        Path(__file__).resolve().parent / "frontend_dist",
    )
    return next((path for path in candidates if path.is_dir()), None)


def _first_validation_problem(exc: RequestValidationError) -> tuple[str, str]:
    errors = exc.errors()
    if not errors:
        return "request", "the request body could not be validated"
    first = errors[0]
    location = [str(part) for part in first["loc"] if part not in ("body", "query", "path")]
    return ".".join(location) or "request", first["msg"]


def register_error_handlers(app: FastAPI) -> None:
    """Install the section 9.1 error envelope for every failure mode."""
    app.add_exception_handler(AppError, _handle_app_error)
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
    app.add_exception_handler(StarletteHTTPException, _handle_http_exception)


async def _handle_app_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, AppError)
    logger.debug("API error %s on %s", exc.code, request.url.path)
    return JSONResponse(status_code=exc.status, content=exc.to_envelope())


async def _handle_validation_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    field, reason = _first_validation_problem(exc)
    logger.debug("Invalid request on %s: %s", request.url.path, reason)
    return JSONResponse(
        status_code=422,
        content=error_envelope(
            "OUT_OF_RANGE",
            f"The request is invalid: {reason}",
            {"field": field, "reason": reason},
        ),
    )


async def _handle_http_exception(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    if exc.status_code in (404, 405):
        return JSONResponse(
            status_code=404,
            content=error_envelope("NOT_FOUND", "The requested page or API route does not exist."),
        )
    logger.error("Unhandled HTTP error %s on %s", exc.status_code, request.url.path)
    return JSONResponse(
        status_code=500,
        content=error_envelope("INTERNAL_ERROR", "Something went wrong. Please try again."),
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the application; tests may inject explicit settings."""
    app = FastAPI(title="tts", version=__version__, lifespan=_lifespan)
    app.state.settings = settings if settings is not None else Settings.load()

    for router in ROUTERS:
        app.include_router(router, prefix="/api")

    register_error_handlers(app)

    dist_dir = _frontend_dist_dir()
    if dist_dir is not None:
        app.mount("/", StaticFiles(directory=dist_dir, html=True), name="frontend")
    else:
        logger.info("Frontend build not found; serving the API only")

    return app
