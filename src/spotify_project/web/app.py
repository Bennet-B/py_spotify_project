"""FastAPI application factory.

Run locally with ``uvicorn spotify_project.web.app:create_app --factory`` (see README for the full command; the server binds to 127.0.0.1 only).
Deliberately does NOT call ``spotify_project.logging_setup.configure_logging`` — that helper removes all root handlers, which would wipe uvicorn's logging config.
"""

from __future__ import annotations

from dotenv import load_dotenv
from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .errors import register_error_handlers
from .routers import analysis, insights, jobs, organizer, playlists, system

# The Vite dev server origins. In dev the frontend proxies /api to this server, but direct browser calls still work thanks to CORS.
_DEV_ORIGINS = ("http://localhost:5173", "http://127.0.0.1:5173")


def create_app() -> FastAPI:
    """Build the API application.

    Loads ``.env`` (Spotify credentials) into the process environment first, mirroring the notebook's startup, then wires middleware, error handlers, and routers.

    Returns:
        The configured FastAPI instance.
    """
    load_dotenv()
    app = FastAPI(title="Spotify Project API", version="0.1.0")
    app.add_middleware(CORSMiddleware, allow_origins=list(_DEV_ORIGINS), allow_methods=["*"], allow_headers=["*"])
    register_error_handlers(app)
    api = APIRouter(prefix="/api")
    api.include_router(system.router)
    api.include_router(playlists.router)
    api.include_router(insights.router)
    api.include_router(organizer.router)
    api.include_router(analysis.router)
    api.include_router(jobs.router)
    app.include_router(api)
    return app
