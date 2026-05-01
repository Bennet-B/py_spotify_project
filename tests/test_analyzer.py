from __future__ import annotations

from typing import Any

import pandas as pd

from spotify_project.analyzer import GenreAnalyzer, YearAnalyzer


def _frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    """Build a DataFrame matching the relevant subset of the spec's track schema."""
    return pd.DataFrame(rows)


def test_genre_analyzer_returns_top_n_by_count() -> None:
    """GenreAnalyzer counts genre frequency across the playlist."""
    df = _frame(
        [
            {"track_id": "1", "genres": ["rock", "indie"]},
            {"track_id": "2", "genres": ["rock"]},
            {"track_id": "3", "genres": ["pop"]},
            {"track_id": "4", "genres": []},
        ]
    )
    summary = GenreAnalyzer(top_n=10).analyze(df)
    counts = dict(zip(summary["genre"], summary["count"], strict=True))
    assert counts["rock"] == 2
    assert counts["indie"] == 1
    assert counts["pop"] == 1


def test_year_analyzer_extracts_release_year() -> None:
    """YearAnalyzer counts tracks per release year, including year-only dates."""
    df = _frame(
        [
            {"track_id": "1", "release_date": "2020-01-01"},
            {"track_id": "2", "release_date": "2020-06-01"},
            {"track_id": "3", "release_date": "1979"},
            {"track_id": "4", "release_date": None},
        ]
    )
    summary = YearAnalyzer().analyze(df)
    counts = dict(zip(summary["year"], summary["count"], strict=True))
    assert counts[2020] == 2
    assert counts[1979] == 1
