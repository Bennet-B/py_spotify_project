from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

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
            "popularity": 50,
            "explicit": False,
        },
        "added_at": "2024-06-01T00:00:00Z",
        "is_local": False,
    }


def test_playlist_paginates_and_enriches_artists(tmp_path: Path) -> None:
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
        "popularity": 70,
    }

    client = SpotifyClient(sp=fake_sp, cache=cache)
    playlist = client.fetch_playlist("pl1")

    assert len(playlist.tracks) == 150
    first = playlist.tracks[0].primary_artist
    assert first is not None
    assert first.name == "Artist 1"
    assert "rock" in first.genres


def test_from_env_raises_on_missing_credentials(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """from_env raises RuntimeError listing the missing SPOTIPY_* env vars."""
    for var in ("SPOTIPY_CLIENT_ID", "SPOTIPY_CLIENT_SECRET", "SPOTIPY_REDIRECT_URI"):
        monkeypatch.delenv(var, raising=False)
    cache = FileCache(root=tmp_path)
    with pytest.raises(RuntimeError, match="SPOTIPY_CLIENT_ID"):
        SpotifyClient.from_env(cache=cache)


def _saved_track_item(idx: int, artist_id: str = "a1") -> dict[str, Any]:
    """Build a spotipy current_user_saved_tracks item — uses legacy 'track' key."""
    return {
        "track": {
            "id": f"st{idx}",
            "name": f"Saved Track {idx}",
            "type": "track",
            "artists": [{"id": artist_id, "name": "Artist 1"}],
            "album": {"name": "Album", "release_date": "2020-01-01"},
            "duration_ms": 200_000,
            "popularity": 50,
            "explicit": False,
        },
        "added_at": "2024-06-01T00:00:00Z",
    }


def test_liked_songs_paginates_and_synthesizes_pseudo_playlist(tmp_path: Path) -> None:
    """SpotifyClient.fetch_liked_songs paginates saved tracks and returns a pseudo-Playlist.

    The synthetic Playlist has id="__liked__", name="Liked Songs", owner from
    the authenticated user's display_name, and concatenated tracks from all
    pages. Each Track ends up enriched with full Artist data.
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
        "popularity": 70,
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
    assert "rock" in first.genres


def test_artists_uses_long_ttl_for_cached_entries(tmp_path: Path) -> None:
    """fetch_artists() reads cached entries past the default 7-day TTL.

    Pins the contract that ARTIST_CACHE_TTL_DAYS is plumbed into
    cache.get's ttl_days override. Without the long TTL, this test would
    re-fetch the stale entry — and the mock has no .artist method, so
    the fetch would AttributeError.
    """
    import os
    import time

    cache = FileCache(root=tmp_path)  # default 7-day TTL
    cache.put(
        "artist/a1",
        {"id": "a1", "name": "Alice", "genres": ["rock"], "popularity": 50},
    )
    cache_file = tmp_path / "artist" / "a1.json"
    thirty_days_ago = time.time() - 30 * 86_400
    os.utime(cache_file, (thirty_days_ago, thirty_days_ago))

    fake_sp = MagicMock(spec=[])  # spec=[] means ANY attribute access raises
    client = SpotifyClient(sp=fake_sp, cache=cache)
    artists = client.fetch_artists(["a1"])
    assert len(artists) == 1
    assert artists[0].name == "Alice"


def test_artists_throttles_between_uncached_fetches(tmp_path: Path) -> None:
    """fetch_artists() sleeps after each real API call (cache hits skip the sleep).

    Pins the throttle behavior: a 2-artist fetch with a cold cache should
    invoke time.sleep twice, with the value from ARTIST_FETCH_DELAY_SECONDS.
    """
    from unittest.mock import patch

    cache = FileCache(root=tmp_path)
    fake_sp = MagicMock()
    fake_sp.artist.side_effect = [
        {"id": "a1", "name": "Alice", "genres": ["rock"], "popularity": 50},
        {"id": "a2", "name": "Bob", "genres": ["pop"], "popularity": 40},
    ]

    client = SpotifyClient(sp=fake_sp, cache=cache)
    with patch("spotify_project.client.time.sleep") as mock_sleep:
        client.fetch_artists(["a1", "a2"])
    assert mock_sleep.call_count == 2
    for call in mock_sleep.call_args_list:
        assert call.args[0] == SpotifyClient.ARTIST_FETCH_DELAY_SECONDS
