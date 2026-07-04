"""Health and identity endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from ..deps import ClientDep
from ..schemas import HealthResponse, MeResponse

router = APIRouter(tags=["system"])


@router.get("/health")
def health() -> HealthResponse:
    """Liveness probe; carries no dependencies so it succeeds even before Spotify auth."""
    return HealthResponse(status="ok")


@router.get("/me")
def me(client: ClientDep) -> MeResponse:
    """Return the authenticated Spotify user's id and display name."""
    user = client.fetch_current_user()
    return MeResponse(id=user.id, display_name=user.display_name)
