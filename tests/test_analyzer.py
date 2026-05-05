from __future__ import annotations

from typing import Any

import pandas as pd
import pytest
from matplotlib.figure import Figure

from spotify_project.analyzer import (
    Analyzer,
    GenreAnalyzer,
    PlaylistAnalyzer,
    YearAnalyzer,
)


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


def test_year_analyzer_handles_missing_release_date_column() -> None:
    """YearAnalyzer returns an empty summary when release_date column is absent."""
    df = _frame([{"track_id": "1", "name": "Song"}])
    summary = YearAnalyzer().analyze(df)
    assert summary.empty


def test_plot_all_with_no_analyzers_does_not_crash() -> None:
    """PlaylistAnalyzer.plot_all returns early when the analyzer list is empty."""
    pa = PlaylistAnalyzer(df=pd.DataFrame(), analyzers=[])
    pa.plot_all(Figure())


def test_analyzer_subclass_without_title_raises() -> None:
    """Subclassing Analyzer without setting `title` fails at class-creation time."""
    with pytest.raises(TypeError, match="title"):
        type("_BadAnalyzer", (Analyzer,), {})


def test_year_analyzer_groups_into_decade_buckets() -> None:
    """YearAnalyzer with bucket_size=10 groups years into decade ranges.

    The ``year`` column reports the bucket's lower bound (e.g. 1970 means
    1970-1979 inclusive); the ``count`` column sums tracks across the bucket.
    """
    df = _frame(
        [
            {"track_id": "1", "release_date": "1972-05-01"},
            {"track_id": "2", "release_date": "1979-12-31"},
            {"track_id": "3", "release_date": "1980-01-01"},
            {"track_id": "4", "release_date": "2021-06-01"},
            {"track_id": "5", "release_date": "2024-03-15"},
        ]
    )
    summary = YearAnalyzer(bucket_size=10).analyze(df)
    counts = dict(zip(summary["year"], summary["count"], strict=True))
    assert counts[1970] == 2
    assert counts[1980] == 1
    assert counts[2020] == 2


def test_year_analyzer_rejects_non_positive_bucket_size() -> None:
    """YearAnalyzer's __init__ rejects bucket_size < 1."""
    with pytest.raises(ValueError, match="bucket_size"):
        YearAnalyzer(bucket_size=0)
