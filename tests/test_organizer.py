"""Tests for the organizer rule engine — the matrix behind the dry-run preview and Apply."""

from __future__ import annotations

import pandas as pd
import pytest

from spotify_project.organizer import (
    ArtistRule,
    BucketSpec,
    DurationRule,
    OrganizerSpec,
    TagRule,
    TrackRule,
    YearRule,
    assign,
    summarize,
)


def _library() -> pd.DataFrame:
    """Five tracks: rock 1999, rock+jazz 2020 (feat.), jazz 2020, untagged 1975, and one local file."""
    rows: list[dict[str, object]] = [
        {"track_id": "t1", "name": "Anthem", "artist_ids": ["a1"], "genres": ["rock"], "tags": ["rock", "seen live"], "release_year": 1999, "duration_ms": 180_000, "is_local": False},
        {
            "track_id": "t2",
            "name": "Fusion",
            "artist_ids": ["a1", "a2"],
            "genres": ["rock", "jazz"],
            "tags": ["rock", "jazz"],
            "release_year": 2020,
            "duration_ms": 240_000,
            "is_local": False,
        },
        {"track_id": "t3", "name": "Smooth", "artist_ids": ["a2"], "genres": ["jazz"], "tags": ["jazz"], "release_year": 2020, "duration_ms": 200_000, "is_local": False},
        {"track_id": "t4", "name": "Mystery", "artist_ids": ["a3"], "genres": [], "tags": [], "release_year": 1975, "duration_ms": 500_000, "is_local": False},
        {"track_id": None, "name": "Local Demo", "artist_ids": [], "genres": [], "tags": [], "release_year": None, "duration_ms": 100_000, "is_local": True},
    ]
    df = pd.DataFrame(rows)
    df["release_year"] = df["release_year"].astype("Int64")
    return df


class TestRuleValidation:
    """Invariants are enforced at construction, not at assign time."""

    def test_empty_rule_values_raise(self) -> None:
        with pytest.raises(ValueError, match="at least one label"):
            TagRule(labels=frozenset())
        with pytest.raises(ValueError, match="at least one bound"):
            YearRule()
        with pytest.raises(ValueError, match="at least one bound"):
            DurationRule()
        with pytest.raises(ValueError, match="at least one artist"):
            ArtistRule(artist_ids=frozenset())
        with pytest.raises(ValueError, match="at least one track"):
            TrackRule(track_ids=frozenset())

    def test_inverted_and_negative_bounds_raise(self) -> None:
        with pytest.raises(ValueError, match="inverted"):
            YearRule(min_year=2020, max_year=1999)
        with pytest.raises(ValueError, match="inverted"):
            DurationRule(min_seconds=300, max_seconds=60)
        with pytest.raises(ValueError, match="non-negative"):
            DurationRule(min_seconds=-1, max_seconds=None)

    def test_duplicate_bucket_names_raise(self) -> None:
        with pytest.raises(ValueError, match="unique"):
            OrganizerSpec(buckets=(BucketSpec(name="A"), BucketSpec(name="A")))

    def test_blank_bucket_name_raises(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            BucketSpec(name="   ")


class TestRuleMatching:
    """Each rule kind, alone in a bucket."""

    def _ids(self, spec: OrganizerSpec) -> dict[str, tuple[str, ...]]:
        return dict(assign(_library(), spec).by_bucket)

    def test_tag_rule_matches_any_label_case_insensitive(self) -> None:
        spec = OrganizerSpec(buckets=(BucketSpec(name="Rock", rules=(TagRule(labels=frozenset({"ROCK"})),)),))
        assert self._ids(spec)["Rock"] == ("t1", "t2")

    def test_tag_rule_on_raw_tags_field(self) -> None:
        spec = OrganizerSpec(buckets=(BucketSpec(name="Live", rules=(TagRule(labels=frozenset({"seen live"}), field="tags"),)),))
        assert self._ids(spec)["Live"] == ("t1",)

    def test_year_rule_bounds_and_null_years(self) -> None:
        spec = OrganizerSpec(buckets=(BucketSpec(name="Oldies", rules=(YearRule(max_year=2000),)),))
        assert self._ids(spec)["Oldies"] == ("t1", "t4")

    def test_duration_rule(self) -> None:
        spec = OrganizerSpec(buckets=(BucketSpec(name="Short", rules=(DurationRule(max_seconds=200),)),))
        assert self._ids(spec)["Short"] == ("t1", "t3")

    def test_artist_rule_matches_featured_artists(self) -> None:
        spec = OrganizerSpec(buckets=(BucketSpec(name="A2", rules=(ArtistRule(artist_ids=frozenset({"a2"})),)),))
        assert self._ids(spec)["A2"] == ("t2", "t3")

    def test_track_rule_explicit_ids(self) -> None:
        spec = OrganizerSpec(buckets=(BucketSpec(name="Picked", rules=(TrackRule(track_ids=frozenset({"t4", "t1"})),)),))
        assert self._ids(spec)["Picked"] == ("t1", "t4")

    def test_rules_and_together(self) -> None:
        spec = OrganizerSpec(buckets=(BucketSpec(name="New Rock", rules=(TagRule(labels=frozenset({"rock"})), YearRule(min_year=2010))),))
        assert self._ids(spec)["New Rock"] == ("t2",)

    def test_bucket_without_rules_matches_nothing(self) -> None:
        spec = OrganizerSpec(buckets=(BucketSpec(name="Empty"),))
        result = assign(_library(), spec)
        assert result.by_bucket["Empty"] == ()
        assert result.rest == ("t1", "t2", "t3", "t4")


class TestDuplicatesAndRest:
    """Duplication policy, rest bucket, and local-file handling."""

    def _two_bucket_spec(self, *, allow_duplicates: bool) -> OrganizerSpec:
        return OrganizerSpec(
            buckets=(
                BucketSpec(name="Rock", rules=(TagRule(labels=frozenset({"rock"})),)),
                BucketSpec(name="Jazz", rules=(TagRule(labels=frozenset({"jazz"})),)),
            ),
            allow_duplicates=allow_duplicates,
        )

    def test_duplicates_allowed_puts_track_in_both(self) -> None:
        result = assign(_library(), self._two_bucket_spec(allow_duplicates=True))
        assert result.by_bucket == {"Rock": ("t1", "t2"), "Jazz": ("t2", "t3")}
        assert result.rest == ("t4",)

    def test_first_match_wins_when_duplicates_off(self) -> None:
        result = assign(_library(), self._two_bucket_spec(allow_duplicates=False))
        assert result.by_bucket == {"Rock": ("t1", "t2"), "Jazz": ("t3",)}

    def test_local_files_are_skipped_and_reported(self) -> None:
        result = assign(_library(), self._two_bucket_spec(allow_duplicates=True))
        assert result.skipped_local == ("Local Demo",)
        assert all("Local Demo" not in ids for ids in result.by_bucket.values())

    def test_empty_dataframe_yields_empty_buckets(self) -> None:
        result = assign(pd.DataFrame(), OrganizerSpec(buckets=(BucketSpec(name="Rock", rules=(TagRule(labels=frozenset({"rock"})),)),)))
        assert result.by_bucket == {"Rock": ()}
        assert result.rest == ()


class TestSummarize:
    """The preview stats block."""

    def test_stats_counts_coverage_overlap(self) -> None:
        df = _library()
        spec = OrganizerSpec(
            buckets=(
                BucketSpec(name="Rock", rules=(TagRule(labels=frozenset({"rock"})),)),
                BucketSpec(name="Jazz", rules=(TagRule(labels=frozenset({"jazz"})),)),
            )
        )
        stats = summarize(df, assign(df, spec))
        assert [(b.name, b.count) for b in stats.buckets] == [("Rock", 2), ("Jazz", 2)]
        assert stats.buckets[0].duration_ms_total == 420_000
        assert stats.rest_count == 1
        assert stats.coverage_pct == pytest.approx(75.0)  # pyright: ignore[reportUnknownMemberType]
        assert stats.duplicate_count == 1
        assert (
            (stats.overlaps[0].count == 1
            and (stats.overlaps[0].bucket_a, stats.overlaps[0].bucket_b) == ("Jazz", "Rock"))
            or (stats.overlaps[0].bucket_a, stats.overlaps[0].bucket_b) == ("Rock", "Jazz")
        )
        assert stats.skipped_local_count == 1

    def test_no_eligible_tracks_gives_zero_coverage(self) -> None:
        stats = summarize(pd.DataFrame(), assign(pd.DataFrame(), OrganizerSpec()))
        assert stats.coverage_pct == 0.0
        assert stats.buckets == ()
