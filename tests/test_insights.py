from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd
import pytest

from spotify_project.insights import (
    additions_over_time,
    artist_first_seen,
    artist_track_counts,
    collaboration_edges,
    discovery_waves,
    genre_cooccurrence,
    genre_share_over_time,
    label_frequencies,
    release_vs_added,
    seasonal_profile,
    year_counts,
)


def _df(rows: list[dict[str, object]]) -> pd.DataFrame:
    return pd.DataFrame(rows)


class TestAdditionsOverTime:
    """Tests for additions_over_time — per-period adds and cumulative growth curves."""

    def test_counts_and_cumulates_with_gap_free_periods(self) -> None:
        """Quiet months appear with added=0 so cumulative curves step instead of jumping across gaps."""
        df = _df(
            [
                {"added_at": datetime(2024, 1, 10, tzinfo=UTC), "duration_min": 30.0},
                {"added_at": datetime(2024, 1, 20, tzinfo=UTC), "duration_min": 30.0},
                {"added_at": datetime(2024, 3, 5, tzinfo=UTC), "duration_min": 60.0},
            ]
        )
        out = additions_over_time(df, freq="M")
        assert list(out["added"]) == [2, 0, 1]  # Jan, Feb (gap), Mar
        assert list(out["cumulative_tracks"]) == [2, 2, 3]
        assert list(out["cumulative_hours"]) == pytest.approx([1.0, 1.0, 2.0])  # pyright: ignore[reportUnknownMemberType]

    def test_empty_and_all_null_yield_empty_with_columns(self) -> None:
        """Both an empty df and one with only null added_at return the documented empty shape."""
        expected = ["period", "added", "cumulative_tracks", "cumulative_hours"]
        assert list(additions_over_time(pd.DataFrame()).columns) == expected
        out = additions_over_time(_df([{"added_at": None, "duration_min": 3.0}]))
        assert out.empty
        assert list(out.columns) == expected


class TestArtistFirstSeen:
    """Tests for artist_first_seen — earliest added_at per credited artist."""

    def test_takes_min_across_tracks_and_all_credited_artists(self) -> None:
        """Every artist on a track counts, and the earliest appearance wins."""
        df = _df(
            [
                {"artist_ids": ["a1", "a2"], "artist_names": ["Alice", "Bob"], "added_at": datetime(2024, 2, 1, tzinfo=UTC)},
                {"artist_ids": ["a1"], "artist_names": ["Alice"], "added_at": datetime(2024, 1, 1, tzinfo=UTC)},
            ]
        )
        out = artist_first_seen(df)
        by_id = {row["artist_id"]: row["first_added"] for _, row in out.iterrows()}
        assert by_id["a1"] == datetime(2024, 1, 1, tzinfo=UTC)
        assert by_id["a2"] == datetime(2024, 2, 1, tzinfo=UTC)

    def test_rows_without_added_at_are_ignored(self) -> None:
        df = _df([{"artist_ids": ["a1"], "artist_names": ["Alice"], "added_at": None}])
        assert artist_first_seen(df).empty


class TestDiscoveryWaves:
    """Tests for discovery_waves — first-appearance counts per period."""

    def test_counts_first_appearances_only(self) -> None:
        """An artist added in January doesn't count again for a February track."""
        df = _df(
            [
                {"artist_ids": ["a1"], "artist_names": ["Alice"], "added_at": datetime(2024, 1, 1, tzinfo=UTC)},
                {"artist_ids": ["a1"], "artist_names": ["Alice"], "added_at": datetime(2024, 2, 1, tzinfo=UTC)},
                {"artist_ids": ["a2"], "artist_names": ["Bob"], "added_at": datetime(2024, 2, 1, tzinfo=UTC)},
            ]
        )
        out = discovery_waves(df, freq="M")
        assert list(out["new_artists"]) == [1, 1]  # Alice in Jan, Bob in Feb


class TestSeasonalProfile:
    """Tests for seasonal_profile — calendar-month aggregation."""

    def test_always_returns_twelve_months(self) -> None:
        df = _df(
            [
                {"added_at": datetime(2023, 6, 1, tzinfo=UTC)},
                {"added_at": datetime(2024, 6, 15, tzinfo=UTC)},
                {"added_at": datetime(2024, 12, 24, tzinfo=UTC)},
            ]
        )
        out = seasonal_profile(df)
        assert len(out) == 12
        by_month = dict(zip(out["month"], out["added"], strict=True))
        assert by_month[6] == 2  # June across both years
        assert by_month[12] == 1
        assert by_month[1] == 0
        assert list(out["month_name"])[:3] == ["Jan", "Feb", "Mar"]


class TestGenreShareOverTime:
    """Tests for genre_share_over_time — normalized wide-format genre evolution."""

    def test_shares_sum_to_one_and_fold_tail_into_other(self) -> None:
        df = _df(
            [
                {"added_at": datetime(2024, 1, 1, tzinfo=UTC), "genres": ["rock", "pop"]},
                {"added_at": datetime(2024, 1, 15, tzinfo=UTC), "genres": ["rock"]},
                {"added_at": datetime(2024, 4, 1, tzinfo=UTC), "genres": ["jazz"]},
            ]
        )
        out = genre_share_over_time(df, top_n=2, freq="Q")
        assert list(out.columns) == ["rock", "pop", "other"]  # jazz folds into other
        assert out.sum(axis=1).tolist() == pytest.approx([1.0, 1.0])  # pyright: ignore[reportUnknownMemberType]
        assert out.iloc[0]["rock"] == pytest.approx(2 / 3)  # pyright: ignore[reportUnknownMemberType]

    def test_no_genres_yields_empty(self) -> None:
        df = _df([{"added_at": datetime(2024, 1, 1, tzinfo=UTC), "genres": []}])
        assert genre_share_over_time(df).empty


class TestCollaborationEdges:
    """Tests for collaboration_edges — same-track artist pairs."""

    def test_counts_pairs_and_applies_min_weight(self) -> None:
        df = _df(
            [
                {"artist_names": ["Alice", "Bob"]},
                {"artist_names": ["Bob", "Alice"]},  # order within the track doesn't matter
                {"artist_names": ["Alice", "Carol"]},
                {"artist_names": ["Solo"]},
            ]
        )
        out = collaboration_edges(df, min_weight=2)
        assert len(out) == 1
        edge = out.iloc[0]
        assert (edge["artist_a"], edge["artist_b"], edge["weight"]) == ("Alice", "Bob", 2)

    def test_no_collaborations_yields_empty_with_columns(self) -> None:
        out = collaboration_edges(_df([{"artist_names": ["Solo"]}]))
        assert out.empty
        assert list(out.columns) == ["artist_a", "artist_b", "weight"]


class TestGenreCooccurrence:
    """Tests for genre_cooccurrence — symmetric matrix with counts on the diagonal."""

    def test_matrix_is_symmetric_with_counts_on_diagonal(self) -> None:
        df = _df(
            [
                {"genres": ["rock", "indie"]},
                {"genres": ["rock", "indie"]},
                {"genres": ["rock"]},
                {"genres": ["pop"]},
            ]
        )
        out = genre_cooccurrence(df, top_n=3)
        assert list(out.index) == ["rock", "indie", "pop"]  # descending track count
        assert out.loc["rock", "rock"] == 3
        assert out.loc["rock", "indie"] == 2
        assert out.loc["indie", "rock"] == 2
        assert out.loc["rock", "pop"] == 0

    def test_top_n_limits_matrix_dimension(self) -> None:
        df = _df([{"genres": ["rock", "indie", "pop", "jazz"]}])
        out = genre_cooccurrence(df, top_n=2)
        assert out.shape == (2, 2)


class TestReleaseVsAdded:
    """Tests for release_vs_added — the year-pairing behind the back-catalog scatter."""

    def test_pairs_years_and_carries_hover_fields(self) -> None:
        df = _df(
            [
                {
                    "track_id": "t1",
                    "release_year": 1979,
                    "added_at": datetime(2024, 5, 1, tzinfo=UTC),
                    "name": "Old Song",
                    "primary_artist_name": "Alice",
                },
                {"track_id": "t2", "release_year": None, "added_at": datetime(2024, 5, 1, tzinfo=UTC), "name": "No Year", "primary_artist_name": "Bob"},
            ]
        )
        out = release_vs_added(df)
        assert len(out) == 1
        row = out.iloc[0]
        assert (row["track_id"], row["release_year"], row["added_year"], row["track"], row["artist"]) == ("t1", 1979, 2024, "Old Song", "Alice")

    def test_missing_track_id_column_returns_typed_empty(self) -> None:
        """A frame without track_id (pre-M1 parquet export) degrades to the typed empty result instead of raising."""
        df = _df([{"release_year": 1979, "added_at": datetime(2024, 5, 1, tzinfo=UTC), "name": "Old Song", "primary_artist_name": "Alice"}])
        out = release_vs_added(df)
        assert out.empty
        assert list(out.columns) == ["track_id", "release_year", "added_year", "track", "artist"]


class TestLabelFrequencies:
    """Tests for label_frequencies — the tag/genre bar chart behind the rule builder."""

    def test_counts_across_tracks_descending(self) -> None:
        df = _df([{"genres": ["rock", "pop"]}, {"genres": ["rock"]}, {"genres": []}])
        out = label_frequencies(df, field="genres", top_n=10)
        assert list(zip(out["label"], out["count"], strict=True)) == [("rock", 2), ("pop", 1)]

    def test_top_n_truncates(self) -> None:
        df = _df([{"genres": ["a", "b", "c"]}, {"genres": ["a", "b"]}, {"genres": ["a"]}])
        out = label_frequencies(df, top_n=2)
        assert list(out["label"]) == ["a", "b"]

    def test_tags_field_and_missing_column(self) -> None:
        df = _df([{"tags": ["seen live", "rock"]}])
        assert list(label_frequencies(df, field="tags")["label"]) == ["seen live", "rock"]
        empty = label_frequencies(_df([{"name": "x"}]), field="genres")
        assert empty.empty
        assert list(empty.columns) == ["label", "count"]


class TestYearCounts:
    """Tests for year_counts — pre-binned release-year bars."""

    def test_counts_ascending_years_skipping_nulls(self) -> None:
        df = _df([{"release_year": 1999}, {"release_year": 2020}, {"release_year": 1999}, {"release_year": None}])
        out = year_counts(df)
        assert list(zip(out["year"], out["count"], strict=True)) == [(1999, 2), (2020, 1)]

    def test_all_null_returns_typed_empty(self) -> None:
        out = year_counts(_df([{"release_year": None}]))
        assert out.empty
        assert list(out.columns) == ["year", "count"]


class TestArtistTrackCounts:
    """Tests for artist_track_counts — the cascading genre-scoped artist chart."""

    def _library(self) -> pd.DataFrame:
        return _df(
            [
                {"artist_ids": ["a1"], "artist_names": ["Rocker"], "genres": ["rock"]},
                {"artist_ids": ["a1", "a2"], "artist_names": ["Rocker", "Jazzer"], "genres": ["rock", "jazz"]},
                {"artist_ids": ["a2"], "artist_names": ["Jazzer"], "genres": ["jazz"]},
            ]
        )

    def test_counts_all_credited_artists(self) -> None:
        out = artist_track_counts(self._library())
        assert list(zip(out["artist_name"], out["track_count"], strict=True)) == [("Rocker", 2), ("Jazzer", 2)]

    def test_genre_scope_filters_tracks_case_insensitively(self) -> None:
        out = artist_track_counts(self._library(), genres=["ROCK"])
        assert list(zip(out["artist_name"], out["track_count"], strict=True)) == [("Rocker", 2), ("Jazzer", 1)]

    def test_unmatched_genre_returns_typed_empty(self) -> None:
        out = artist_track_counts(self._library(), genres=["polka"])
        assert out.empty
        assert list(out.columns) == ["artist_id", "artist_name", "track_count"]

    def test_none_artist_ids_are_skipped(self) -> None:
        df = _df([{"artist_ids": [None], "artist_names": ["Local Hero"], "genres": []}])
        assert artist_track_counts(df).empty
