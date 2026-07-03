from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import matplotlib.patches as mpatches
import numpy as np
import pandas as pd
import pytest
from matplotlib.axes import Axes
from matplotlib.figure import Figure

from spotify_project.analyzer import (
    Analyzer,
    ArtistAnalyzer,
    DurationAnalyzer,
    GenreAnalyzer,
    TagAnalyzer,
    TimelineAnalyzer,
    YearAnalyzer,
)


class TestAnalyzerBase:
    """Tests for the Analyzer ABC's class-creation hooks and the plot contract shared by all subclasses."""

    def test_subclass_without_title_raises(self) -> None:
        """Subclassing Analyzer without setting `title` fails at class-creation time."""
        with pytest.raises(TypeError, match="title"):
            type("_BadAnalyzer", (Analyzer,), {})

    def test_plot_accepts_color_kwarg(self) -> None:
        """Each Analyzer subclass's plot() accepts a color= kwarg without raising.

        Pins the contract that PlaylistAnalyzer.plot_all relies on for palette threading.
        Doesn't assert color was actually used (matplotlib internals); just that the kwarg is supported.
        """
        fig = Figure()
        ax = fig.subplots()
        df = pd.DataFrame(
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
                    "added_at": pd.Timestamp("2024-01-01", tz="UTC"),
                }
            ]
        )
        for cls in (
            GenreAnalyzer,
            YearAnalyzer,
            ArtistAnalyzer,
            DurationAnalyzer,
            TimelineAnalyzer,
        ):
            analyzer = cls()
            summary = analyzer.analyze(df)
            analyzer.plot(ax, summary, color="#ff0000")
            ax.clear()


class TestGenreAnalyzer:
    """Tests for GenreAnalyzer.analyze and plot, including coverage reporting and partial-coverage rendering."""

    def test_returns_top_n_by_count(self) -> None:
        """GenreAnalyzer counts genre frequency across the playlist."""
        df = pd.DataFrame(
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

    def test_reports_partial_coverage_via_attrs(self) -> None:
        """GenreAnalyzer.analyze attaches (n_with_genres, n_total) to summary.attrs.

        Tracks with empty genres list count toward n_total but not n_with_genres.
        """
        df = pd.DataFrame(
            [
                {"track_id": "1", "genres": ["rock", "indie"]},
                {"track_id": "2", "genres": ["pop"]},
                {"track_id": "3", "genres": []},
                {"track_id": "4", "genres": []},
            ]
        )
        summary = GenreAnalyzer().analyze(df)
        assert summary.attrs["coverage"] == (2, 4)

    def test_plot_draws_band_when_coverage_below_100(self) -> None:
        """GenreAnalyzer.plot adds the missing-fraction band patch when coverage < 100%, in axes-fraction coordinates below the axes.

        Placement is asserted, not just patch count: the band must sit at y=-0.05 in ``ax.transAxes`` space.
        (An earlier axhspan-based implementation silently dropped the transform and drew the band over the top bar in data space.)
        We use a playlist with enough genres that both full and partial have the same number of genres in the result, differing only in coverage.
        """
        df_full = pd.DataFrame(
            [
                {"track_id": "1", "genres": ["rock", "indie"]},
                {"track_id": "2", "genres": ["pop", "electronic"]},
                {"track_id": "3", "genres": ["rock"]},
            ]
        )
        df_partial = pd.DataFrame(
            [
                {"track_id": "1", "genres": ["rock", "indie"]},
                {"track_id": "2", "genres": ["pop", "electronic"]},
                {"track_id": "3", "genres": []},
            ]
        )

        def _draw(d: pd.DataFrame) -> tuple[Axes, int]:
            fig = Figure()
            ax = fig.subplots()
            analyzer = GenreAnalyzer()
            summary = analyzer.analyze(d)
            analyzer.plot(ax, summary)
            return ax, len(ax.patches)

        _, patches_full = _draw(df_full)
        ax_partial, patches_partial = _draw(df_partial)
        assert patches_partial == patches_full + 1
        band = ax_partial.patches[-1]
        # get_transform() composes the patch's own transform on top of the assigned one, so identity fails; contains_branch asserts transAxes is in the chain.
        assert band.get_transform().contains_branch(ax_partial.transAxes)
        assert isinstance(band, mpatches.Rectangle)
        assert band.get_y() == pytest.approx(-0.05)  # pyright: ignore[reportUnknownMemberType]
        assert band.get_width() == pytest.approx(1 / 3)  # pyright: ignore[reportUnknownMemberType] — one of three tracks has no genres


class TestYearAnalyzer:
    """Tests for YearAnalyzer.analyze, including decade bucketing and coverage reporting."""

    def test_extracts_release_year(self) -> None:
        """YearAnalyzer counts tracks per release year, including year-only dates."""
        df = pd.DataFrame(
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

    def test_handles_missing_release_date_column(self) -> None:
        """YearAnalyzer returns an empty summary when release_date column is absent."""
        df = pd.DataFrame([{"track_id": "1", "name": "Song"}])
        summary = YearAnalyzer().analyze(df)
        assert summary.empty

    def test_groups_into_decade_buckets(self) -> None:
        """YearAnalyzer with bucket_size=10 groups years into decade ranges.

        The ``year`` column reports the bucket's lower bound (e.g. 1970 means 1970-1979 inclusive); the ``count`` column sums tracks across the bucket.
        """
        df = pd.DataFrame(
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

    def test_excludes_implausible_years(self) -> None:
        """Junk release dates like Spotify's "0000" are dropped from both the summary and the coverage count."""
        df = pd.DataFrame(
            [
                {"track_id": "1", "release_date": "2020-01-01"},
                {"track_id": "2", "release_date": "0000"},
                {"track_id": "3", "release_date": "9999-01-01"},
            ]
        )
        summary = YearAnalyzer().analyze(df)
        assert list(summary["year"]) == [2020]
        assert summary.attrs["coverage"] == (1, 3)

    def test_rejects_non_positive_bucket_size(self) -> None:
        """YearAnalyzer's __init__ rejects bucket_size < 1."""
        with pytest.raises(ValueError, match="bucket_size"):
            YearAnalyzer(bucket_size=0)

    def test_reports_coverage_via_attrs(self) -> None:
        """YearAnalyzer.analyze counts rows with parseable release_date."""
        df = pd.DataFrame(
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


class TestArtistAnalyzer:
    """Tests for ArtistAnalyzer.analyze across primary-only and all-artists modes."""

    def test_counts_all_artists_by_default(self) -> None:
        """ArtistAnalyzer with default primary_only=False counts every artist on every track.

        A track with two artists contributes 1 to each artist's track_count and its full duration to each artist's total_minutes (naive credit).
        """
        df = pd.DataFrame(
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

    def test_primary_only_mode_ignores_collaborators(self) -> None:
        """ArtistAnalyzer(primary_only=True) only counts the lead artist per track."""
        df = pd.DataFrame(
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

    def test_returns_empty_summary_for_empty_df(self) -> None:
        """ArtistAnalyzer.analyze returns an empty summary for an empty df."""
        summary = ArtistAnalyzer().analyze(pd.DataFrame([]))
        assert summary.empty
        assert list(summary.columns) == [
            "artist_id",
            "artist_name",
            "track_count",
            "total_minutes",
        ]

    def test_raises_value_error_on_mismatched_list_lengths(self) -> None:
        """ArtistAnalyzer.analyze raises ValueError when artist_ids and artist_names lists are different lengths in any row.

        The docstring documents this contract; previously no test exercised it.
        """
        df = pd.DataFrame(
            [
                {
                    "track_id": "t1",
                    "artist_ids": ["a1", "a2"],
                    "artist_names": ["Alice"],
                    "duration_min": 4.0,
                },
            ]
        )
        with pytest.raises(ValueError):
            ArtistAnalyzer().analyze(df)


class TestDurationAnalyzer:
    """Tests for DurationAnalyzer.analyze binning and edge cases."""

    def test_returns_bins_with_exact_minutes_per_bin(self) -> None:
        """DurationAnalyzer reports both track count and exact total minutes per bin.

        The ``minutes_in_bin`` column is the exact sum of durations falling in that bin (not a midpoint approximation), so plot() can annotate total runtime accurately.
        """
        df = pd.DataFrame(
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

    def test_handles_single_track(self) -> None:
        """DurationAnalyzer returns a single-row summary for a single-track df."""
        df = pd.DataFrame([{"track_id": "1", "duration_min": 3.5}])
        summary = DurationAnalyzer(bins=10).analyze(df)
        assert summary["count"].sum() == 1
        assert summary["minutes_in_bin"].sum() == pytest.approx(3.5)  # pyright: ignore[reportUnknownMemberType]

    def test_handles_empty_df(self) -> None:
        """DurationAnalyzer returns an empty summary for an empty df."""
        summary = DurationAnalyzer().analyze(pd.DataFrame([]))
        assert summary.empty
        assert list(summary.columns) == ["bin_low", "bin_high", "count", "minutes_in_bin"]

    def test_rejects_non_positive_bins(self) -> None:
        """DurationAnalyzer.__init__ rejects bins < 1."""
        with pytest.raises(ValueError, match="bins"):
            DurationAnalyzer(bins=0)


class TestTimelineAnalyzer:
    """Tests for TimelineAnalyzer.analyze grouping, source selection, and coverage reporting."""

    def test_groups_added_at_by_month_by_default(self) -> None:
        """TimelineAnalyzer groups added_at into monthly periods by default."""
        df = pd.DataFrame(
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

    def test_returns_empty_when_all_added_at_null(self) -> None:
        """TimelineAnalyzer returns an empty summary when every added_at is null.

        release_date is intentionally ignored — YearAnalyzer covers year-level breakdown.
        """
        df = pd.DataFrame(
            [
                {"track_id": "1", "added_at": None, "release_date": "2020-05-01"},
                {"track_id": "2", "added_at": None, "release_date": "2020-05-15"},
                {"track_id": "3", "added_at": None, "release_date": "2021-02-01"},
            ]
        )
        summary = TimelineAnalyzer().analyze(df)
        assert summary.empty
        assert list(summary.columns) == ["period", "count"]
        assert summary.attrs["coverage"] == (0, 3)

    def test_returns_empty_when_no_dates_at_all(self) -> None:
        """TimelineAnalyzer returns an empty summary when added_at is null."""
        df = pd.DataFrame(
            [
                {"track_id": "1", "added_at": None, "release_date": None},
            ]
        )
        summary = TimelineAnalyzer().analyze(df)
        assert summary.empty
        assert list(summary.columns) == ["period", "count"]

    def test_reports_coverage_via_attrs(self) -> None:
        """TimelineAnalyzer.analyze counts rows that actually produce a data point.

        Coverage mirrors analyze()'s source selection: when ANY added_at values are present, coverage counts non-null added_at rows (tracks 1 and 4 here).
        Track 2 has a release_date but its added_at is null, and since the source chosen is added_at it doesn't count. Track 3 has neither.
        """
        df = pd.DataFrame(
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
        # added_at is the source (non-null for tracks 1 and 4). Track 2's release_date doesn't count — it's not the active source. Track 3 has neither.
        assert summary.attrs["coverage"] == (2, 4)

    def test_coverage_when_added_at_column_absent(self) -> None:
        """TimelineAnalyzer reports zero coverage when the added_at column is entirely absent."""
        df = pd.DataFrame(
            [
                {"track_id": "1", "release_date": "2020-01-01"},
                {"track_id": "2", "release_date": "2020-05-01"},
                {"track_id": "3", "release_date": None},
            ]
        )
        summary = TimelineAnalyzer().analyze(df)
        assert summary.empty
        assert summary.attrs["coverage"] == (0, 3)


class TestTagAnalyzer:
    """Tests for TagAnalyzer.analyze, coverage, and the skip-when-no-LASTFM-API-KEY contract."""

    def test_counts_tags_top_n(self) -> None:
        """TagAnalyzer counts tag frequency across rows and returns the top N tags."""
        df = pd.DataFrame(
            {
                "tags": [
                    ["rock", "indie", "british"],
                    ["rock", "00s"],
                    ["rock", "indie"],
                    [],
                ],
                "duration_min": [3.5, 4.0, 3.0, 2.0],
            }
        )
        result = TagAnalyzer(top_n=2).analyze(df)
        # Counts: rock=3, indie=2, british=1, 00s=1. Top-2: rock, indie.
        assert list(result["tag"]) == ["rock", "indie"]
        assert list(result["count"]) == [3, 2]

    def test_coverage_counts_rows_with_any_tag(self) -> None:
        """TagAnalyzer.coverage counts rows with at least one tag against the total row count."""
        df = pd.DataFrame({"tags": [["rock"], [], ["pop", "indie"], []]})
        n_data, n_total = TagAnalyzer().coverage(df)
        assert n_data == 2
        assert n_total == 4

    def test_coverage_is_container_type_agnostic(self) -> None:
        """coverage() must not depend on the exact container type: a parquet round-trip yields numpy arrays where the live pipeline yields lists."""
        mixed_containers: list[Any] = [np.array(["rock"]), np.array([]), ("pop", "indie"), []]
        df = pd.DataFrame({"tags": mixed_containers})
        n_data, n_total = TagAnalyzer().coverage(df)
        assert n_data == 2
        assert n_total == 4

    def test_empty_df_returns_empty(self) -> None:
        """TagAnalyzer.analyze returns an empty summary for an empty df."""
        result = TagAnalyzer().analyze(pd.DataFrame())
        assert result.empty

    def test_skips_with_zero_coverage_via_skip_message(self) -> None:
        """TagAnalyzer.skip_message is non-None and mentions LASTFM_API_KEY so the skip path activates."""
        assert TagAnalyzer.skip_message is not None
        assert "LASTFM_API_KEY" in TagAnalyzer.skip_message
