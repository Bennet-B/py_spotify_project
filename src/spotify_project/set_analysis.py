"""Set-analysis over playlists as track-id sets — overlaps, subset detection, membership counts, and the unorganized-tracks report.

The scope is user-selected: *sources* are the libraries that should be fully organized (typically Liked Songs plus big mixed playlists), *subsets*
are the existing sub-playlists that organize them. "Every song has its place" then reads as: ``unorganized = union(sources) - union(subsets)``.

Pure and framework-free: inputs are plain ``PlaylistTrackSet`` values, outputs are plot-ready DataFrames / frozensets.
"""

from __future__ import annotations

import itertools
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

import pandas as pd

__all__ = [
    "PlaylistTrackSet",
    "overlap_pairs",
    "track_membership",
    "unorganized",
]


@dataclass(frozen=True, slots=True)
class PlaylistTrackSet:
    """A playlist reduced to its identity and set of (non-local) track ids.

    Raises:
        ValueError: If the playlist id is empty.
    """

    playlist_id: str
    name: str
    track_ids: frozenset[str]

    def __post_init__(self) -> None:
        if not self.playlist_id:
            raise ValueError("PlaylistTrackSet needs a playlist id")


def overlap_pairs(track_sets: Sequence[PlaylistTrackSet]) -> pd.DataFrame:
    """Pairwise overlap metrics for every playlist pair (including empty overlaps, so a heatmap stays complete).

    Args:
        track_sets: The selected playlists (order preserved into the pairing).

    Returns:
        DataFrame with columns ``a_id``, ``a_name``, ``b_id``, ``b_name``, ``intersection``, ``jaccard``,
        ``containment_a_in_b`` (share of A's tracks that live in B), ``containment_b_in_a``. Empty for fewer than two playlists.
    """
    empty = pd.DataFrame({"a_id": [], "a_name": [], "b_id": [], "b_name": [], "intersection": [], "jaccard": [], "containment_a_in_b": [], "containment_b_in_a": []})
    if len(track_sets) < 2:
        return empty
    rows: list[dict[str, object]] = []
    for a, b in itertools.combinations(track_sets, 2):
        shared = len(a.track_ids & b.track_ids)
        union = len(a.track_ids | b.track_ids)
        rows.append(
            {
                "a_id": a.playlist_id,
                "a_name": a.name,
                "b_id": b.playlist_id,
                "b_name": b.name,
                "intersection": shared,
                "jaccard": shared / union if union > 0 else 0.0,
                "containment_a_in_b": shared / len(a.track_ids) if a.track_ids else 0.0,
                "containment_b_in_a": shared / len(b.track_ids) if b.track_ids else 0.0,
            }
        )
    return pd.DataFrame(rows)


def track_membership(track_sets: Sequence[PlaylistTrackSet]) -> pd.DataFrame:
    """How many of the given playlists each track lives in — the duplication report.

    Args:
        track_sets: Typically the selected sub-playlists.

    Returns:
        DataFrame with columns ``track_id``, ``n_playlists``, ``playlist_names`` (list, input order), most-duplicated first
        (ties by track_id for determinism). One row per track appearing in at least one playlist.
    """
    empty = pd.DataFrame({"track_id": [], "n_playlists": [], "playlist_names": []})
    membership: dict[str, list[str]] = {}
    for ts in track_sets:
        for track_id in ts.track_ids:
            membership.setdefault(track_id, []).append(ts.name)
    if not membership:
        return empty
    rows = [{"track_id": track_id, "n_playlists": len(names), "playlist_names": names} for track_id, names in membership.items()]
    return pd.DataFrame(rows).sort_values(["n_playlists", "track_id"], ascending=[False, True], kind="stable").reset_index(drop=True)


def unorganized(sources: Iterable[PlaylistTrackSet], subsets: Iterable[PlaylistTrackSet]) -> frozenset[str]:
    """Tracks present in any source but in no subset — the "songs without a place" set.

    Args:
        sources: Playlists whose tracks should all be organized somewhere.
        subsets: The playlists that count as "organized".

    Returns:
        The uncovered track ids (empty when everything has a place).
    """
    source_union: set[str] = set()
    for ts in sources:
        source_union |= ts.track_ids
    for ts in subsets:
        source_union -= ts.track_ids
    return frozenset(source_union)
