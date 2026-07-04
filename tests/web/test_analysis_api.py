"""API tests for the analysis router: scoped scan, typed scan result, sweep, and suggest-split."""

from __future__ import annotations

import time
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from spotify_project.analyzer import PlaylistAnalyzer
from spotify_project.client import ProgressFn
from spotify_project.models import Artist, Playlist, Track, User
from spotify_project.web.app import create_app
from spotify_project.web.batches import BatchStore
from spotify_project.web.dataset import Dataset, DatasetStore
from spotify_project.web.deps import get_batch_store, get_client, get_dataset_store, get_job_registry
from spotify_project.web.jobs import JobRegistry


def _track(track_id: str, name: str, genres: tuple[str, ...] = ("rock",), year: str = "2000-01-01") -> Track:
    artist = Artist(id=f"artist-{track_id}", name=f"Artist {track_id}", tags=genres)
    return Track(
        id=track_id, name=name, artists=(artist,), album_name="A", release_date=year, duration_ms=200_000, explicit=False, added_at=datetime(2024, 1, 1, tzinfo=UTC), is_local=False
    )


def _playlist(playlist_id: str, name: str, tracks: tuple[Track, ...]) -> Playlist:
    return Playlist(id=playlist_id, name=name, owner_display_name="Bennet", public=False, collaborative=False, description="", tracks=tracks)


T1, T2, T3, T4 = (_track("t1", "One"), _track("t2", "Two"), _track("t3", "Three"), _track("t4", "Four"))

LIKED = _playlist("__liked__", "Liked Songs", (T1, T2, T3, T4))
ROCK = _playlist("rock_pl", "Rock", (T1, T2))
JAZZ = _playlist("jazz_pl", "Jazz", (T2, T3))


class FakeScanClient:
    """Serves canned playlists; records mutations like the organizer fake."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []
        self.playlists = {"__liked__": LIKED, "rock_pl": ROCK, "jazz_pl": JAZZ}

    def fetch_current_user(self) -> User:
        return User(id="u1", display_name="Bennet", email=None)

    def fetch_liked_songs(self, *, force_refresh: bool = False, on_progress: ProgressFn | None = None) -> Playlist:
        return self.playlists["__liked__"]

    def fetch_playlist(self, playlist_id: str, *, force_refresh: bool = False, on_progress: ProgressFn | None = None) -> Playlist:
        return self.playlists[playlist_id]

    def create_playlist(self, name: str, *, public: bool = False, description: str = "") -> str:
        self.calls.append(("create_playlist", {"name": name, "description": description}))
        return "swept_pl"

    def add_tracks(self, playlist_id: str, track_ids: Any, *, on_progress: ProgressFn | None = None) -> int:
        ids = list(track_ids)
        self.calls.append(("add_tracks", {"playlist_id": playlist_id, "track_ids": ids}))
        return len(ids)


@pytest.fixture
def api(tmp_path: Path) -> Iterator[tuple[TestClient, FakeScanClient, DatasetStore]]:
    app = create_app()
    store = DatasetStore()
    fake = FakeScanClient()
    registry = JobRegistry(max_workers=1, max_jobs=10)
    batch_store = BatchStore(path=tmp_path / "batches.json")
    app.dependency_overrides[get_dataset_store] = lambda: store
    app.dependency_overrides[get_client] = lambda: fake
    app.dependency_overrides[get_job_registry] = lambda: registry
    app.dependency_overrides[get_batch_store] = lambda: batch_store
    with TestClient(app) as test_client:
        yield test_client, fake, store
    registry.shutdown()


def _poll_job(test_client: TestClient, job_id: str, *, timeout: float = 5.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        body: dict[str, Any] = test_client.get(f"/api/jobs/{job_id}").json()
        if body["status"] in ("done", "error"):
            return body
        time.sleep(0.01)
    pytest.fail(f"Job {job_id} did not finish within {timeout}s")


class TestScan:
    """POST /api/analysis/scan + GET /api/analysis/scan-result/{job_id}."""

    def test_scan_computes_pairs_duplication_unorganized(self, api: tuple[TestClient, FakeScanClient, DatasetStore]) -> None:
        test_client, _, store = api
        response = test_client.post("/api/analysis/scan", json={"source_ids": ["__liked__"], "subset_ids": ["rock_pl", "jazz_pl"]})
        assert response.status_code == 202
        job = _poll_job(test_client, response.json()["job_id"])
        assert job["status"] == "done"

        result = test_client.get(f"/api/jobs/{job['id']}").json()
        scan = test_client.get(f"/api/analysis/scan-result/{result['id']}").json()
        assert [p["role"] for p in scan["playlists"]] == ["source", "subset", "subset"]
        assert len(scan["pairs"]) == 3
        liked_rock = next(p for p in scan["pairs"] if p["b_name"] == "Rock")
        assert liked_rock["intersection"] == 2
        assert liked_rock["containment_b_in_a"] == pytest.approx(1.0)  # pyright: ignore[reportUnknownMemberType]

        assert scan["duplication_total"] == 1
        assert scan["duplication"][0]["track_id"] == "t2"
        assert scan["duplication"][0]["playlist_names"] == ["Rock", "Jazz"]

        assert scan["unorganized"]["count"] == 1
        assert scan["unorganized"]["track_ids"] == ["t4"]
        assert scan["unorganized"]["sample_names"] == ["Four — Artist t4"]

        # Scanned playlists are stored for instant exploring afterwards.
        assert store.get("rock_pl") is not None and store.get("__liked__") is not None

    def test_playlist_in_both_roles_400(self, api: tuple[TestClient, FakeScanClient, DatasetStore]) -> None:
        test_client, _, _ = api
        response = test_client.post("/api/analysis/scan", json={"source_ids": ["__liked__"], "subset_ids": ["__liked__"]})
        assert response.status_code == 400

    def test_scan_result_for_unknown_or_unfinished_job_404(self, api: tuple[TestClient, FakeScanClient, DatasetStore]) -> None:
        test_client, _, _ = api
        assert test_client.get("/api/analysis/scan-result/nope").status_code == 404


class TestSweep:
    """POST /api/analysis/sweep."""

    def test_sweep_creates_placeholder_and_batch(self, api: tuple[TestClient, FakeScanClient, DatasetStore]) -> None:
        test_client, fake, _ = api
        response = test_client.post("/api/analysis/sweep", json={"name": "Unsorted July", "track_ids": ["t4"]})
        assert response.status_code == 202
        job = _poll_job(test_client, response.json()["job_id"])
        assert job["status"] == "done"
        assert job["result"]["added"] == 1
        assert ("add_tracks", {"playlist_id": "swept_pl", "track_ids": ["t4"]}) in fake.calls
        batches = test_client.get("/api/organizer/batches").json()["batches"]
        assert batches[0]["batch_name"] == "Unsorted July"


class TestSuggestSplit:
    """POST /api/analysis/suggest-split."""

    def test_suggestion_returns_loadable_spec(self, api: tuple[TestClient, FakeScanClient, DatasetStore]) -> None:
        test_client, _, store = api
        store.put("__liked__", Dataset(playlist=LIKED, df=PlaylistAnalyzer.from_playlist(LIKED).df, loaded_at=datetime.now(UTC)))
        response = test_client.post("/api/analysis/suggest-split", json={"playlist_id": "__liked__", "target_buckets": 2, "duplication_tolerance": 0.2})
        assert response.status_code == 200
        body = response.json()
        assert body["coverage_pct"] > 0
        assert len(body["spec"]["buckets"]) >= 1
        # The returned spec must round-trip straight into the preview endpoint.
        preview = test_client.post("/api/organizer/preview", json={"playlist_id": "__liked__", "spec": body["spec"]})
        assert preview.status_code == 200

    def test_unloaded_playlist_409(self, api: tuple[TestClient, FakeScanClient, DatasetStore]) -> None:
        test_client, _, _ = api
        response = test_client.post("/api/analysis/suggest-split", json={"playlist_id": "ghost", "target_buckets": 3})
        assert response.status_code == 409
