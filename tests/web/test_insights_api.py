"""API tests for the insights router, served from a pre-populated DatasetStore (no Spotify client involved)."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from spotify_project.analyzer import PlaylistAnalyzer
from spotify_project.models import Artist, Playlist, Track
from spotify_project.web.app import create_app
from spotify_project.web.dataset import Dataset, DatasetStore
from spotify_project.web.deps import get_dataset_store


def _make_playlist() -> Playlist:
    """Three tracks: two rock (one shared with jazz, one featuring), one jazz-only, spanning 1999-2020."""
    rocker = Artist(id="a1", name="Rocker", tags=("rock",))
    jazzer = Artist(id="a2", name="Jazzer", tags=("jazz",))
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
    )
    return Playlist(id="pl1", name="Mixed", owner_display_name="Bennet", public=False, collaborative=False, description="", tracks=tracks)


@pytest.fixture
def api() -> Iterator[TestClient]:
    """TestClient with the store pre-populated for pl1; pl_empty stays unloaded."""
    app = create_app()
    store = DatasetStore()
    playlist = _make_playlist()
    store.put("pl1", Dataset(playlist=playlist, df=PlaylistAnalyzer.from_playlist(playlist).df, loaded_at=datetime.now(UTC)))
    app.dependency_overrides[get_dataset_store] = lambda: store
    with TestClient(app) as test_client:
        yield test_client


class TestLabels:
    """GET .../insights/labels."""

    def test_genre_counts_descending(self, api: TestClient) -> None:
        response = api.get("/api/playlists/pl1/insights/labels")
        assert response.status_code == 200
        body = response.json()
        assert body["field"] == "genres"
        assert body["rows"] == [{"label": "rock", "count": 2}, {"label": "jazz", "count": 2}]

    def test_top_n_and_tags_field(self, api: TestClient) -> None:
        response = api.get("/api/playlists/pl1/insights/labels", params={"field": "tags", "top_n": 1})
        assert response.status_code == 200
        assert len(response.json()["rows"]) == 1

    def test_unloaded_playlist_409(self, api: TestClient) -> None:
        response = api.get("/api/playlists/pl_empty/insights/labels")
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "dataset_not_loaded"

    def test_invalid_top_n_400(self, api: TestClient) -> None:
        response = api.get("/api/playlists/pl1/insights/labels", params={"top_n": 0})
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "invalid_request"


class TestYears:
    """GET .../insights/years."""

    def test_pre_binned_ascending(self, api: TestClient) -> None:
        response = api.get("/api/playlists/pl1/insights/years")
        assert response.status_code == 200
        assert response.json()["rows"] == [{"year": 1999, "count": 1}, {"year": 2020, "count": 2}]


class TestTimelines:
    """GET .../insights/additions|discovery|seasonal."""

    def test_additions_monthly(self, api: TestClient) -> None:
        response = api.get("/api/playlists/pl1/insights/additions")
        assert response.status_code == 200
        body = response.json()
        assert body["freq"] == "M"
        assert [row["added"] for row in body["rows"]] == [1, 2]
        assert body["rows"][-1]["cumulative_tracks"] == 3

    def test_discovery_counts_first_appearances(self, api: TestClient) -> None:
        response = api.get("/api/playlists/pl1/insights/discovery")
        assert response.status_code == 200
        assert [row["new_artists"] for row in response.json()["rows"]] == [1, 1]

    def test_seasonal_always_twelve_rows(self, api: TestClient) -> None:
        response = api.get("/api/playlists/pl1/insights/seasonal")
        assert response.status_code == 200
        rows = response.json()["rows"]
        assert len(rows) == 12
        assert rows[0]["added"] == 1 and rows[1]["added"] == 2

    def test_invalid_freq_400(self, api: TestClient) -> None:
        response = api.get("/api/playlists/pl1/insights/additions", params={"freq": "X"})
        assert response.status_code == 400


class TestArtists:
    """GET .../insights/artists with the cascading genre scope."""

    def test_unscoped_counts_all_credited(self, api: TestClient) -> None:
        response = api.get("/api/playlists/pl1/insights/artists")
        assert response.status_code == 200
        body = response.json()
        assert body["scoped_to_genres"] == []
        assert {(row["artist_name"], row["track_count"]) for row in body["rows"]} == {("Rocker", 2), ("Jazzer", 2)}

    def test_genre_scope_rescopes(self, api: TestClient) -> None:
        response = api.get("/api/playlists/pl1/insights/artists", params=[("genre", "rock")])
        assert response.status_code == 200
        body = response.json()
        assert body["scoped_to_genres"] == ["rock"]
        assert {(row["artist_name"], row["track_count"]) for row in body["rows"]} == {("Rocker", 2), ("Jazzer", 1)}


class TestReleaseVsAdded:
    """GET .../insights/release-vs-added."""

    def test_rows_carry_track_ids(self, api: TestClient) -> None:
        response = api.get("/api/playlists/pl1/insights/release-vs-added")
        assert response.status_code == 200
        rows = response.json()["rows"]
        assert len(rows) == 3
        assert {row["track_id"] for row in rows} == {"t1", "t2", "t3"}
        anthem = next(row for row in rows if row["track_id"] == "t1")
        assert (anthem["release_year"], anthem["added_year"], anthem["artist"]) == (1999, 2024, "Rocker")
