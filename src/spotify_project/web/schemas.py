"""Pydantic models forming the API boundary.

The core keeps frozen dataclasses (it has no serialization concern); pydantic lives exactly here, where request validation and OpenAPI generation are the
job. The OpenAPI schema generated from these models is the source of truth for the frontend's generated TypeScript types (``npm run gen:api``).
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal, cast

import pandas as pd
from pydantic import BaseModel, Field

from .. import organizer
from .batches import Batch
from .jobs import JobSnapshot, JobStatus


class HealthResponse(BaseModel):
    """Liveness probe body."""

    status: Literal["ok"]


class MeResponse(BaseModel):
    """The authenticated Spotify user."""

    id: str
    display_name: str


class PlaylistItem(BaseModel):
    """One sidebar entry; id ``__liked__`` is the synthetic Liked Songs pseudo-playlist.

    ``track_count`` is None when unknown (Liked Songs before its first load). ``cached_at`` is the raw-response cache write time, or None when uncached/stale.
    """

    id: str
    name: str
    owner_name: str
    track_count: int | None
    public: bool
    is_liked: bool
    loaded: bool
    cached_at: datetime | None


class PlaylistsResponse(BaseModel):
    """Response of ``GET /api/playlists``."""

    items: list[PlaylistItem]


class RefreshRequest(BaseModel):
    """Body of ``POST /api/playlists/{id}/refresh``; ``force`` bypasses the response cache."""

    force: bool = False


class JobAccepted(BaseModel):
    """202 response carrying the id to poll at ``GET /api/jobs/{job_id}``."""

    job_id: str


class JobProgressOut(BaseModel):
    """Progress block of a job snapshot."""

    phase: str
    done: int
    total: int | None
    message: str


class JobErrorOut(BaseModel):
    """Error block of a failed job."""

    code: str
    message: str


class JobOut(BaseModel):
    """Response of ``GET /api/jobs/{job_id}``."""

    id: str
    kind: str
    status: JobStatus
    progress: JobProgressOut
    result: dict[str, Any] | None
    error: JobErrorOut | None

    @classmethod
    def from_snapshot(cls, snap: JobSnapshot) -> JobOut:
        """Convert a registry snapshot into the wire shape.

        Args:
            snap: The immutable snapshot returned by ``JobRegistry.get``.

        Returns:
            The corresponding response model.
        """
        error = JobErrorOut(code=snap.error_code, message=snap.error_message or "") if snap.error_code is not None else None
        progress = JobProgressOut(phase=snap.phase, done=snap.done, total=snap.total, message=snap.message)
        return cls(id=snap.id, kind=snap.kind, status=snap.status, progress=progress, result=snap.result, error=error)


class TrackRow(BaseModel):
    """One flattened track, mirroring the columns of ``PlaylistAnalyzer.from_playlist``'s DataFrame."""

    track_id: str | None
    name: str
    primary_artist_id: str | None
    primary_artist_name: str
    artist_ids: list[str]
    artist_names: list[str]
    album_name: str
    release_year: int | None
    duration_ms: int
    explicit: bool
    added_at: datetime | None
    is_local: bool
    tags: list[str]
    genres: list[str]


class TracksResponse(BaseModel):
    """Response of ``GET /api/playlists/{id}/tracks``."""

    playlist_id: str
    name: str
    tracks: list[TrackRow]


class LabelCountRow(BaseModel):
    """One bar of the tag/genre frequency chart."""

    label: str
    count: int


class LabelsResponse(BaseModel):
    """Response of ``GET .../insights/labels``; ``field`` echoes which label column was counted."""

    field: Literal["genres", "tags"]
    rows: list[LabelCountRow]


class YearCountRow(BaseModel):
    """One pre-binned bar of the release-year chart (clicks map to exact years)."""

    year: int
    count: int


class YearsResponse(BaseModel):
    """Response of ``GET .../insights/years``."""

    rows: list[YearCountRow]


class AdditionRow(BaseModel):
    """One period of the library-growth chart."""

    period: datetime
    added: int
    cumulative_tracks: int
    cumulative_hours: float


class AdditionsResponse(BaseModel):
    """Response of ``GET .../insights/additions``."""

    freq: str
    rows: list[AdditionRow]


class DiscoveryRow(BaseModel):
    """One period of the artist-discovery-waves chart."""

    period: datetime
    new_artists: int


class DiscoveryResponse(BaseModel):
    """Response of ``GET .../insights/discovery``."""

    freq: str
    rows: list[DiscoveryRow]


class SeasonalRow(BaseModel):
    """One calendar month of the seasonal-profile chart (always 12 rows)."""

    month: int
    month_name: str
    added: int


class SeasonalResponse(BaseModel):
    """Response of ``GET .../insights/seasonal``."""

    rows: list[SeasonalRow]


class ArtistCountRow(BaseModel):
    """One bar of the (optionally genre-scoped) artist chart."""

    artist_id: str
    artist_name: str
    track_count: int


class ArtistsResponse(BaseModel):
    """Response of ``GET .../insights/artists``; ``scoped_to_genres`` echoes the cascading genre filter."""

    scoped_to_genres: list[str]
    rows: list[ArtistCountRow]


class ReleaseVsAddedRow(BaseModel):
    """One dot of the release-vs-added scatter; ``track_id`` is None for local files (excluded from lasso selections)."""

    track_id: str | None
    release_year: int
    added_year: int
    track: str
    artist: str


class ReleaseVsAddedResponse(BaseModel):
    """Response of ``GET .../insights/release-vs-added``."""

    rows: list[ReleaseVsAddedRow]


class TagRuleIn(BaseModel):
    """Boundary mirror of ``organizer.TagRule``: match any of the labels (case-insensitive) in the chosen field."""

    kind: Literal["tag"] = "tag"
    labels: list[str] = Field(min_length=1)
    field: Literal["genres", "tags"] = "genres"


class YearRuleIn(BaseModel):
    """Boundary mirror of ``organizer.YearRule``; bound validation happens in the core dataclass."""

    kind: Literal["year"] = "year"
    min_year: int | None = None
    max_year: int | None = None


class DurationRuleIn(BaseModel):
    """Boundary mirror of ``organizer.DurationRule`` (whole seconds)."""

    kind: Literal["duration"] = "duration"
    min_seconds: int | None = None
    max_seconds: int | None = None


class ArtistRuleIn(BaseModel):
    """Boundary mirror of ``organizer.ArtistRule``: match any credited artist."""

    kind: Literal["artist"] = "artist"
    artist_ids: list[str] = Field(min_length=1)


class TrackRuleIn(BaseModel):
    """Boundary mirror of ``organizer.TrackRule``: an explicit track-id set (the lasso selection)."""

    kind: Literal["track"] = "track"
    track_ids: list[str] = Field(min_length=1)


type RuleIn = Annotated[TagRuleIn | YearRuleIn | DurationRuleIn | ArtistRuleIn | TrackRuleIn, Field(discriminator="kind")]


class BucketSpecIn(BaseModel):
    """One named bucket; rules AND together."""

    name: str = Field(min_length=1)
    rules: list[RuleIn] = Field(default_factory=list[RuleIn])


class OrganizerSpecIn(BaseModel):
    """The organizer configuration as sent by the frontend."""

    buckets: list[BucketSpecIn] = Field(default_factory=list[BucketSpecIn])
    allow_duplicates: bool = True


def to_core_spec(spec: OrganizerSpecIn) -> organizer.OrganizerSpec:
    """Convert the boundary spec into core dataclasses.

    Core ``__post_init__`` invariants (inverted bounds, duplicate bucket names, ...) raise ValueError, which the error handlers map to HTTP 400.

    Args:
        spec: The validated request body.

    Returns:
        The equivalent ``organizer.OrganizerSpec``.
    """

    def to_rule(rule: TagRuleIn | YearRuleIn | DurationRuleIn | ArtistRuleIn | TrackRuleIn) -> organizer.Rule:
        match rule:
            case TagRuleIn():
                return organizer.TagRule(labels=frozenset(rule.labels), field=rule.field)
            case YearRuleIn():
                return organizer.YearRule(min_year=rule.min_year, max_year=rule.max_year)
            case DurationRuleIn():
                return organizer.DurationRule(min_seconds=rule.min_seconds, max_seconds=rule.max_seconds)
            case ArtistRuleIn():
                return organizer.ArtistRule(artist_ids=frozenset(rule.artist_ids))
            case TrackRuleIn():
                return organizer.TrackRule(track_ids=frozenset(rule.track_ids))

    return organizer.OrganizerSpec(
        buckets=tuple(organizer.BucketSpec(name=bucket.name, rules=tuple(to_rule(rule) for rule in bucket.rules)) for bucket in spec.buckets),
        allow_duplicates=spec.allow_duplicates,
    )


class PreviewRequest(BaseModel):
    """Body of ``POST /api/organizer/preview``."""

    playlist_id: str
    spec: OrganizerSpecIn


class BucketPreview(BaseModel):
    """One bucket's dry-run result."""

    name: str
    count: int
    duration_ms_total: int
    track_ids: list[str]


class OverlapOut(BaseModel):
    """Tracks shared by two buckets."""

    bucket_a: str
    bucket_b: str
    count: int


class PreviewStats(BaseModel):
    """Aggregate dry-run numbers."""

    coverage_pct: float
    duplicate_count: int
    overlaps: list[OverlapOut]
    skipped_local_count: int


class PreviewResponse(BaseModel):
    """Response of ``POST /api/organizer/preview`` — a pure dry-run, nothing written."""

    buckets: list[BucketPreview]
    rest_track_ids: list[str]
    rest_count: int
    stats: PreviewStats


class ApplyRequest(BaseModel):
    """Body of ``POST /api/organizer/apply``: which buckets of the spec to materialize, under which batch name."""

    playlist_id: str
    spec: OrganizerSpecIn
    bucket_names: list[str] = Field(min_length=1)
    include_rest: bool = False
    rest_name: str = Field(default="Rest", min_length=1)
    public: bool = False
    batch_name: str = Field(min_length=1)


class CreatedPlaylistOut(BaseModel):
    """One playlist created by an Apply."""

    bucket_name: str
    playlist_id: str
    url: str
    added: int


class BatchOut(BaseModel):
    """One recorded Apply batch."""

    batch_name: str
    created_at: str
    source_playlist_id: str
    created: list[CreatedPlaylistOut]

    @classmethod
    def from_batch(cls, batch: Batch) -> BatchOut:
        """Convert a stored batch into the wire shape."""
        return cls(
            batch_name=batch.batch_name,
            created_at=batch.created_at,
            source_playlist_id=batch.source_playlist_id,
            created=[CreatedPlaylistOut(bucket_name=c.bucket_name, playlist_id=c.playlist_id, url=c.url, added=c.added) for c in batch.created],
        )


class BatchesResponse(BaseModel):
    """Response of ``GET /api/organizer/batches``, newest first."""

    batches: list[BatchOut]


def from_core_spec(spec: organizer.OrganizerSpec) -> OrganizerSpecIn:
    """Convert a core spec back into the boundary shape (used by suggest-split so the frontend can load the proposal into the organizer)."""

    def to_rule_in(rule: organizer.Rule) -> TagRuleIn | YearRuleIn | DurationRuleIn | ArtistRuleIn | TrackRuleIn:
        match rule:
            case organizer.TagRule():
                return TagRuleIn(labels=sorted(rule.labels), field=rule.field)
            case organizer.YearRule():
                return YearRuleIn(min_year=rule.min_year, max_year=rule.max_year)
            case organizer.DurationRule():
                return DurationRuleIn(min_seconds=rule.min_seconds, max_seconds=rule.max_seconds)
            case organizer.ArtistRule():
                return ArtistRuleIn(artist_ids=sorted(rule.artist_ids))
            case organizer.TrackRule():
                return TrackRuleIn(track_ids=sorted(rule.track_ids))

    return OrganizerSpecIn(
        buckets=[BucketSpecIn(name=bucket.name, rules=[to_rule_in(rule) for rule in bucket.rules]) for bucket in spec.buckets],
        allow_duplicates=spec.allow_duplicates,
    )


class ScanRequest(BaseModel):
    """Body of ``POST /api/analysis/scan``: the user-selected analysis scope."""

    source_ids: list[str] = Field(min_length=1)
    subset_ids: list[str] = Field(default_factory=list[str])


class ScannedPlaylistOut(BaseModel):
    """One playlist that participated in a scan."""

    id: str
    name: str
    track_count: int
    role: Literal["source", "subset"]


class OverlapPairOut(BaseModel):
    """Pairwise overlap metrics between two scanned playlists."""

    a_id: str
    a_name: str
    b_id: str
    b_name: str
    intersection: int
    jaccard: float
    containment_a_in_b: float
    containment_b_in_a: float


class DuplicatedTrackOut(BaseModel):
    """One track living in several of the selected sub-playlists."""

    track_id: str
    name: str
    n_playlists: int
    playlist_names: list[str]


class UnorganizedOut(BaseModel):
    """The songs-without-a-place report; ``track_ids`` is complete (it feeds the sweep), ``sample_names`` is display-sized."""

    count: int
    track_ids: list[str]
    sample_names: list[str]


class ScanResultResponse(BaseModel):
    """Typed view of a finished scan job (``GET /api/analysis/scan-result/{job_id}``)."""

    playlists: list[ScannedPlaylistOut]
    pairs: list[OverlapPairOut]
    duplication: list[DuplicatedTrackOut]
    duplication_total: int
    unorganized: UnorganizedOut


class SweepRequest(BaseModel):
    """Body of ``POST /api/analysis/sweep``: create a placeholder playlist from unorganized tracks."""

    name: str = Field(min_length=1)
    track_ids: list[str] = Field(min_length=1)


class SuggestSplitRequest(BaseModel):
    """Body of ``POST /api/analysis/suggest-split``."""

    playlist_id: str
    target_buckets: int = Field(ge=1, le=50)
    duplication_tolerance: float = Field(default=0.15, ge=0.0, le=1.0)


class SuggestSplitResponse(BaseModel):
    """The proposed spec (ready to load into the organizer) plus its dry-run numbers and decision notes."""

    spec: OrganizerSpecIn
    bucket_sizes: dict[str, int]
    duplication_rate: float
    coverage_pct: float
    notes: list[str]


def track_rows_from_df(df: pd.DataFrame) -> list[TrackRow]:
    """Convert the flattened track DataFrame into wire-ready rows.

    Handles pandas nullability at the boundary: ``NaT`` added_at and ``pd.NA`` release_year become None; list-valued columns are copied into plain lists;
    the occasional None artist id of a local file is dropped rather than serialized.

    Args:
        df: The DataFrame produced by ``PlaylistAnalyzer.from_playlist``.

    Returns:
        One ``TrackRow`` per DataFrame row, in DataFrame order.
    """
    rows: list[TrackRow] = []
    for rec in cast("list[dict[str, Any]]", df.to_dict("records")):
        release_year = rec["release_year"]
        added_at = rec["added_at"]
        rows.append(
            TrackRow(
                track_id=rec["track_id"],
                name=rec["name"],
                primary_artist_id=rec["primary_artist_id"],
                primary_artist_name=rec["primary_artist_name"],
                artist_ids=[a for a in rec["artist_ids"] if a is not None],
                artist_names=list(rec["artist_names"]),
                album_name=rec["album_name"],
                release_year=None if pd.isna(release_year) else int(release_year),
                duration_ms=int(rec["duration_ms"]),
                explicit=bool(rec["explicit"]),
                added_at=None if pd.isna(added_at) else added_at.to_pydatetime(),
                is_local=bool(rec["is_local"]),
                tags=list(rec["tags"]),
                genres=list(rec["genres"]),
            )
        )
    return rows
