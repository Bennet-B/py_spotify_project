"""Tests for the suggest-split heuristic — determinism, dominance splitting, packing, and duplication control."""

from __future__ import annotations

import pandas as pd
import pytest

from spotify_project.organizer import TagRule, YearRule, assign, summarize
from spotify_project.suggest_split import SplitParams, SplitReport, suggest_split


def _df(rows: list[dict[str, object]]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    if "release_year" in df.columns:
        df["release_year"] = df["release_year"].astype("Int64")
    return df


def _track(i: int, genres: list[str], year: int | None = 2000) -> dict[str, object]:
    return {"track_id": f"t{i}", "name": f"Track {i}", "genres": genres, "tags": genres, "artist_ids": ["a1"], "release_year": year, "duration_ms": 200_000, "is_local": False}


def _library_rock_dominated() -> pd.DataFrame:
    """60 rock tracks across five decades, 10 jazz, 10 pop, 5 untagged — rock must split, jazz+pop pack."""
    rows: list[dict[str, object]] = []
    for i in range(60):
        rows.append(_track(i, ["rock"], 1960 + (i % 5) * 10))
    for i in range(60, 70):
        rows.append(_track(i, ["jazz"], 1990))
    for i in range(70, 80):
        rows.append(_track(i, ["pop"], 2010))
    for i in range(80, 85):
        rows.append(_track(i, [], 2020))
    return _df(rows)


class TestParams:
    """Constructor invariants."""

    def test_invalid_params_raise(self) -> None:
        with pytest.raises(ValueError, match="at least 1"):
            SplitParams(target_buckets=0)
        with pytest.raises(ValueError, match="within"):
            SplitParams(target_buckets=3, duplication_tolerance=1.5)


class TestSuggestSplit:
    """The heuristic's shape guarantees."""

    def test_deterministic(self) -> None:
        df = _library_rock_dominated()
        first = suggest_split(df, SplitParams(target_buckets=4))
        second = suggest_split(df, SplitParams(target_buckets=4))
        assert first == second

    def test_dominant_genre_splits_into_decade_buckets(self) -> None:
        report = suggest_split(_library_rock_dominated(), SplitParams(target_buckets=4))
        rock_buckets = [name for name in report.bucket_sizes if name.lower().startswith("rock")]
        assert len(rock_buckets) >= 2, f"expected a decade split, got {report.bucket_sizes}"
        rock_rules = [bucket.rules for bucket in report.spec.buckets if bucket.name in rock_buckets]
        assert all(any(isinstance(rule, YearRule) for rule in rules) for rules in rock_rules)
        assert all(any(isinstance(rule, TagRule) for rule in rules) for rules in rock_rules)

    def test_small_genres_pack_and_untagged_noted(self) -> None:
        report = suggest_split(_library_rock_dominated(), SplitParams(target_buckets=4))
        assert any("packed" in note for note in report.notes)
        assert any("no genre data" in note for note in report.notes)
        total_assigned = sum(report.bucket_sizes.values())
        assert total_assigned >= 80  # every tagged track lands somewhere

    def test_tolerance_zero_disables_duplicates(self) -> None:
        report = suggest_split(_library_rock_dominated(), SplitParams(target_buckets=3, duplication_tolerance=0.0))
        assert report.spec.allow_duplicates is False
        assert report.duplication_rate == 0.0

    def test_duplication_respects_tolerance_after_trimming(self) -> None:
        """Tracks tagged with two genres force overlap; a tight tolerance must trim it away."""
        rows: list[dict[str, object]] = []
        for i in range(20):
            rows.append(_track(i, ["rock", "metal"], 2000))
        for i in range(20, 40):
            rows.append(_track(i, ["metal"], 2005))
        for i in range(40, 60):
            rows.append(_track(i, ["rock"], 1995))
        df = _df(rows)
        report = suggest_split(df, SplitParams(target_buckets=2, duplication_tolerance=0.05))
        assert report.duplication_rate <= 0.05
        assert any("above tolerance" in note for note in report.notes)

    def test_spec_is_directly_assignable(self) -> None:
        """The returned spec runs through the organizer engine unchanged (names unique, rules valid)."""
        df = _library_rock_dominated()
        report = suggest_split(df, SplitParams(target_buckets=4))
        stats = summarize(df, assign(df, report.spec))
        assert {bucket.name for bucket in stats.buckets} == set(report.bucket_sizes)

    def test_empty_and_genreless_libraries_degrade_gracefully(self) -> None:
        empty = suggest_split(pd.DataFrame(), SplitParams(target_buckets=3))
        assert empty.spec.buckets == () and "empty" in empty.notes[0]

        genreless = suggest_split(_df([_track(1, [], 2000)]), SplitParams(target_buckets=3))
        assert genreless.spec.buckets == ()
        assert "No genre data" in genreless.notes[0]

    def test_report_type(self) -> None:
        assert isinstance(suggest_split(_library_rock_dominated(), SplitParams(target_buckets=4)), SplitReport)
