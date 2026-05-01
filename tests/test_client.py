from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from spotify_project.cache import FileCache
from spotify_project.client import SpotifyClient


def _track_item(idx: int, artist_id: str = "a1") -> dict:
    """Build a spotipy-shaped playlist-item dict for one fake track."""
    return {
        "track": {
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
    """Client.playlist concatenates pages and embeds full Artist data per Track."""
    cache = FileCache(root=tmp_path)
    fake_sp = MagicMock()

    fake_sp.playlist.return_value = {
        "id": "pl1",
        "name": "Test PL",
        "owner": {"display_name": "Bennet"},
        "public": True,
        "collaborative": False,
        "description": "",
        "tracks": {
            "items": [_track_item(i) for i in range(100)],
            "next": "next_url",
        },
    }
    fake_sp.next.side_effect = [
        {"items": [_track_item(i) for i in range(100, 150)], "next": None},
    ]
    fake_sp.artists.return_value = {
        "artists": [
            {
                "id": "a1",
                "name": "Artist 1",
                "genres": ["rock", "indie"],
                "popularity": 70,
            },
        ],
    }

    client = SpotifyClient(sp=fake_sp, cache=cache)
    playlist = client.playlist("pl1")

    assert len(playlist.tracks) == 150
    first = playlist.tracks[0].primary_artist
    assert first is not None
    assert first.name == "Artist 1"
    assert "rock" in first.genres
