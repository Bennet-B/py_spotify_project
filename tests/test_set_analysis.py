"""Tests for the set-analysis pure functions — overlaps, membership, and the unorganized report."""

from __future__ import annotations

import pytest

from spotify_project.set_analysis import PlaylistTrackSet, overlap_pairs, track_membership, unorganized


def _ts(playlist_id: str, name: str, *track_ids: str) -> PlaylistTrackSet:
    return PlaylistTrackSet(playlist_id=playlist_id, name=name, track_ids=frozenset(track_ids))


class TestOverlapPairs:
    """Pairwise intersection / jaccard / containment."""

    def test_subset_detection_via_containment(self) -> None:
        big = _ts("big", "Liked", "t1", "t2", "t3", "t4")
        small = _ts("small", "Chill", "t1", "t2")
        out = overlap_pairs([big, small])
        row = out.iloc[0]
        assert row["intersection"] == 2
        assert row["jaccard"] == pytest.approx(0.5)  # pyright: ignore[reportUnknownMemberType]
        assert row["containment_a_in_b"] == pytest.approx(0.5)  # pyright: ignore[reportUnknownMemberType]
        assert row["containment_b_in_a"] == pytest.approx(1.0)  # pyright: ignore[reportUnknownMemberType]

    def test_disjoint_pairs_are_included_with_zeros(self) -> None:
        out = overlap_pairs([_ts("a", "A", "t1"), _ts("b", "B", "t2")])
        assert len(out) == 1
        assert out.iloc[0]["intersection"] == 0
        assert out.iloc[0]["jaccard"] == 0.0

    def test_all_pairs_for_three_playlists(self) -> None:
        out = overlap_pairs([_ts("a", "A", "t1"), _ts("b", "B", "t1"), _ts("c", "C", "t1")])
        assert len(out) == 3

    def test_fewer_than_two_yields_typed_empty(self) -> None:
        out = overlap_pairs([_ts("a", "A", "t1")])
        assert out.empty
        assert "containment_a_in_b" in out.columns

    def test_empty_playlist_has_zero_containment(self) -> None:
        out = overlap_pairs([_ts("a", "A"), _ts("b", "B", "t1")])
        assert out.iloc[0]["containment_a_in_b"] == 0.0


class TestTrackMembership:
    """The track-in-N-playlists duplication report."""

    def test_counts_and_orders_most_duplicated_first(self) -> None:
        out = track_membership([_ts("a", "A", "t1", "t2"), _ts("b", "B", "t1"), _ts("c", "C", "t1", "t3")])
        assert list(out["track_id"]) == ["t1", "t2", "t3"]
        assert list(out["n_playlists"]) == [3, 1, 1]
        assert out.iloc[0]["playlist_names"] == ["A", "B", "C"]

    def test_empty_input_yields_typed_empty(self) -> None:
        out = track_membership([])
        assert out.empty
        assert list(out.columns) == ["track_id", "n_playlists", "playlist_names"]


class TestUnorganized:
    """union(sources) - union(subsets)."""

    def test_uncovered_tracks_remain(self) -> None:
        sources = [_ts("liked", "Liked", "t1", "t2", "t3")]
        subsets = [_ts("rock", "Rock", "t1"), _ts("jazz", "Jazz", "t2", "t9")]
        assert unorganized(sources, subsets) == frozenset({"t3"})

    def test_fully_covered_and_no_subsets(self) -> None:
        sources = [_ts("liked", "Liked", "t1")]
        assert unorganized(sources, [_ts("rock", "Rock", "t1")]) == frozenset()
        assert unorganized(sources, []) == frozenset({"t1"})

    def test_empty_playlist_id_raises(self) -> None:
        with pytest.raises(ValueError, match="playlist id"):
            _ts("", "X", "t1")
