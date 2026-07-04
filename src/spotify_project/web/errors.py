"""Uniform error envelope and exception handlers for the web API.

Every non-2xx response carries ``{"error": {"code", "message", "detail"}}`` so the frontend handles all failures through one code path.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from spotipy.exceptions import SpotifyException

from .dataset import DatasetNotLoadedError

logger = logging.getLogger(__name__)


class NotFoundError(LookupError):
    """Raised by routers when a requested resource (job, playlist) does not exist; mapped to HTTP 404."""


def _envelope(status_code: int, code: str, message: str, detail: Any = None) -> JSONResponse:
    """Build a uniform enveloped error response.

    Args:
        status_code: HTTP status to return.
        code: Machine-readable error code the frontend switches on.
        message: Human-readable description.
        detail: Optional JSON-serializable extra context.

    Returns:
        The enveloped JSONResponse.
    """
    return JSONResponse(status_code=status_code, content={"error": {"code": code, "message": message, "detail": detail}})


def register_error_handlers(app: FastAPI) -> None:
    """Attach exception handlers translating domain errors into enveloped HTTP responses.

    Args:
        app: The FastAPI application to register handlers on.
    """

    # The handlers below are referenced only by their decorator registration, which pyright's reportUnusedFunction does not count as a use.

    @app.exception_handler(DatasetNotLoadedError)
    async def handle_not_loaded(_: Request, exc: DatasetNotLoadedError) -> JSONResponse:  # pyright: ignore[reportUnusedFunction]
        return _envelope(409, "dataset_not_loaded", str(exc), {"playlist_id": exc.playlist_id})

    @app.exception_handler(NotFoundError)
    async def handle_not_found(_: Request, exc: NotFoundError) -> JSONResponse:  # pyright: ignore[reportUnusedFunction]
        return _envelope(404, "not_found", str(exc))

    @app.exception_handler(RequestValidationError)
    async def handle_validation(_: Request, exc: RequestValidationError) -> JSONResponse:  # pyright: ignore[reportUnusedFunction]
        return _envelope(400, "invalid_request", "Request validation failed.", exc.errors())

    @app.exception_handler(ValueError)
    async def handle_value_error(_: Request, exc: ValueError) -> JSONResponse:  # pyright: ignore[reportUnusedFunction]
        return _envelope(400, "invalid_request", str(exc))

    @app.exception_handler(SpotifyException)
    async def handle_spotify(_: Request, exc: SpotifyException) -> JSONResponse:  # pyright: ignore[reportUnusedFunction]
        logger.error("Spotify API error surfaced to a request: %s", exc)
        return _envelope(502, "spotify_error", str(exc))

    @app.exception_handler(RuntimeError)
    async def handle_runtime(_: Request, exc: RuntimeError) -> JSONResponse:  # pyright: ignore[reportUnusedFunction]
        # SpotifyClient._call raises RuntimeError for over-threshold Retry-After cooldowns; any other RuntimeError is a genuine server fault.
        if "rate-limit" in str(exc):
            return _envelope(503, "rate_limited", str(exc))
        logger.exception("Unhandled RuntimeError")
        return _envelope(500, "internal_error", str(exc))
