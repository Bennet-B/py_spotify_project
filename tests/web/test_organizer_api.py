"""API tests for the organizer router: preview purity, rule round-trips, and the create-only Apply job."""

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


def _make_playlist() -> Playlist:
    """Four tracks: rock 1999, rock+jazz 2020, jazz 2020, untagged 1975."""
    rocker = Artist(id="a1", name="Rocker", tags=("rock",))
    jazzer = Artist(id="a2", name="Jazzer", tags=("jazz",))
    ghost = Artist(id="a3", name="Ghost", tags=())
    tracks = (
        Track(
            id="t1",
            name="Anthem",
            artists=(rocker,),
            album_name="A",
            release_date="1999-01-01",
            duration_ms=180_000,
            explicit=False,
            added_at=datetime(2024, 1, 5, tzinfo=UTC),
            is_local=False,
        ),
        Track(
            id="t2",
            name="Fusion",
            artists=(rocker, jazzer),
            album_name="B",
            release_date="2020-06-01",
            duration_ms=240_000,
            explicit=False,
            added_at=datetime(2024, 2, 5, tzinfo=UTC),
            is_local=False,
        ),
        Track(
            id="t3",
            name="Smooth",
            artists=(jazzer,),
            album_name="C",
            release_date="2020-03-01",
            duration_ms=200_000,
            explicit=False,
            added_at=datetime(2024, 2, 20, tzinfo=UTC),
            is_local=False,
        ),
        Track(
            id="t4",
            name="Mystery",
            artists=(ghost,),
            album_name="D",
            release_date="1975-01-01",
            duration_ms=500_000,
            explicit=False,
            added_at=datetime(2024, 3, 1, tzinfo=UTC),
            is_local=False,
        ),
    )
    return Playlist(id="pl1", name="Mixed", owner_display_name="Bennet", public=False, collaborative=False, description="", tracks=tracks)


class FakeMutationClient:
    """Fake SpotifyClient recording every write; create_playlist returns deterministic ids."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []
        self._counter = 0

    def fetch_current_user(self) -> User:
        return User(id="u1", display_name="Bennet", email=None)

    def create_playlist(self, name: str, *, public: bool = False, description: str = "") -> str:
        self._counter += 1
        self.calls.append(("create_playlist", {"name": name, "public": public, "description": description}))
        return f"created_{self._counter}"

    def add_tracks(self, playlist_id: str, track_ids: Any, *, on_progress: ProgressFn | None = None) -> int:
        ids = list(track_ids)
        self.calls.append(("add_tracks", {"playlist_id": playlist_id, "track_ids": ids}))
        return len(ids)


ALL_RULE_KINDS_SPEC: dict[str, Any] = {
    "buckets": [
        {
            "name": "Everything",
            "rules": [
                {"kind": "tag", "labels": ["rock", "jazz"]},
                {"kind": "year", "min_year": 1990, "max_year": 2025},
                {"kind": "duration", "min_seconds": 60, "max_seconds": 600},
                {"kind": "artist", "artist_ids": ["a1", "a2"]},
                {"kind": "track", "track_ids": ["t1", "t2", "t3"]},
            ],
        }
    ],
    "allow_duplicates": True,
}


@pytest.fixture
def api(tmp_path: Path) -> Iterator[tuple[TestClient, FakeMutationClient, BatchStore]]:
    """TestClient with a preloaded dataset, fake mutation client, fresh registry, and tmp batch store."""
    app = create_app()
    store = DatasetStore()
    playlist = _make_playlist()
    store.put("pl1", Dataset(playlist=playlist, df=PlaylistAnalyzer.from_playlist(playlist).df, loaded_at=datetime.now(UTC)))
    fake = FakeMutationClient()
    registry = JobRegistry(max_workers=1, max_jobs=10)
    batch_store = BatchStore(path=tmp_path / "batches.json")
    app.dependency_overrides[get_dataset_store] = lambda: store
    app.dependency_overrides[get_client] = lambda: fake
    app.dependency_overrides[get_job_registry] = lambda: registry
    app.dependency_overrides[get_batch_store] = lambda: batch_store
    with TestClient(app) as test_client:
        yield test_client, fake, batch_store
    registry.shutdown()


def _poll_job(test_client: TestClient, job_id: str, *, timeout: float = 5.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        body: dict[str, Any] = test_client.get(f"/api/jobs/{job_id}").json()
        if body["status"] in ("done", "error"):
            return body
        time.sleep(0.01)
    pytest.fail(f"Job {job_id} did not finish within {timeout}s")


class TestPreview:
    """POST /api/organizer/preview."""

    def test_two_bucket_preview_with_stats(self, api: tuple[TestClient, FakeMutationClient, BatchStore]) -> None:
        test_client, fake, _ = api
        spec = {
            "buckets": [
                {"name": "Rock", "rules": [{"kind": "tag", "labels": ["rock"]}]},
                {"name": "Jazz", "rules": [{"kind": "tag", "labels": ["jazz"]}]},
            ],
            "allow_duplicates": True,
        }
        response = test_client.post("/api/organizer/preview", json={"playlist_id": "pl1", "spec": spec})
        assert response.status_code == 200
        body = response.json()
        assert [(b["name"], b["count"], b["track_ids"]) for b in body["buckets"]] == [("Rock", 2, ["t1", "t2"]), ("Jazz", 2, ["t2", "t3"])]
        assert body["rest_track_ids"] == ["t4"]
        assert body["stats"]["duplicate_count"] == 1
        assert body["stats"]["coverage_pct"] == pytest.approx(75.0)  # pyright: ignore[reportUnknownMemberType]
        assert fake.calls == [], "preview must never write to Spotify"

    def test_every_rule_kind_round_trips(self, api: tuple[TestClient, FakeMutationClient, BatchStore]) -> None:
        """All five discriminated rule kinds deserialize, convert to core rules, and AND together."""
        test_client, _, _ = api
        response = test_client.post("/api/organizer/preview", json={"playlist_id": "pl1", "spec": ALL_RULE_KINDS_SPEC})
        assert response.status_code == 200
        assert response.json()["buckets"][0]["track_ids"] == ["t1", "t2", "t3"]

    def test_first_match_wins_without_duplicates(self, api: tuple[TestClient, FakeMutationClient, BatchStore]) -> None:
        test_client, _, _ = api
        spec = {
            "buckets": [
                {"name": "Rock", "rules": [{"kind": "tag", "labels": ["rock"]}]},
                {"name": "Jazz", "rules": [{"kind": "tag", "labels": ["jazz"]}]},
            ],
            "allow_duplicates": False,
        }
        body = test_client.post("/api/organizer/preview", json={"playlist_id": "pl1", "spec": spec}).json()
        assert [(b["name"], b["track_ids"]) for b in body["buckets"]] == [("Rock", ["t1", "t2"]), ("Jazz", ["t3"])]

    def test_invalid_specs_return_400(self, api: tuple[TestClient, FakeMutationClient, BatchStore]) -> None:
        test_client, _, _ = api
        empty_labels: dict[str, Any] = {"buckets": [{"name": "X", "rules": [{"kind": "tag", "labels": []}]}]}
        response = test_client.post("/api/organizer/preview", json={"playlist_id": "pl1", "spec": empty_labels})
        assert response.status_code == 400

        inverted_years: dict[str, Any] = {"buckets": [{"name": "X", "rules": [{"kind": "year", "min_year": 2020, "max_year": 1999}]}]}
        response = test_client.post("/api/organizer/preview", json={"playlist_id": "pl1", "spec": inverted_years})
        assert response.status_code == 400
        assert "inverted" in response.json()["error"]["message"]

    def test_unloaded_playlist_409(self, api: tuple[TestClient, FakeMutationClient, BatchStore]) -> None:
        test_client, _, _ = api
        response = test_client.post("/api/organizer/preview", json={"playlist_id": "nope", "spec": {"buckets": []}})
        assert response.status_code == 409


class TestApply:
    """POST /api/organizer/apply + GET /api/organizer/batches."""

    def test_apply_creates_batch_named_playlists(self, api: tuple[TestClient, FakeMutationClient, BatchStore]) -> None:
        test_client, fake, batch_store = api
        request = {
            "playlist_id": "pl1",
            "spec": {
                "buckets": [
                    {"name": "Rock", "rules": [{"kind": "tag", "labels": ["rock"]}]},
                    {"name": "Empty", "rules": [{"kind": "year", "min_year": 1800, "max_year": 1801}]},
                ],
                "allow_duplicates": True,
            },
            "bucket_names": ["Rock", "Empty"],
            "include_rest": True,
            "rest_name": "Unsorted",
            "public": False,
            "batch_name": "Split 1",
        }
        response = test_client.post("/api/organizer/apply", json=request)
        assert response.status_code == 202
        job = _poll_job(test_client, response.json()["job_id"])

        assert job["status"] == "done"
        assert job["result"]["skipped_empty"] == ["Empty"]
        created = job["result"]["created"]
        assert [(c["bucket_name"], c["added"]) for c in created] == [("Rock", 2), ("Unsorted", 2)]

        create_calls = [payload for name, payload in fake.calls if name == "create_playlist"]
        assert [c["name"] for c in create_calls] == ["[Split 1] Rock", "[Split 1] Unsorted"]
        assert all("created by spotify_project · batch Split 1" in c["description"] for c in create_calls)
        add_calls = [payload for name, payload in fake.calls if name == "add_tracks"]
        assert add_calls[0]["track_ids"] == ["t1", "t2"]
        assert add_calls[1]["track_ids"] == ["t4"] or add_calls[1]["track_ids"] == ["t3", "t4"]

        batches = test_client.get("/api/organizer/batches").json()["batches"]
        assert len(batches) == 1
        assert batches[0]["batch_name"] == "Split 1"
        assert len(batch_store.all_batches()) == 1

    def test_unknown_bucket_name_400_and_no_writes(self, api: tuple[TestClient, FakeMutationClient, BatchStore]) -> None:
        test_client, fake, _ = api
        request: dict[str, Any] = {
            "playlist_id": "pl1",
            "spec": {"buckets": [{"name": "Rock", "rules": [{"kind": "tag", "labels": ["rock"]}]}]},
            "bucket_names": ["Rock", "Ghost"],
            "batch_name": "B",
        }
        response = test_client.post("/api/organizer/apply", json=request)
        assert response.status_code == 400
        assert "Ghost" in response.json()["error"]["message"]
        assert fake.calls == []

    def test_apply_unloaded_playlist_409(self, api: tuple[TestClient, FakeMutationClient, BatchStore]) -> None:
        test_client, _, _ = api
        request: dict[str, Any] = {"playlist_id": "nope", "spec": {"buckets": [{"name": "X", "rules": []}]}, "bucket_names": ["X"], "batch_name": "B"}
        assert test_client.post("/api/organizer/apply", json=request).status_code == 409
