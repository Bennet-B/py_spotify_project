"""Suggest-split: propose an OrganizerSpec that splits a library into roughly even genre buckets.

Deterministic, explainable heuristic — no ML: group tracks by their canonical genre, split dominant genres by release decade, pack the small
genres to even sizes, then trim tag overlaps until the duplication rate respects the tolerance. The output is a plain ``OrganizerSpec`` the
organizer loads for hand-editing — suggesting never applies anything.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from math import ceil

import pandas as pd

from .organizer import BucketSpec, OrganizerSpec, Rule, TagRule, YearRule, assign, summarize

__all__ = [
    "SplitParams",
    "SplitReport",
    "suggest_split",
]

# A genre group counts as dominant (and gets decade sub-buckets) beyond this multiple of the ideal bucket size.
_DOMINANCE_FACTOR = 1.5

# Safety bound on the overlap-trimming loop; each iteration removes at least one label, so this is never reached in practice.
_MAX_TRIM_ITERATIONS = 100


@dataclass(frozen=True, slots=True)
class SplitParams:
    """Tuning knobs for the suggestion.

    Attributes:
        target_buckets: Rough number of buckets to aim for (dominant genres may add more).
        duplication_tolerance: Highest acceptable share (0-1) of assigned tracks living in more than one bucket.
            0 means "no duplicates at all": the spec switches to first-match-wins instead of trimming rules.

    Raises:
        ValueError: If target_buckets < 1 or the tolerance is outside [0, 1].
    """

    target_buckets: int
    duplication_tolerance: float = 0.15

    def __post_init__(self) -> None:
        if self.target_buckets < 1:
            raise ValueError("target_buckets must be at least 1")
        if not 0.0 <= self.duplication_tolerance <= 1.0:
            raise ValueError("duplication_tolerance must be within [0, 1]")


@dataclass(frozen=True, slots=True)
class SplitReport:
    """The suggestion plus the numbers that justify it.

    Attributes:
        spec: The proposed organizer spec (load into the organizer, edit, apply).
        bucket_sizes: Dry-run track count per bucket.
        duplication_rate: Share of assigned tracks living in >1 bucket (0-1) under the proposed spec.
        coverage_pct: Share of eligible tracks the spec assigns (0-100).
        notes: Human-readable explanation of every decision taken.
    """

    spec: OrganizerSpec
    bucket_sizes: Mapping[str, int]
    duplication_rate: float
    coverage_pct: float
    notes: tuple[str, ...]


def _canonical_genres(df: pd.DataFrame) -> pd.Series[str]:
    """Each track's canonical genre: its globally most frequent genre; tracks without genres map to ''."""
    global_counts: Counter[str] = Counter(str(genre) for cell in df["genres"] for genre in cell)  # pyright: ignore[reportUnknownVariableType] — cell holds a list/ndarray of str

    def pick(cell: object) -> str:
        genres = [str(g) for g in cell]  # pyright: ignore[reportUnknownVariableType, reportGeneralTypeIssues, reportUnknownArgumentType] — cell holds a list/ndarray of str
        if not genres:
            return ""
        return max(genres, key=lambda g: (global_counts[g], g))

    return df["genres"].apply(pick)


def _decade_subbuckets(genre: str, years: pd.Series[int], chunk_count: int) -> list[tuple[str, YearRule | None]]:
    """Split a dominant genre into up to ``chunk_count`` contiguous decade ranges of roughly even size (greedy pack, ascending decades).

    When everything lands in one chunk (a single-decade genre), no year rule applies — the caller gets ``None`` and keeps the plain tag bucket.
    """
    decade_counts = (years // 10 * 10).value_counts().sort_index()
    total = int(decade_counts.sum())
    per_chunk = total / chunk_count
    chunks: list[list[int]] = [[]]
    running = 0
    for decade, count in zip(decade_counts.index.to_numpy(), decade_counts.to_numpy(), strict=True):
        if chunks[-1] and running + int(count) > per_chunk * len(chunks) and len(chunks) < chunk_count:
            chunks.append([])
        chunks[-1].append(int(decade))
        running += int(count)
    if len(chunks) == 1:
        return [(genre.title(), None)]
    result: list[tuple[str, YearRule | None]] = []
    for index, decades in enumerate(chunks):
        lo, hi = min(decades), max(decades) + 9
        min_year = lo if index > 0 else None
        max_year = hi if index < len(chunks) - 1 else None
        label = f"{genre.title()} {lo % 100:02d}s-{max(decades) % 100:02d}s"
        result.append((label, YearRule(min_year=min_year, max_year=max_year)))
    return result


def suggest_split(df: pd.DataFrame, params: SplitParams) -> SplitReport:
    """Propose a bucket layout for a roughly even split of the library.

    Args:
        df: The flattened track DataFrame from ``PlaylistAnalyzer.from_playlist``.
        params: Bucket count target and duplication tolerance.

    Returns:
        The proposed spec plus dry-run numbers and decision notes. For a library without genre data the spec is empty and the notes say why.
    """
    notes: list[str] = []
    if df.empty:
        return SplitReport(spec=OrganizerSpec(), bucket_sizes={}, duplication_rate=0.0, coverage_pct=0.0, notes=("Library is empty — nothing to split.",))

    eligible = df[~(df["is_local"].astype(bool) | df["track_id"].isna())]
    canonical = _canonical_genres(eligible)
    untagged_count = int((canonical == "").sum())
    tagged = eligible[canonical != ""]
    canonical = canonical[canonical != ""]
    if tagged.empty:
        return SplitReport(
            spec=OrganizerSpec(), bucket_sizes={}, duplication_rate=0.0, coverage_pct=0.0, notes=("No genre data (set LASTFM_API_KEY and refresh) — cannot suggest a genre split.",)
        )
    if untagged_count > 0:
        notes.append(f"{untagged_count} tracks have no genre data; they stay in Rest for manual sorting.")

    group_sizes = canonical.value_counts()
    ideal = max(1.0, len(tagged) / params.target_buckets)

    buckets: list[BucketSpec] = []
    packed_labels: list[list[str]] = []
    packed_counts: list[int] = []
    for genre, size in group_sizes.items():
        genre_name = str(genre)
        if int(size) > _DOMINANCE_FACTOR * ideal:
            chunk_count = min(ceil(int(size) / ideal), max(1, params.target_buckets))
            years = tagged.loc[canonical == genre_name, "release_year"].dropna().astype(int)
            if chunk_count > 1 and len(years) >= int(size) * 0.5:
                sub_buckets = _decade_subbuckets(genre_name, years, chunk_count)
                for label, year_rule in sub_buckets:
                    rules: tuple[TagRule | YearRule, ...] = (TagRule(labels=frozenset({genre_name})),) if year_rule is None else (TagRule(labels=frozenset({genre_name})), year_rule)
                    buckets.append(BucketSpec(name=_unique_name(label, buckets), rules=rules))
                if len(sub_buckets) > 1:
                    notes.append(f"'{genre_name}' dominates ({int(size)} tracks, {int(size) / ideal:.1f}x the ideal bucket) — split into {len(sub_buckets)} decade ranges.")
                else:
                    notes.append(f"'{genre_name}' dominates but spans a single decade — kept as one large bucket.")
            else:
                buckets.append(BucketSpec(name=_unique_name(genre_name.title(), buckets), rules=(TagRule(labels=frozenset({genre_name})),)))
                if chunk_count > 1:
                    notes.append(f"'{genre_name}' dominates but lacks release years for a decade split — kept as one large bucket.")
        else:
            # Pack small genres first-fit into shared buckets near the ideal size.
            placed = False
            for index, count in enumerate(packed_counts):
                if count + int(size) <= ideal * 1.2:
                    packed_labels[index].append(genre_name)
                    packed_counts[index] += int(size)
                    placed = True
                    break
            if not placed:
                packed_labels.append([genre_name])
                packed_counts.append(int(size))
    for labels in packed_labels:
        name = labels[0].title() if len(labels) == 1 else f"{labels[0].title()} + {len(labels) - 1} more"
        buckets.append(BucketSpec(name=_unique_name(name, buckets), rules=(TagRule(labels=frozenset(labels)),)))
    if packed_labels:
        notes.append(f"{sum(len(labels) for labels in packed_labels)} smaller genres packed into {len(packed_labels)} shared buckets (first-fit toward {ideal:.0f} tracks each).")

    allow_duplicates = params.duplication_tolerance > 0.0
    if not allow_duplicates:
        notes.append("Tolerance 0: duplicates disabled — first matching bucket wins (bucket order is priority).")

    spec = OrganizerSpec(buckets=tuple(buckets), allow_duplicates=allow_duplicates)
    spec, trim_notes = _trim_overlaps(df, spec, params)
    notes.extend(trim_notes)

    assignment = assign(df, spec)
    stats = summarize(df, assignment)
    assigned = sum(len(ids) for ids in assignment.by_bucket.values()) - stats.duplicate_count
    duplication_rate = stats.duplicate_count / assigned if assigned > 0 else 0.0
    return SplitReport(
        spec=spec,
        bucket_sizes={bucket.name: bucket.count for bucket in stats.buckets},
        duplication_rate=duplication_rate,
        coverage_pct=stats.coverage_pct,
        notes=tuple(notes),
    )


def _unique_name(name: str, existing: list[BucketSpec]) -> str:
    """Ensure bucket-name uniqueness by suffixing a counter when needed."""
    taken = {bucket.name for bucket in existing}
    if name not in taken:
        return name
    counter = 2
    while f"{name} ({counter})" in taken:
        counter += 1
    return f"{name} ({counter})"


def _trim_overlaps(df: pd.DataFrame, spec: OrganizerSpec, params: SplitParams) -> tuple[OrganizerSpec, list[str]]:
    """While the duplication rate exceeds the tolerance, strip the shared labels from the smaller bucket of the heaviest overlap."""
    notes: list[str] = []
    if not spec.allow_duplicates:
        return spec, notes
    for _ in range(_MAX_TRIM_ITERATIONS):
        assignment = assign(df, spec)
        stats = summarize(df, assignment)
        assigned = sum(len(ids) for ids in assignment.by_bucket.values()) - stats.duplicate_count
        rate = stats.duplicate_count / assigned if assigned > 0 else 0.0
        if rate <= params.duplication_tolerance or not stats.overlaps:
            break
        heaviest = stats.overlaps[0]
        sizes = {bucket.name: bucket.count for bucket in stats.buckets}
        smaller, larger = sorted((heaviest.bucket_a, heaviest.bucket_b), key=lambda name: (sizes[name], name))
        smaller_bucket = next(bucket for bucket in spec.buckets if bucket.name == smaller)
        larger_labels = {label for bucket in spec.buckets if bucket.name == larger for rule in bucket.rules if isinstance(rule, TagRule) for label in rule.labels}
        rules: list[Rule] = []
        removed_any = False
        for rule in smaller_bucket.rules:
            if isinstance(rule, TagRule):
                remaining = rule.labels - larger_labels
                if remaining != rule.labels:
                    removed_any = True
                if remaining:
                    rules.append(TagRule(labels=remaining, field=rule.field))
            else:
                rules.append(rule)
        if not removed_any:
            # The overlap comes from multi-genre TRACKS, not shared rule labels — no rule edit can reduce it. First-match-wins resolves it deterministically.
            spec = OrganizerSpec(buckets=spec.buckets, allow_duplicates=False)
            notes.append(f"Duplication {rate:.0%} above tolerance stems from multi-genre tracks — switched to first-match-wins (bucket order is priority).")
            break
        if any(isinstance(rule, TagRule) for rule in rules):
            replacement = BucketSpec(name=smaller_bucket.name, rules=tuple(rules))
            spec = OrganizerSpec(buckets=tuple(replacement if bucket.name == smaller else bucket for bucket in spec.buckets), allow_duplicates=spec.allow_duplicates)
            notes.append(f"Duplication {rate:.0%} above tolerance: removed the labels shared with '{larger}' from '{smaller}'.")
        else:
            spec = OrganizerSpec(buckets=tuple(bucket for bucket in spec.buckets if bucket.name != smaller), allow_duplicates=spec.allow_duplicates)
            notes.append(f"Duplication {rate:.0%} above tolerance: '{smaller}' fully overlapped '{larger}' — dropped it.")
    return spec, notes
