"""Pydantic models forming the API boundary.

The core keeps frozen dataclasses (it has no serialization concern); pydantic lives exactly here, where request validation and OpenAPI generation are the
job. The OpenAPI schema generated from these models is the source of truth for the frontend's generated TypeScript types (``npm run gen:api``).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, cast

import pandas as pd
from pydantic import BaseModel

from .jobs import JobSnapshot, JobStatus


class HealthResponse(BaseModel):
    """Liveness probe body."""

    status: Literal["ok"]


class MeResponse(BaseModel):
    """The authenticated Spotify user."""

    id: str
    display_name: str


class PlaylistItem(BaseModel):
    """One sidebar entry; id ``__liked__`` is the synthetic Liked Songs pseudo-playlist.

    ``track_count`` is None when unknown (Liked Songs before its first load). ``cached_at`` is the raw-response cache write time, or None when uncached/stale.
    """

    id: str
    name: str
    owner_name: str
    track_count: int | None
    public: bool
    is_liked: bool
    loaded: bool
    cached_at: datetime | None


class PlaylistsResponse(BaseModel):
    """Response of ``GET /api/playlists``."""

    items: list[PlaylistItem]


class RefreshRequest(BaseModel):
    """Body of ``POST /api/playlists/{id}/refresh``; ``force`` bypasses the response cache."""

    force: bool = False


class JobAccepted(BaseModel):
    """202 response carrying the id to poll at ``GET /api/jobs/{job_id}``."""

    job_id: str


class JobProgressOut(BaseModel):
    """Progress block of a job snapshot."""

    phase: str
    done: int
    total: int | None
    message: str


class JobErrorOut(BaseModel):
    """Error block of a failed job."""

    code: str
    message: str


class JobOut(BaseModel):
    """Response of ``GET /api/jobs/{job_id}``."""

    id: str
    kind: str
    status: JobStatus
    progress: JobProgressOut
    result: dict[str, Any] | None
    error: JobErrorOut | None

    @classmethod
    def from_snapshot(cls, snap: JobSnapshot) -> JobOut:
        """Convert a registry snapshot into the wire shape.

        Args:
            snap: The immutable snapshot returned by ``JobRegistry.get``.

        Returns:
            The corresponding response model.
        """
        error = JobErrorOut(code=snap.error_code, message=snap.error_message or "") if snap.error_code is not None else None
        progress = JobProgressOut(phase=snap.phase, done=snap.done, total=snap.total, message=snap.message)
        return cls(id=snap.id, kind=snap.kind, status=snap.status, progress=progress, result=snap.result, error=error)


class TrackRow(BaseModel):
    """One flattened track, mirroring the columns of ``PlaylistAnalyzer.from_playlist``'s DataFrame."""

    track_id: str | None
    name: str
    primary_artist_id: str | None
    primary_artist_name: str
    artist_ids: list[str]
    artist_names: list[str]
    album_name: str
    release_year: int | None
    duration_ms: int
    explicit: bool
    added_at: datetime | None
    is_local: bool
    tags: list[str]
    genres: list[str]


class TracksResponse(BaseModel):
    """Response of ``GET /api/playlists/{id}/tracks``."""

    playlist_id: str
    name: str
    tracks: list[TrackRow]


def track_rows_from_df(df: pd.DataFrame) -> list[TrackRow]:
    """Convert the flattened track DataFrame into wire-ready rows.

    Handles pandas nullability at the boundary: ``NaT`` added_at and ``pd.NA`` release_year become None; list-valued columns are copied into plain lists;
    the occasional None artist id of a local file is dropped rather than serialized.

    Args:
        df: The DataFrame produced by ``PlaylistAnalyzer.from_playlist``.

    Returns:
        One ``TrackRow`` per DataFrame row, in DataFrame order.
    """
    rows: list[TrackRow] = []
    for rec in cast("list[dict[str, Any]]", df.to_dict("records")):
        release_year = rec["release_year"]
        added_at = rec["added_at"]
        rows.append(
            TrackRow(
                track_id=rec["track_id"],
                name=rec["name"],
                primary_artist_id=rec["primary_artist_id"],
                primary_artist_name=rec["primary_artist_name"],
                artist_ids=[a for a in rec["artist_ids"] if a is not None],
                artist_names=list(rec["artist_names"]),
                album_name=rec["album_name"],
                release_year=None if pd.isna(release_year) else int(release_year),
                duration_ms=int(rec["duration_ms"]),
                explicit=bool(rec["explicit"]),
                added_at=None if pd.isna(added_at) else added_at.to_pydatetime(),
                is_local=bool(rec["is_local"]),
                tags=list(rec["tags"]),
                genres=list(rec["genres"]),
            )
        )
    return rows
