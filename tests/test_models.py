from __future__ import annotations

import pytest

from spotify_project.models import Artist


def test_artist_popularity_out_of_range_raises() -> None:
    """Artist's __post_init__ rejects popularity outside [0, 100]."""
    with pytest.raises(ValueError, match="popularity"):
        Artist(id="abc", name="Test", genres=(), popularity=101)
