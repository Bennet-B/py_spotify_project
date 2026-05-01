from __future__ import annotations

import logging
from typing import Any

import pytest

from spotify_project.models import Artist, Track


def test_artist_popularity_out_of_range_raises() -> None:
    """Artist's __post_init__ rejects popularity outside [0, 100]."""
    with pytest.raises(ValueError, match="popularity"):
        Artist(id="abc", name="Test", genres=(), popularity=101)


def test_track_negative_duration_raises() -> None:
    """Track's __post_init__ rejects negative duration_ms."""
    with pytest.raises(ValueError, match="duration_ms"):
        Track(
            id="t1",
            name="Test",
            artists=(),
            album_name="Album",
            release_date=None,
            duration_ms=-1,
            popularity=50,
            explicit=False,
            added_at=None,
            is_local=False,
        )


def test_track_from_api_warns_on_unknown_artist_id(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Track.from_api logs a warning when an artist ID is missing from the lookup."""
    item: dict[str, Any] = {
        "track": {
            "id": "t1",
            "name": "Test Track",
            "type": "track",
            "artists": [{"id": "missing_id", "name": "Some Artist"}],
            "album": {"name": "Album", "release_date": "2020"},
            "duration_ms": 100_000,
            "popularity": 50,
            "explicit": False,
        },
        "added_at": "2024-01-01T00:00:00Z",
        "is_local": False,
    }
    with caplog.at_level(logging.WARNING, logger="spotify_project.models"):
        track = Track.from_api(item, artist_by_id={})
    assert track.artists == ()
    assert "missing_id" in caplog.text
