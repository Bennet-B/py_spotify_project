from __future__ import annotations

from datetime import UTC
from typing import Any

import pandas as pd
import pytest
from matplotlib.figure import Figure

from spotify_project.analyzer import (
    Analyzer,
    GenreAnalyzer,
    PlaylistAnalyzer,
    TimelineAnalyzer,
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


def test_playlist_analyzer_rejects_duplicate_titles() -> None:
    """PlaylistAnalyzer fails fast when two analyzers share the same title.

    run_all keys results by title and plot_all renders one subplot per
    analyzer; a duplicate title would silently render the second analyzer's
    data under both subplots without raising.
    """
    with pytest.raises(ValueError, match="Analyzer titles must be unique"):
        PlaylistAnalyzer(
            df=pd.DataFrame(),
            analyzers=[YearAnalyzer(bucket_size=1), YearAnalyzer(bucket_size=10)],
        )


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


def test_from_playlist_exposes_artist_id_and_name_lists() -> None:
    """PlaylistAnalyzer.from_playlist surfaces parallel artist_ids/names lists.

    ArtistAnalyzer needs grouping-friendly columns (lists, not pipe-joined
    strings). This test pins the schema additions; if they regress, the
    analyzer breaks.
    """
    from datetime import datetime

    from spotify_project.models import Artist, Playlist, Track

    a1 = Artist(id="a1", name="Alice", genres=("rock",), popularity=50)
    a2 = Artist(id="a2", name="Bob", genres=("indie",), popularity=40)
    track = Track(
        id="t1",
        name="Song",
        artists=(a1, a2),
        album_name="Album",
        release_date="2020-01-01",
        duration_ms=200_000,
        popularity=60,
        explicit=False,
        added_at=datetime(2024, 6, 1, tzinfo=UTC),
        is_local=False,
    )
    playlist = Playlist(
        id="pl1",
        name="Test",
        owner_display_name="Bennet",
        public=True,
        collaborative=False,
        description="",
        tracks=(track,),
    )
    pa = PlaylistAnalyzer.from_playlist(playlist)
    row = pa.df.iloc[0]
    assert row["artist_ids"] == ["a1", "a2"]
    assert row["artist_names"] == ["Alice", "Bob"]


def test_artist_analyzer_counts_all_artists_by_default() -> None:
    """ArtistAnalyzer with default primary_only=False counts every artist on every track.

    A track with two artists contributes 1 to each artist's track_count and
    its full duration to each artist's total_minutes (naive credit).
    """
    from spotify_project.analyzer import ArtistAnalyzer

    df = _frame(
        [
            {
                "track_id": "t1",
                "artist_ids": ["a1", "a2"],
                "artist_names": ["Alice", "Bob"],
                "primary_artist_id": "a1",
                "primary_artist_name": "Alice",
                "duration_min": 4.0,
            },
            {
                "track_id": "t2",
                "artist_ids": ["a1"],
                "artist_names": ["Alice"],
                "primary_artist_id": "a1",
                "primary_artist_name": "Alice",
                "duration_min": 3.0,
            },
            {
                "track_id": "t3",
                "artist_ids": ["a2"],
                "artist_names": ["Bob"],
                "primary_artist_id": "a2",
                "primary_artist_name": "Bob",
                "duration_min": 5.0,
            },
        ]
    )
    summary = ArtistAnalyzer(top_n=10).analyze(df)
    by_id = {row["artist_id"]: row for _, row in summary.iterrows()}
    assert by_id["a1"]["track_count"] == 2
    assert by_id["a1"]["total_minutes"] == 7.0
    assert by_id["a1"]["artist_name"] == "Alice"
    assert by_id["a2"]["track_count"] == 2
    assert by_id["a2"]["total_minutes"] == 9.0


def test_artist_analyzer_primary_only_mode_ignores_collaborators() -> None:
    """ArtistAnalyzer(primary_only=True) only counts the lead artist per track."""
    from spotify_project.analyzer import ArtistAnalyzer

    df = _frame(
        [
            {
                "track_id": "t1",
                "artist_ids": ["a1", "a2"],
                "artist_names": ["Alice", "Bob"],
                "primary_artist_id": "a1",
                "primary_artist_name": "Alice",
                "duration_min": 4.0,
            },
            {
                "track_id": "t2",
                "artist_ids": ["a2"],
                "artist_names": ["Bob"],
                "primary_artist_id": "a2",
                "primary_artist_name": "Bob",
                "duration_min": 5.0,
            },
        ]
    )
    summary = ArtistAnalyzer(primary_only=True).analyze(df)
    by_id = {row["artist_id"]: row for _, row in summary.iterrows()}
    # Bob is a collaborator on t1, so primary-only does NOT credit him for that track.
    assert by_id["a1"]["track_count"] == 1
    assert by_id["a2"]["track_count"] == 1
    assert by_id["a2"]["total_minutes"] == 5.0


def test_artist_analyzer_returns_empty_summary_for_empty_df() -> None:
    """ArtistAnalyzer.analyze returns an empty summary for an empty df."""
    from spotify_project.analyzer import ArtistAnalyzer

    summary = ArtistAnalyzer().analyze(_frame([]))
    assert summary.empty
    assert list(summary.columns) == [
        "artist_id",
        "artist_name",
        "track_count",
        "total_minutes",
    ]


def test_popularity_analyzer_returns_bin_counts() -> None:
    """PopularityAnalyzer bins track popularity 0-100 and reports counts per bin.

    Default 10 bins → bins of width 10. The summary has columns
    ``bin_low``, ``bin_high``, ``count``; bins are contiguous and cover [0, 100].
    """
    from spotify_project.analyzer import PopularityAnalyzer

    df = _frame(
        [
            {"track_id": "1", "popularity": 5},
            {"track_id": "2", "popularity": 12},
            {"track_id": "3", "popularity": 18},
            {"track_id": "4", "popularity": 95},
        ]
    )
    summary = PopularityAnalyzer(bins=10).analyze(df)
    assert list(summary.columns) == ["bin_low", "bin_high", "count"]
    assert len(summary) == 10
    first = summary.iloc[0]
    assert first["bin_low"] == 0
    assert first["bin_high"] == 10
    assert first["count"] == 1  # popularity=5 lives in [0, 10)
    second = summary.iloc[1]
    assert second["count"] == 2  # popularity=12 and 18 in [10, 20)
    assert summary.iloc[-1]["count"] == 1  # popularity=95 in [90, 100]


def test_popularity_analyzer_handles_empty_df() -> None:
    """PopularityAnalyzer returns an empty summary for an empty df."""
    from spotify_project.analyzer import PopularityAnalyzer

    summary = PopularityAnalyzer().analyze(_frame([]))
    assert summary.empty
    assert list(summary.columns) == ["bin_low", "bin_high", "count"]


def test_popularity_analyzer_all_zero_popularity_collapses_into_first_bin() -> None:
    """Tracks with popularity=0 (e.g. unreleased / unrated) all land in [0, 10)."""
    from spotify_project.analyzer import PopularityAnalyzer

    df = _frame([{"track_id": str(i), "popularity": 0} for i in range(5)])
    summary = PopularityAnalyzer(bins=10).analyze(df)
    assert summary.iloc[0]["count"] == 5
    assert summary["count"].sum() == 5


def test_popularity_analyzer_rejects_non_positive_bins() -> None:
    """PopularityAnalyzer.__init__ rejects bins < 1."""
    from spotify_project.analyzer import PopularityAnalyzer

    with pytest.raises(ValueError, match="bins"):
        PopularityAnalyzer(bins=0)


def test_duration_analyzer_returns_bins_with_exact_minutes_per_bin() -> None:
    """DurationAnalyzer reports both track count and exact total minutes per bin.

    The ``minutes_in_bin`` column is the exact sum of durations falling in
    that bin (not a midpoint approximation), so plot() can annotate total
    runtime accurately.
    """
    from spotify_project.analyzer import DurationAnalyzer

    df = _frame(
        [
            {"track_id": "1", "duration_min": 2.0},
            {"track_id": "2", "duration_min": 2.5},
            {"track_id": "3", "duration_min": 4.0},
            {"track_id": "4", "duration_min": 5.5},
        ]
    )
    summary = DurationAnalyzer(bins=4).analyze(df)
    assert list(summary.columns) == ["bin_low", "bin_high", "count", "minutes_in_bin"]
    assert summary["count"].sum() == 4
    assert summary["minutes_in_bin"].sum() == pytest.approx(14.0)  # pyright: ignore[reportUnknownMemberType]


def test_duration_analyzer_handles_single_track() -> None:
    """DurationAnalyzer returns a single-row summary for a single-track df."""
    from spotify_project.analyzer import DurationAnalyzer

    df = _frame([{"track_id": "1", "duration_min": 3.5}])
    summary = DurationAnalyzer(bins=10).analyze(df)
    assert summary["count"].sum() == 1
    assert summary["minutes_in_bin"].sum() == pytest.approx(3.5)  # pyright: ignore[reportUnknownMemberType]


def test_duration_analyzer_handles_empty_df() -> None:
    """DurationAnalyzer returns an empty summary for an empty df."""
    from spotify_project.analyzer import DurationAnalyzer

    summary = DurationAnalyzer().analyze(_frame([]))
    assert summary.empty
    assert list(summary.columns) == ["bin_low", "bin_high", "count", "minutes_in_bin"]


def test_duration_analyzer_rejects_non_positive_bins() -> None:
    """DurationAnalyzer.__init__ rejects bins < 1."""
    from spotify_project.analyzer import DurationAnalyzer

    with pytest.raises(ValueError, match="bins"):
        DurationAnalyzer(bins=0)


def test_timeline_analyzer_groups_added_at_by_month_by_default() -> None:
    """TimelineAnalyzer groups added_at into monthly periods by default."""
    from datetime import datetime

    from spotify_project.analyzer import TimelineAnalyzer

    df = _frame(
        [
            {"track_id": "1", "added_at": datetime(2024, 1, 5, tzinfo=UTC)},
            {"track_id": "2", "added_at": datetime(2024, 1, 28, tzinfo=UTC)},
            {"track_id": "3", "added_at": datetime(2024, 3, 10, tzinfo=UTC)},
            {"track_id": "4", "added_at": None},
        ]
    )
    summary = TimelineAnalyzer().analyze(df)
    assert list(summary.columns) == ["period", "count"]
    counts = dict(zip(summary["period"].astype(str), summary["count"], strict=True))
    assert counts["2024-01"] == 2
    assert counts["2024-03"] == 1


def test_timeline_analyzer_falls_back_to_release_date_when_all_added_at_missing() -> (
    None
):
    """When added_at is entirely missing, TimelineAnalyzer uses release_date.

    Models the Spotify-curated-playlist case: the API returns added_at=null
    for every track on official editorial playlists.
    """
    from spotify_project.analyzer import TimelineAnalyzer

    df = _frame(
        [
            {"track_id": "1", "added_at": None, "release_date": "2020-05-01"},
            {"track_id": "2", "added_at": None, "release_date": "2020-05-15"},
            {"track_id": "3", "added_at": None, "release_date": "2021-02-01"},
        ]
    )
    summary = TimelineAnalyzer().analyze(df)
    counts = dict(zip(summary["period"].astype(str), summary["count"], strict=True))
    assert counts["2020-05"] == 2
    assert counts["2021-02"] == 1


def test_timeline_analyzer_returns_empty_when_no_dates_at_all() -> None:
    """TimelineAnalyzer returns an empty summary if both added_at and release_date are missing."""
    from spotify_project.analyzer import TimelineAnalyzer

    df = _frame(
        [
            {"track_id": "1", "added_at": None, "release_date": None},
        ]
    )
    summary = TimelineAnalyzer().analyze(df)
    assert summary.empty
    assert list(summary.columns) == ["period", "count"]


def test_analyzer_plot_accepts_color_kwarg() -> None:
    """Each Analyzer subclass's plot() accepts a color= kwarg without raising.

    Pins the contract that PlaylistAnalyzer.plot_all relies on for palette
    threading. Doesn't assert color was actually used (matplotlib internals);
    just that the kwarg is supported.
    """
    from matplotlib.figure import Figure

    from spotify_project.analyzer import (
        ArtistAnalyzer,
        DurationAnalyzer,
        GenreAnalyzer,
        PopularityAnalyzer,
        TimelineAnalyzer,
        YearAnalyzer,
    )

    fig = Figure()
    ax = fig.subplots()
    df = _frame(
        [
            {
                "track_id": "t1",
                "genres": ["rock"],
                "release_date": "2020-01-01",
                "primary_artist_id": "a1",
                "primary_artist_name": "Alice",
                "artist_ids": ["a1"],
                "artist_names": ["Alice"],
                "duration_min": 3.0,
                "popularity": 50,
                "added_at": pd.Timestamp("2024-01-01", tz="UTC"),
            }
        ]
    )
    for cls in (
        GenreAnalyzer,
        YearAnalyzer,
        ArtistAnalyzer,
        PopularityAnalyzer,
        DurationAnalyzer,
        TimelineAnalyzer,
    ):
        analyzer = cls()
        summary = analyzer.analyze(df)
        analyzer.plot(ax, summary, color="#ff0000")
        ax.clear()


def test_genre_analyzer_reports_partial_coverage_via_attrs() -> None:
    """GenreAnalyzer.analyze attaches (n_with_genres, n_total) to summary.attrs.

    Tracks with empty genres list count toward n_total but not n_with_genres.
    """
    df = _frame(
        [
            {"track_id": "1", "genres": ["rock", "indie"]},
            {"track_id": "2", "genres": ["pop"]},
            {"track_id": "3", "genres": []},
            {"track_id": "4", "genres": []},
        ]
    )
    summary = GenreAnalyzer().analyze(df)
    assert summary.attrs["coverage"] == (2, 4)


def test_year_analyzer_reports_coverage_via_attrs() -> None:
    """YearAnalyzer.analyze counts rows with parseable release_date."""
    df = _frame(
        [
            {"track_id": "1", "release_date": "2020-01-01"},
            {"track_id": "2", "release_date": "1979"},
            {"track_id": "3", "release_date": None},
            {"track_id": "4", "release_date": "not-a-date"},
        ]
    )
    summary = YearAnalyzer().analyze(df)
    # Rows 1, 2 parse cleanly. Row 3 is None. Row 4's first 4 chars "not-"
    # fail pd.to_numeric → NaN → dropped. So 2 of 4 cleanly contribute years.
    assert summary.attrs["coverage"] == (2, 4)


def test_timeline_analyzer_reports_coverage_via_attrs() -> None:
    """TimelineAnalyzer.analyze counts rows with usable date data.

    A row contributes to coverage if EITHER added_at OR release_date is
    parseable.
    """
    from datetime import datetime

    df = _frame(
        [
            {
                "track_id": "1",
                "added_at": datetime(2024, 1, 1, tzinfo=UTC),
                "release_date": "2020-01-01",
            },
            {"track_id": "2", "added_at": None, "release_date": "2020-05-01"},
            {"track_id": "3", "added_at": None, "release_date": None},
            {
                "track_id": "4",
                "added_at": datetime(2024, 2, 1, tzinfo=UTC),
                "release_date": None,
            },
        ]
    )
    summary = TimelineAnalyzer().analyze(df)
    # Rows 1, 2, 4 contribute (have at least one usable date). Row 3 doesn't.
    assert summary.attrs["coverage"] == (3, 4)
