"""Rule engine for the playlist organizer — pure, framework-free, DataFrame-in / assignment-out.

An ``OrganizerSpec`` describes named buckets, each defined by rules. Within a bucket, rules AND together; within a single rule, values OR
(a ``TagRule`` matches when the track carries *any* of its labels). Tracks matching no bucket fall into the rest set. With
``allow_duplicates=True`` a track may land in several buckets; with ``False`` the first matching bucket wins, so bucket order is priority order.

Only real, addable tracks participate: local files (no Spotify id, rejected by the add-tracks API) are excluded from matching and reported
separately, so the dry-run preview shows exactly what an Apply would do.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal

import pandas as pd

__all__ = [
    "ArtistRule",
    "Assignment",
    "AssignmentStats",
    "BucketSpec",
    "BucketStats",
    "DurationRule",
    "OrganizerSpec",
    "OverlapPair",
    "Rule",
    "TagRule",
    "TrackRule",
    "YearRule",
    "assign",
    "summarize",
]


@dataclass(frozen=True, slots=True)
class TagRule:
    """Match tracks whose ``genres`` (or raw ``tags``) intersect the given labels, case-insensitively.

    Attributes:
        labels: Labels to match; a track matches when it carries at least one.
        field: Which track column to match against — curated ``genres`` (default) or raw Last.fm ``tags``.

    Raises:
        ValueError: If ``labels`` is empty (a rule that can never match is a spec bug, not a filter).
    """

    labels: frozenset[str]
    field: Literal["genres", "tags"] = "genres"

    def __post_init__(self) -> None:
        if not self.labels:
            raise ValueError("TagRule needs at least one label")


@dataclass(frozen=True, slots=True)
class YearRule:
    """Match tracks whose release year lies in [min_year, max_year]; either bound may be open.

    Raises:
        ValueError: If both bounds are None, or min exceeds max.
    """

    min_year: int | None = None
    max_year: int | None = None

    def __post_init__(self) -> None:
        if self.min_year is None and self.max_year is None:
            raise ValueError("YearRule needs at least one bound")
        if self.min_year is not None and self.max_year is not None and self.min_year > self.max_year:
            raise ValueError(f"YearRule bounds inverted: {self.min_year} > {self.max_year}")


@dataclass(frozen=True, slots=True)
class DurationRule:
    """Match tracks whose duration lies in [min_seconds, max_seconds]; either bound may be open.

    Raises:
        ValueError: If both bounds are None, or min exceeds max, or a bound is negative.
    """

    min_seconds: int | None = None
    max_seconds: int | None = None

    def __post_init__(self) -> None:
        if self.min_seconds is None and self.max_seconds is None:
            raise ValueError("DurationRule needs at least one bound")
        if (self.min_seconds is not None and self.min_seconds < 0) or (self.max_seconds is not None and self.max_seconds < 0):
            raise ValueError("DurationRule bounds must be non-negative")
        if self.min_seconds is not None and self.max_seconds is not None and self.min_seconds > self.max_seconds:
            raise ValueError(f"DurationRule bounds inverted: {self.min_seconds} > {self.max_seconds}")


@dataclass(frozen=True, slots=True)
class ArtistRule:
    """Match tracks crediting any of the given artist ids (not just the primary artist).

    Raises:
        ValueError: If ``artist_ids`` is empty.
    """

    artist_ids: frozenset[str]

    def __post_init__(self) -> None:
        if not self.artist_ids:
            raise ValueError("ArtistRule needs at least one artist id")


@dataclass(frozen=True, slots=True)
class TrackRule:
    """Match an explicit set of track ids — the "lasso a selection, make it a playlist" rule.

    Raises:
        ValueError: If ``track_ids`` is empty.
    """

    track_ids: frozenset[str]

    def __post_init__(self) -> None:
        if not self.track_ids:
            raise ValueError("TrackRule needs at least one track id")


type Rule = TagRule | YearRule | DurationRule | ArtistRule | TrackRule


@dataclass(frozen=True, slots=True)
class BucketSpec:
    """A named bucket: a track belongs when it matches ALL rules. A bucket with no rules matches nothing.

    Raises:
        ValueError: If the name is empty or whitespace.
    """

    name: str
    rules: tuple[Rule, ...] = ()

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Bucket name must be non-empty")


@dataclass(frozen=True, slots=True)
class OrganizerSpec:
    """The full organizer configuration: ordered buckets plus the duplication policy.

    Attributes:
        buckets: Buckets in priority order (order only matters when ``allow_duplicates`` is False).
        allow_duplicates: True lets a track land in several buckets; False gives it to the first match.

    Raises:
        ValueError: If bucket names collide.
    """

    buckets: tuple[BucketSpec, ...] = ()
    allow_duplicates: bool = True

    def __post_init__(self) -> None:
        names = [b.name for b in self.buckets]
        if len(set(names)) != len(names):
            duplicates = sorted({n for n in names if names.count(n) > 1})
            raise ValueError(f"Bucket names must be unique; got duplicates: {duplicates}")


@dataclass(frozen=True, slots=True)
class Assignment:
    """The dry-run result: which track ids landed where (all in DataFrame order).

    Attributes:
        by_bucket: Bucket name -> matched track ids.
        rest: Eligible tracks matching no bucket.
        skipped_local: Names of local-file tracks excluded from matching (they have no addable Spotify id).
    """

    by_bucket: Mapping[str, tuple[str, ...]] = field(default_factory=dict[str, tuple[str, ...]])
    rest: tuple[str, ...] = ()
    skipped_local: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class BucketStats:
    """Per-bucket preview numbers."""

    name: str
    count: int
    duration_ms_total: int


@dataclass(frozen=True, slots=True)
class OverlapPair:
    """Tracks shared by two buckets (only possible with ``allow_duplicates=True``)."""

    bucket_a: str
    bucket_b: str
    count: int


@dataclass(frozen=True, slots=True)
class AssignmentStats:
    """Aggregate preview numbers for an assignment.

    Attributes:
        buckets: Per-bucket counts and durations, in spec order.
        rest_count: Eligible tracks matching no bucket.
        coverage_pct: Share of eligible tracks assigned to at least one bucket (0-100).
        duplicate_count: Distinct tracks living in more than one bucket.
        overlaps: Pairwise shared-track counts, heaviest first.
        skipped_local_count: Local files excluded from matching.
    """

    buckets: tuple[BucketStats, ...]
    rest_count: int
    coverage_pct: float
    duplicate_count: int
    overlaps: tuple[OverlapPair, ...]
    skipped_local_count: int


def _rule_mask(df: pd.DataFrame, rule: Rule) -> pd.Series[bool]:
    """Boolean row mask for one rule over the flattened track DataFrame."""
    if isinstance(rule, TagRule):
        wanted = {label.lower() for label in rule.labels}
        return df[rule.field].apply(lambda cell: any(str(label).lower() in wanted for label in cell))  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType, reportUnknownLambdaType] — cell holds a list/ndarray of str
    if isinstance(rule, YearRule):
        years = df["release_year"]
        mask = years.notna()
        if rule.min_year is not None:
            mask &= years >= rule.min_year
        if rule.max_year is not None:
            mask &= years <= rule.max_year
        return mask
    if isinstance(rule, DurationRule):
        duration_ms = df["duration_ms"]
        mask = pd.Series(True, index=df.index)
        if rule.min_seconds is not None:
            mask &= duration_ms >= rule.min_seconds * 1000
        if rule.max_seconds is not None:
            mask &= duration_ms <= rule.max_seconds * 1000
        return mask
    if isinstance(rule, ArtistRule):
        return df["artist_ids"].apply(lambda cell: any(artist_id in rule.artist_ids for artist_id in cell))  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType, reportUnknownLambdaType] — cell holds a list/ndarray of str
    return df["track_id"].isin(rule.track_ids)


def assign(df: pd.DataFrame, spec: OrganizerSpec) -> Assignment:
    """Run the dry-run: evaluate every bucket's rules over the DataFrame and split tracks into buckets, rest, and skipped locals.

    Args:
        df: The flattened track DataFrame from ``PlaylistAnalyzer.from_playlist``.
        spec: Buckets and duplication policy.

    Returns:
        The assignment; nothing is written anywhere — Apply consumes this separately.
    """
    if df.empty:
        return Assignment(by_bucket={bucket.name: () for bucket in spec.buckets})
    local_mask = df["is_local"].astype(bool) | df["track_id"].isna()
    eligible = ~local_mask
    skipped_local = tuple(str(name) for name in df.loc[local_mask, "name"])

    by_bucket: dict[str, tuple[str, ...]] = {}
    assigned = pd.Series(False, index=df.index)
    claimed = pd.Series(False, index=df.index)
    for bucket in spec.buckets:
        if bucket.rules:
            mask = eligible.copy()
            for rule in bucket.rules:
                mask &= _rule_mask(df, rule)
        else:
            mask = pd.Series(False, index=df.index)
        if not spec.allow_duplicates:
            mask &= ~claimed
            claimed |= mask
        assigned |= mask
        by_bucket[bucket.name] = tuple(str(track_id) for track_id in df.loc[mask, "track_id"])

    rest = tuple(str(track_id) for track_id in df.loc[eligible & ~assigned, "track_id"])
    return Assignment(by_bucket=by_bucket, rest=rest, skipped_local=skipped_local)


def summarize(df: pd.DataFrame, assignment: Assignment) -> AssignmentStats:
    """Aggregate an assignment into the numbers the live preview shows.

    Args:
        df: The same DataFrame the assignment was computed from.
        assignment: Output of ``assign``.

    Returns:
        Per-bucket stats (spec order), coverage, duplication, and pairwise overlaps (heaviest first, ties alphabetical).
    """
    duration_by_id: dict[str, int] = {}
    if not df.empty:
        valid = df.dropna(subset=["track_id"])
        duration_by_id = {str(track_id): int(duration) for track_id, duration in zip(valid["track_id"], valid["duration_ms"], strict=True)}

    buckets = tuple(
        BucketStats(name=name, count=len(track_ids), duration_ms_total=sum(duration_by_id.get(track_id, 0) for track_id in track_ids)) for name, track_ids in assignment.by_bucket.items()
    )

    membership: dict[str, int] = {}
    for track_ids in assignment.by_bucket.values():
        for track_id in track_ids:
            membership[track_id] = membership.get(track_id, 0) + 1
    duplicate_count = sum(1 for count in membership.values() if count > 1)

    overlaps: list[OverlapPair] = []
    names = list(assignment.by_bucket)
    for i, name_a in enumerate(names):
        set_a = set(assignment.by_bucket[name_a])
        for name_b in names[i + 1 :]:
            shared = len(set_a.intersection(assignment.by_bucket[name_b]))
            if shared > 0:
                overlaps.append(OverlapPair(bucket_a=name_a, bucket_b=name_b, count=shared))
    overlaps.sort(key=lambda pair: (-pair.count, pair.bucket_a, pair.bucket_b))

    eligible_total = len(membership) + len(assignment.rest)
    coverage_pct = 100.0 * len(membership) / eligible_total if eligible_total > 0 else 0.0
    return AssignmentStats(
        buckets=buckets,
        rest_count=len(assignment.rest),
        coverage_pct=coverage_pct,
        duplicate_count=duplicate_count,
        overlaps=tuple(overlaps),
        skipped_local_count=len(assignment.skipped_local),
    )
