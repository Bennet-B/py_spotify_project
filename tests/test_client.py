from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from spotipy.exceptions import SpotifyException

from spotify_project.cache import FileCache
from spotify_project.client import SpotifyClient


def _track_item(idx: int, artist_id: str = "a1") -> dict[str, Any]:
    """Build a spotipy-shaped playlist-item dict (Feb-2026-schema) for one fake track."""
    return {
        "item": {
            "id": f"t{idx}",
            "name": f"Track {idx}",
            "type": "track",
            "artists": [{"id": artist_id, "name": "Artist 1"}],
            "album": {"name": "Album", "release_date": "2020-01-01"},
            "duration_ms": 200_000,
            "explicit": False,
        },
        "added_at": "2024-06-01T00:00:00Z",
        "is_local": False,
    }


def _saved_track_item(idx: int, artist_id: str = "a1") -> dict[str, Any]:
    """Build a spotipy current_user_saved_tracks item.

    Uses the 'track' key (the saved-tracks endpoint never received the Feb 2026 rename, unlike the playlist endpoints which now use 'item').
    """
    return {
        "track": {
            "id": f"st{idx}",
            "name": f"Saved Track {idx}",
            "type": "track",
            "artists": [{"id": artist_id, "name": "Artist 1"}],
            "album": {"name": "Album", "release_date": "2020-01-01"},
            "duration_ms": 200_000,
            "explicit": False,
        },
        "added_at": "2024-06-01T00:00:00Z",
    }


def _playlist_summary_item(idx: int, track_count: int = 5) -> dict[str, Any]:
    """Build a spotipy current_user_playlists item."""
    return {
        "id": f"pl{idx}",
        "name": f"Playlist {idx}",
        "owner": {"display_name": "Bennet"},
        "items": {"total": track_count},
        "public": True,
    }


def _rate_limit_exc(retry_after: str | None) -> SpotifyException:
    """Build a SpotifyException as spotipy would surface a 429.

    When ``retry_after`` is None, the exception carries an empty headers dict — mimicking spotipy's urllib3-retry-exhaustion path where the Retry-After is dropped.
    """
    headers = {"Retry-After": retry_after} if retry_after is not None else {}
    return SpotifyException(429, -1, "rate limit", reason=None, headers=headers)


class TestFetchPlaylist:
    """Tests for SpotifyClient.fetch_playlist — pagination and artist enrichment."""

    def test_paginates_and_enriches_artists(self, tmp_path: Path) -> None:
        """Client.fetch_playlist concatenates pages and embeds full Artist data per Track."""
        cache = FileCache(root=tmp_path)
        fake_sp = MagicMock()

        fake_sp.playlist.return_value = {
            "id": "pl1",
            "name": "Test PL",
            "owner": {"display_name": "Bennet"},
            "public": True,
            "collaborative": False,
            "description": "",
            "items": {
                "items": [_track_item(i) for i in range(100)],
                "next": "next_url",
            },
        }
        fake_sp.next.side_effect = [
            {"items": [_track_item(i) for i in range(100, 150)], "next": None},
        ]
        fake_sp.artist.return_value = {
            "id": "a1",
            "name": "Artist 1",
            "genres": ["rock", "indie"],
        }

        client = SpotifyClient(sp=fake_sp, cache=cache)
        playlist = client.fetch_playlist("pl1")

        assert len(playlist.tracks) == 150
        first = playlist.tracks[0].primary_artist
        assert first is not None
        assert first.name == "Artist 1"
        assert first.tags == ()


class TestFromEnv:
    """Tests for SpotifyClient.from_env — credential validation at construction time."""

    def test_raises_on_missing_credentials(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """from_env raises RuntimeError listing the missing SPOTIPY_* env vars."""
        for var in ("SPOTIPY_CLIENT_ID", "SPOTIPY_CLIENT_SECRET", "SPOTIPY_REDIRECT_URI"):
            monkeypatch.delenv(var, raising=False)
        cache = FileCache(root=tmp_path)
        with pytest.raises(RuntimeError, match="SPOTIPY_CLIENT_ID"):
            SpotifyClient.from_env(cache=cache)


class TestFetchLikedSongs:
    """Tests for SpotifyClient.fetch_liked_songs — pagination and pseudo-playlist synthesis."""

    def test_paginates_and_synthesizes_pseudo_playlist(self, tmp_path: Path) -> None:
        """SpotifyClient.fetch_liked_songs paginates saved tracks and returns a pseudo-Playlist.

        The synthetic Playlist has id="__liked__", name="Liked Songs", owner from the authenticated user's display_name, and concatenated tracks from allpages.
        Each Track ends up enriched with full Artist data.
        """
        cache = FileCache(root=tmp_path)
        fake_sp = MagicMock()

        fake_sp.current_user.return_value = {"id": "me", "display_name": "Bennet"}
        fake_sp.current_user_saved_tracks.return_value = {
            "items": [_saved_track_item(i) for i in range(50)],
            "next": "next_url_1",
        }
        fake_sp.next.side_effect = [
            {
                "items": [_saved_track_item(i) for i in range(50, 100)],
                "next": "next_url_2",
            },
            {
                "items": [_saved_track_item(i) for i in range(100, 130)],
                "next": None,
            },
        ]
        fake_sp.artist.return_value = {
            "id": "a1",
            "name": "Artist 1",
            "genres": ["rock", "indie"],
        }

        client = SpotifyClient(sp=fake_sp, cache=cache)
        playlist = client.fetch_liked_songs()

        assert playlist.id == "__liked__"
        assert playlist.name == "Liked Songs"
        assert playlist.owner_display_name == "Bennet"
        assert len(playlist.tracks) == 130
        first = playlist.tracks[0].primary_artist
        assert first is not None
        assert first.name == "Artist 1"
        assert first.tags == ()


class TestFetchArtists:
    """Tests for SpotifyClient.fetch_artists — long-TTL caching and inter-call throttling."""

    def test_uses_long_ttl_for_cached_entries(self, tmp_path: Path) -> None:
        """fetch_artists() reads cached entries past the default 7-day TTL.

        Pins the contract that ARTIST_CACHE_TTL_DAYS is plumbed into cache.get's ttl_days override.
        Without the long TTL, this test would re-fetch the stale entry — and the mock has no .artist method, so the fetch would AttributeError.
        """
        cache = FileCache(root=tmp_path)  # default 7-day TTL
        cache.put(
            "artist/a1",
            {"id": "a1", "name": "Alice", "genres": ["rock"]},
        )
        cache_file = tmp_path / "artist" / "a1.json"
        thirty_days_ago = time.time() - 30 * 86_400
        os.utime(cache_file, (thirty_days_ago, thirty_days_ago))

        fake_sp = MagicMock(spec=[])  # spec=[] means ANY attribute access raises
        client = SpotifyClient(sp=fake_sp, cache=cache)
        artists = client.fetch_artists(["a1"])
        assert len(artists) == 1
        assert artists[0].name == "Alice"

    def test_throttles_between_uncached_fetches(self, tmp_path: Path) -> None:
        """fetch_artists() sleeps after each real API call (cache hits skip the sleep).

        Pins the throttle behavior: a 2-artist fetch with a cold cache should invoke time.sleep twice, with the value from ARTIST_FETCH_DELAY_SECONDS.
        """
        cache = FileCache(root=tmp_path)
        fake_sp = MagicMock()
        fake_sp.artist.side_effect = [
            {"id": "a1", "name": "Alice", "genres": ["rock"]},
            {"id": "a2", "name": "Bob", "genres": ["pop"]},
        ]

        client = SpotifyClient(sp=fake_sp, cache=cache)
        with patch("spotify_project.client.time.sleep") as mock_sleep:
            client.fetch_artists(["a1", "a2"])
        assert mock_sleep.call_count == 2
        for call in mock_sleep.call_args_list:
            assert call.args[0] == SpotifyClient.ARTIST_FETCH_DELAY_SECONDS


class TestFetchCurrentUser:
    """Tests for SpotifyClient.fetch_current_user — field mapping and error handling."""

    def test_returns_user(self, tmp_path: Path) -> None:
        """fetch_current_user maps id/display_name/email from the API response."""
        fake_sp = MagicMock()
        fake_sp.current_user.return_value = {"id": "u1", "display_name": "Bennet", "email": "b@example.com"}
        client = SpotifyClient(sp=fake_sp, cache=FileCache(root=tmp_path))
        user = client.fetch_current_user()
        assert user.id == "u1"
        assert user.display_name == "Bennet"
        assert user.email == "b@example.com"

    def test_null_display_name(self, tmp_path: Path) -> None:
        """fetch_current_user coerces display_name: null to empty string."""
        fake_sp = MagicMock()
        fake_sp.current_user.return_value = {"id": "u1", "display_name": None}
        client = SpotifyClient(sp=fake_sp, cache=FileCache(root=tmp_path))
        user = client.fetch_current_user()
        assert user.display_name == ""

    def test_missing_id_raises(self, tmp_path: Path) -> None:
        """fetch_current_user raises RuntimeError when the API returns no id (auth failure)."""
        fake_sp = MagicMock()
        fake_sp.current_user.return_value = {"display_name": "Bennet"}
        client = SpotifyClient(sp=fake_sp, cache=FileCache(root=tmp_path))
        with pytest.raises(RuntimeError, match="no id"):
            client.fetch_current_user()


class TestFetchUserPlaylists:
    """Tests for SpotifyClient.fetch_user_playlists — pagination."""

    def test_paginates(self, tmp_path: Path) -> None:
        """fetch_user_playlists concatenates pages and returns one PlaylistSummary per playlist."""
        fake_sp = MagicMock()
        fake_sp.current_user_playlists.return_value = {
            "items": [_playlist_summary_item(i) for i in range(3)],
            "next": "next_url",
        }
        fake_sp.next.return_value = {
            "items": [_playlist_summary_item(i) for i in range(3, 5)],
            "next": None,
        }
        client = SpotifyClient(sp=fake_sp, cache=FileCache(root=tmp_path))
        summaries = client.fetch_user_playlists()
        assert len(summaries) == 5
        assert summaries[0].id == "pl0"
        assert summaries[0].track_count == 5
        assert summaries[4].id == "pl4"


class TestEnrichWithArtists:
    """Tests for SpotifyClient._enrich_with_artists — the Last.fm tag-enrichment hook."""

    def test_uses_genre_enricher_when_set(self, tmp_path: Path) -> None:
        """_enrich_with_artists calls genre_enricher.fetch_artist_tags and populates Artist.tags."""
        cache = FileCache(root=tmp_path / "api")
        # Pre-populate Spotify artist cache so the Spotify side is read-only here.
        cache.put("artist/A1", {"id": "A1", "name": "Artist One"})

        sp = MagicMock()  # Spotipy client; should NOT be called for already-cached artists.
        enricher = MagicMock()
        enricher.fetch_artist_tags.return_value = ("rock", "indie")

        client = SpotifyClient(sp=sp, cache=cache, genre_enricher=enricher)
        track_items = [
            {
                "item": {
                    "type": "track",
                    "id": "T1",
                    "name": "Track One",
                    "artists": [{"id": "A1", "name": "Artist One"}],
                    "album": {"name": "Album", "release_date": "2020-01-01"},
                    "duration_ms": 200_000,
                    "explicit": False,
                },
                "added_at": "2024-01-01T00:00:00Z",
                "is_local": False,
            }
        ]

        tracks = client._enrich_with_artists(track_items)  # pyright: ignore[reportPrivateUsage]

        assert len(tracks) == 1
        primary = tracks[0].primary_artist
        assert primary is not None
        assert primary.tags == ("rock", "indie")
        enricher.fetch_artist_tags.assert_called_once_with("A1", "Artist One", force_refresh=False)
        sp.artist.assert_not_called()

    def test_skips_lastfm_when_enricher_none(self, tmp_path: Path) -> None:
        """_enrich_with_artists leaves Artist.tags empty when genre_enricher is None."""
        cache = FileCache(root=tmp_path / "api")
        cache.put("artist/A1", {"id": "A1", "name": "Artist One"})

        sp = MagicMock()
        client = SpotifyClient(sp=sp, cache=cache, genre_enricher=None)
        track_items = [
            {
                "item": {
                    "type": "track",
                    "id": "T1",
                    "name": "Track One",
                    "artists": [{"id": "A1", "name": "Artist One"}],
                    "album": {"name": "Album", "release_date": "2020-01-01"},
                    "duration_ms": 200_000,
                    "explicit": False,
                },
                "added_at": "2024-01-01T00:00:00Z",
                "is_local": False,
            }
        ]

        tracks = client._enrich_with_artists(track_items)  # pyright: ignore[reportPrivateUsage]

        primary = tracks[0].primary_artist
        assert primary is not None
        assert primary.tags == ()


class TestInit:
    """Tests for SpotifyClient.__init__ defaults."""

    def test_defaults_genre_enricher_to_none(self, tmp_path: Path) -> None:
        """SpotifyClient.__init__ defaults genre_enricher to None when not supplied."""
        cache = FileCache(root=tmp_path / "api")
        sp = MagicMock()
        client = SpotifyClient(sp=sp, cache=cache)
        assert client.genre_enricher is None


class TestMalformedItems:
    """Tests for robustness against null slots and non-track items flowing through the public fetch methods."""

    def test_fetch_playlist_drops_episode_and_null_items(self, tmp_path: Path) -> None:
        """fetch_playlist keeps only audio tracks: podcast episodes and null item slots are dropped."""
        cache = FileCache(root=tmp_path)
        fake_sp = MagicMock()
        episode_item: dict[str, Any] = {
            "item": {"id": "e1", "name": "Some Podcast", "type": "episode", "duration_ms": 1_800_000},
            "added_at": "2024-06-01T00:00:00Z",
            "is_local": False,
        }
        null_item: dict[str, Any] = {"item": None, "added_at": "2024-06-01T00:00:00Z", "is_local": False}
        fake_sp.playlist.return_value = {
            "id": "pl1",
            "name": "Mixed PL",
            "owner": {"display_name": "Bennet"},
            "public": True,
            "collaborative": False,
            "description": "",
            "items": {"items": [_track_item(0), episode_item, null_item], "next": None},
        }
        fake_sp.artist.return_value = {"id": "a1", "name": "Artist 1"}

        client = SpotifyClient(sp=fake_sp, cache=cache)
        playlist = client.fetch_playlist("pl1")

        assert len(playlist.tracks) == 1
        assert playlist.tracks[0].id == "t0"

    def test_fetch_liked_songs_drops_null_tracks(self, tmp_path: Path) -> None:
        """fetch_liked_songs drops saved-track slots whose 'track' payload is null (deleted/region-blocked tracks)."""
        cache = FileCache(root=tmp_path)
        fake_sp = MagicMock()
        fake_sp.current_user.return_value = {"id": "me", "display_name": "Bennet"}
        fake_sp.current_user_saved_tracks.return_value = {
            "items": [_saved_track_item(0), {"track": None, "added_at": "2024-06-01T00:00:00Z"}],
            "next": None,
        }
        fake_sp.artist.return_value = {"id": "a1", "name": "Artist 1"}

        client = SpotifyClient(sp=fake_sp, cache=cache)
        playlist = client.fetch_liked_songs()

        assert len(playlist.tracks) == 1
        assert playlist.tracks[0].id == "st0"


class TestRateLimitHandling:
    """Tests for SpotifyClient._call's 429 backoff and bail-out behavior."""

    def test_retries_once_when_retry_after_below_threshold(self, tmp_path: Path) -> None:
        """Short Retry-After: _call sleeps once then succeeds on retry."""
        cache = FileCache(root=tmp_path)
        fake_sp = MagicMock()
        fake_sp.artist.side_effect = [
            _rate_limit_exc("5"),
            {"id": "a1", "name": "Alice", "genres": []},
        ]

        client = SpotifyClient(sp=fake_sp, cache=cache)
        with patch("spotify_project.client.time.sleep") as mock_sleep:
            artists = client.fetch_artists(["a1"])

        assert len(artists) == 1
        assert artists[0].name == "Alice"
        # Two sleeps: one for the 5s rate-limit backoff, one for the post-fetch throttle.
        sleep_durations = sorted(call.args[0] for call in mock_sleep.call_args_list)
        assert sleep_durations == [SpotifyClient.ARTIST_FETCH_DELAY_SECONDS, 5]

    def test_raises_when_retry_after_exceeds_threshold(self, tmp_path: Path) -> None:
        """Long Retry-After: _call refuses to sleep and raises RuntimeError without invoking time.sleep with the cooldown."""
        cache = FileCache(root=tmp_path)
        fake_sp = MagicMock()
        huge_retry = str(SpotifyClient.MAX_RATE_LIMIT_WAIT_SECONDS + 60)
        fake_sp.artist.side_effect = _rate_limit_exc(huge_retry)

        client = SpotifyClient(sp=fake_sp, cache=cache)
        with (
            patch("spotify_project.client.time.sleep") as mock_sleep,
            pytest.raises(RuntimeError, match="refusing to wait"),
        ):
            client.fetch_artists(["a1"])

        # The post-fetch throttle never runs because the fetch raised; no rate-limit sleep should have happened either.
        for call in mock_sleep.call_args_list:
            assert call.args[0] != int(huge_retry)

    def test_raises_when_retry_after_header_missing(self, tmp_path: Path) -> None:
        """Missing Retry-After defaults above the threshold so _call bails out rather than retrying blindly."""
        cache = FileCache(root=tmp_path)
        fake_sp = MagicMock()
        fake_sp.artist.side_effect = _rate_limit_exc(None)

        client = SpotifyClient(sp=fake_sp, cache=cache)
        with patch("spotify_project.client.time.sleep"), pytest.raises(RuntimeError, match="refusing to wait"):
            client.fetch_artists(["a1"])

    def test_passes_non_429_spotify_exception_through(self, tmp_path: Path) -> None:
        """Non-429 SpotifyException is not caught by the rate-limit guard."""
        cache = FileCache(root=tmp_path)
        fake_sp = MagicMock()
        fake_sp.artist.side_effect = SpotifyException(500, -1, "server error", headers={})

        client = SpotifyClient(sp=fake_sp, cache=cache)
        with pytest.raises(SpotifyException) as excinfo:
            client.fetch_artists(["a1"])
        assert excinfo.value.http_status == 500  # pyright: ignore[reportUnknownMemberType]
