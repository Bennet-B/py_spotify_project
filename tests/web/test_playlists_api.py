"""API tests for the playlists/jobs/system routers via TestClient with a fake SpotifyClient."""

from __future__ import annotations

import time
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from spotify_project.cache import FileCache
from spotify_project.client import ProgressFn
from spotify_project.models import Artist, Playlist, PlaylistSummary, Track, User
from spotify_project.web.app import create_app
from spotify_project.web.dataset import DatasetStore
from spotify_project.web.deps import get_cache, get_client, get_dataset_store, get_job_registry
from spotify_project.web.jobs import JobRegistry


def _make_playlist(playlist_id: str, name: str) -> Playlist:
    """Build a small fully-enriched Playlist with two tracks and tagged artists."""
    rock = Artist(id="a1", name="Artist One", tags=("rock", "seen live"))
    jazz = Artist(id="a2", name="Artist Two", tags=("jazz",))
    tracks = (
        Track(
            id="t1",
            name="Track 1",
            artists=(rock,),
            album_name="Album A",
            release_date="2020-01-01",
            duration_ms=200_000,
            explicit=False,
            added_at=datetime(2024, 6, 1, tzinfo=UTC),
            is_local=False,
        ),
        Track(
            id="t2",
            name="Track 2",
            artists=(rock, jazz),
            album_name="Album B",
            release_date="1999-05-05",
            duration_ms=180_000,
            explicit=True,
            added_at=datetime(2024, 7, 1, tzinfo=UTC),
            is_local=False,
        ),
    )
    return Playlist(id=playlist_id, name=name, owner_display_name="Bennet", public=False, collaborative=False, description="", tracks=tracks)


class FakeSpotifyClient:
    """Stands in for SpotifyClient behind the dependency seam; records calls and drives the progress callback."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def fetch_current_user(self) -> User:
        self.calls.append("fetch_current_user")
        return User(id="u1", display_name="Bennet", email=None)

    def fetch_user_playlists(self) -> list[PlaylistSummary]:
        self.calls.append("fetch_user_playlists")
        return [PlaylistSummary(id="pl1", name="Playlist 1", owner_name="Bennet", track_count=2, public=True)]

    def fetch_playlist(self, playlist_id: str, *, force_refresh: bool = False, on_progress: ProgressFn | None = None) -> Playlist:
        self.calls.append(f"fetch_playlist:{playlist_id}:force={force_refresh}")
        if on_progress is not None:
            on_progress("tracks", 2, None)
            on_progress("artists", 2, 2)
        return _make_playlist(playlist_id, "Playlist 1")

    def fetch_liked_songs(self, *, force_refresh: bool = False, on_progress: ProgressFn | None = None) -> Playlist:
        self.calls.append(f"fetch_liked_songs:force={force_refresh}")
        if on_progress is not None:
            on_progress("tracks", 2, None)
        return _make_playlist("__liked__", "Liked Songs")


@pytest.fixture
def api(tmp_path: Path) -> Iterator[tuple[TestClient, FakeSpotifyClient, DatasetStore]]:
    """A TestClient wired to a fake Spotify client, fresh registry/store, and a tmp cache."""
    app = create_app()
    fake = FakeSpotifyClient()
    registry = JobRegistry(max_workers=1, max_jobs=10)
    store = DatasetStore()
    cache = FileCache(root=tmp_path)
    app.dependency_overrides[get_client] = lambda: fake
    app.dependency_overrides[get_cache] = lambda: cache
    app.dependency_overrides[get_job_registry] = lambda: registry
    app.dependency_overrides[get_dataset_store] = lambda: store
    with TestClient(app) as test_client:
        yield test_client, fake, store
    registry.shutdown()


def _poll_job(test_client: TestClient, job_id: str, *, timeout: float = 5.0) -> dict[str, Any]:
    """Poll GET /api/jobs/{id} until a terminal status, failing the test on timeout."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = test_client.get(f"/api/jobs/{job_id}")
        assert response.status_code == 200
        body: dict[str, Any] = response.json()
        if body["status"] in ("done", "error"):
            return body
        time.sleep(0.01)
    pytest.fail(f"Job {job_id} did not finish within {timeout}s")


class TestSystem:
    """Health and identity endpoints."""

    def test_health(self, api: tuple[TestClient, FakeSpotifyClient, DatasetStore]) -> None:
        """GET /api/health answers without touching Spotify."""
        test_client, fake, _ = api
        response = test_client.get("/api/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
        assert fake.calls == []

    def test_me(self, api: tuple[TestClient, FakeSpotifyClient, DatasetStore]) -> None:
        """GET /api/me returns the authenticated user."""
        test_client, _, _ = api
        response = test_client.get("/api/me")
        assert response.status_code == 200
        assert response.json() == {"id": "u1", "display_name": "Bennet"}


class TestListPlaylists:
    """GET /api/playlists."""

    def test_liked_first_then_summaries(self, api: tuple[TestClient, FakeSpotifyClient, DatasetStore]) -> None:
        """The synthetic Liked Songs entry leads; real playlists follow with summary data."""
        test_client, _, _ = api
        response = test_client.get("/api/playlists")
        assert response.status_code == 200
        items = response.json()["items"]
        assert [item["id"] for item in items] == ["__liked__", "pl1"]
        liked, pl1 = items
        assert liked["is_liked"] is True
        assert liked["track_count"] is None
        assert liked["loaded"] is False
        assert pl1 == {"id": "pl1", "name": "Playlist 1", "owner_name": "Bennet", "track_count": 2, "public": True, "is_liked": False, "loaded": False, "cached_at": None}


class TestRefreshAndTracks:
    """POST /{id}/refresh job flow feeding GET /{id}/tracks."""

    def test_refresh_job_loads_dataset_then_tracks_serve(self, api: tuple[TestClient, FakeSpotifyClient, DatasetStore]) -> None:
        """A refresh job completes with progress and track_count; the tracks endpoint then serves flattened rows."""
        test_client, fake, store = api
        response = test_client.post("/api/playlists/pl1/refresh", json={"force": False})
        assert response.status_code == 202
        job = _poll_job(test_client, response.json()["job_id"])

        assert job["status"] == "done"
        assert job["result"] == {"playlist_id": "pl1", "track_count": 2}
        assert job["progress"]["phase"] == "artists"
        assert "fetch_playlist:pl1:force=False" in fake.calls
        assert store.get("pl1") is not None

        tracks_response = test_client.get("/api/playlists/pl1/tracks")
        assert tracks_response.status_code == 200
        body = tracks_response.json()
        assert body["playlist_id"] == "pl1"
        assert body["name"] == "Playlist 1"
        rows = body["tracks"]
        assert len(rows) == 2
        assert rows[0]["track_id"] == "t1"
        assert rows[0]["release_year"] == 2020
        assert rows[0]["added_at"] == "2024-06-01T00:00:00Z"
        assert rows[1]["artist_names"] == ["Artist One", "Artist Two"]
        assert rows[1]["tags"] == ["rock", "seen live", "jazz"]

    def test_refresh_liked_songs_uses_liked_fetch(self, api: tuple[TestClient, FakeSpotifyClient, DatasetStore]) -> None:
        """Refreshing __liked__ routes to fetch_liked_songs with the force flag."""
        test_client, fake, _ = api
        response = test_client.post("/api/playlists/__liked__/refresh", json={"force": True})
        assert response.status_code == 202
        job = _poll_job(test_client, response.json()["job_id"])
        assert job["status"] == "done"
        assert "fetch_liked_songs:force=True" in fake.calls

    def test_tracks_before_load_returns_409_envelope(self, api: tuple[TestClient, FakeSpotifyClient, DatasetStore]) -> None:
        """The tracks endpoint answers 409 dataset_not_loaded until a refresh job has run."""
        test_client, _, _ = api
        response = test_client.get("/api/playlists/pl1/tracks")
        assert response.status_code == 409
        error = response.json()["error"]
        assert error["code"] == "dataset_not_loaded"
        assert error["detail"] == {"playlist_id": "pl1"}


class TestJobEndpoint:
    """GET /api/jobs/{id} error path."""

    def test_unknown_job_returns_404_envelope(self, api: tuple[TestClient, FakeSpotifyClient, DatasetStore]) -> None:
        """Unknown job ids yield the enveloped 404."""
        test_client, _, _ = api
        response = test_client.get("/api/jobs/nope")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"
