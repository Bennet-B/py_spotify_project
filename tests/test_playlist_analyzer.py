from __future__ import annotations

from pathlib import Path

import pandas as pd

from spotify_project.analyzer import PlaylistAnalyzer


def test_to_parquet_round_trip_preserves_schema(tmp_path: Path) -> None:
    """to_parquet → read_parquet preserves columns and values exactly.

    Especially important for the list columns (``artist_ids``, ``artist_names``,
    ``genres``) which parquet stores as nested types.
    """
    df = pd.DataFrame(
        [
            {
                "track_id": "t1",
                "name": "Song",
                "primary_artist_id": "a1",
                "primary_artist_name": "Alice",
                "artist_ids": ["a1"],
                "artist_names": ["Alice"],
                "album_name": "Album",
                "release_date": "2020-01-01",
                "release_year": pd.array([2020], dtype="Int64")[0],
                "duration_ms": 200_000,
                "duration_min": 200_000 / 60_000,
                "explicit": False,
                "added_at": pd.Timestamp("2024-06-01", tz="UTC"),
                "is_local": False,
                "genres": ["rock"],
            }
        ]
    )
    pa = PlaylistAnalyzer(df=df, analyzers=[])
    out = tmp_path / "playlist.parquet"
    pa.to_parquet(out)
    assert out.exists()

    reloaded = pd.read_parquet(out)
    assert list(reloaded.columns) == list(df.columns)
    assert reloaded.iloc[0]["track_id"] == "t1"
    assert list(reloaded.iloc[0]["artist_ids"]) == ["a1"]
    assert list(reloaded.iloc[0]["genres"]) == ["rock"]
