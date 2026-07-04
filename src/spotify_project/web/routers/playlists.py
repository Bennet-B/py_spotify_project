"""Playlist listing, refresh jobs, and flattened track data."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter

from ...analyzer import PlaylistAnalyzer
from ...client import ProgressFn
from ..dataset import Dataset
from ..deps import CacheDep, ClientDep, DatasetStoreDep, JobRegistryDep
from ..schemas import JobAccepted, PlaylistItem, PlaylistsResponse, RefreshRequest, TracksResponse, track_rows_from_df

router = APIRouter(prefix="/playlists", tags=["playlists"])

LIKED_PLAYLIST_ID = "__liked__"


@router.get("")
def list_playlists(client: ClientDep, cache: CacheDep, store: DatasetStoreDep) -> PlaylistsResponse:
    """List the user's playlists with load/cache state, Liked Songs first.

    ``track_count`` stays None for Liked Songs until a refresh job loads it — Spotify's saved-tracks endpoint offers no cheap count without fetching pages.
    """
    me = client.fetch_current_user()
    loaded = store.loaded_ids()
    liked_dataset = store.get(LIKED_PLAYLIST_ID)
    items = [
        PlaylistItem(
            id=LIKED_PLAYLIST_ID,
            name="Liked Songs",
            owner_name=me.display_name,
            track_count=len(liked_dataset.df) if liked_dataset is not None else None,
            public=False,
            is_liked=True,
            loaded=LIKED_PLAYLIST_ID in loaded,
            cached_at=cache.cached_at("liked/me"),
        )
    ]
    items.extend(
        PlaylistItem(
            id=s.id,
            name=s.name,
            owner_name=s.owner_name,
            track_count=s.track_count,
            public=s.public,
            is_liked=False,
            loaded=s.id in loaded,
            cached_at=cache.cached_at(f"playlist/{s.id}"),
        )
        for s in client.fetch_user_playlists()
    )
    return PlaylistsResponse(items=items)


@router.post("/{playlist_id}/refresh", status_code=202)
def refresh_playlist(playlist_id: str, body: RefreshRequest, client: ClientDep, registry: JobRegistryDep, store: DatasetStoreDep) -> JobAccepted:
    """Start (or join) a background job that fetches the playlist and builds its dataset.

    Cache-warm loads also run as jobs — they finish in seconds and keep the client's flow uniform. A queued or running job for the same playlist is joined,
    not duplicated.
    """

    def run(progress: ProgressFn) -> dict[str, Any]:
        playlist = (
            client.fetch_liked_songs(force_refresh=body.force, on_progress=progress)
            if playlist_id == LIKED_PLAYLIST_ID
            else client.fetch_playlist(playlist_id, force_refresh=body.force, on_progress=progress)
        )
        df = PlaylistAnalyzer.from_playlist(playlist).df
        store.put(playlist_id, Dataset(playlist=playlist, df=df, loaded_at=datetime.now(UTC)))
        return {"playlist_id": playlist_id, "track_count": len(df)}

    job_id = registry.submit(kind="refresh", fn=run, dedupe_key=f"refresh:{playlist_id}")
    return JobAccepted(job_id=job_id)


@router.get("/{playlist_id}/tracks")
def playlist_tracks(playlist_id: str, store: DatasetStoreDep) -> TracksResponse:
    """Return the flattened track rows of a loaded playlist.

    Raises:
        DatasetNotLoadedError: Mapped to HTTP 409 when no refresh job has loaded the playlist yet.
    """
    dataset = store.require(playlist_id)
    return TracksResponse(playlist_id=playlist_id, name=dataset.playlist.name, tracks=track_rows_from_df(dataset.df))
