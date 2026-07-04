"""Organizer endpoints: dry-run preview, Apply (create-only, batch-grouped), and the batch history.

Preview is synchronous and pure — it never touches Spotify. Apply is the only mutating path in the whole API and always CREATES new playlists;
existing playlists are never modified. Spotify has no folder API, so grouping = shared ``[batch]`` name prefix + description marker + local history.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter

from ... import organizer
from ...client import ProgressFn, SpotifyClient
from ..batches import Batch, BatchStore, CreatedPlaylist
from ..deps import BatchStoreDep, ClientDep, DatasetStoreDep, JobRegistryDep
from ..schemas import (
    ApplyRequest,
    BatchesResponse,
    BatchOut,
    BucketPreview,
    JobAccepted,
    OverlapOut,
    PreviewRequest,
    PreviewResponse,
    PreviewStats,
    to_core_spec,
)

router = APIRouter(prefix="/organizer", tags=["organizer"])


@router.post("/preview")
def preview(body: PreviewRequest, store: DatasetStoreDep) -> PreviewResponse:
    """Dry-run the spec against the loaded playlist: bucket contents and stats, nothing written anywhere.

    Raises:
        DatasetNotLoadedError: Mapped to 409 when the playlist has no loaded dataset.
        ValueError: Mapped to 400 for invalid specs (inverted bounds, duplicate bucket names, ...).
    """
    dataset = store.require(body.playlist_id)
    spec = to_core_spec(body.spec)
    assignment = organizer.assign(dataset.df, spec)
    stats = organizer.summarize(dataset.df, assignment)
    return PreviewResponse(
        buckets=[
            BucketPreview(name=bucket.name, count=bucket.count, duration_ms_total=bucket.duration_ms_total, track_ids=list(assignment.by_bucket[bucket.name])) for bucket in stats.buckets
        ],
        rest_track_ids=list(assignment.rest),
        rest_count=stats.rest_count,
        stats=PreviewStats(
            coverage_pct=stats.coverage_pct,
            duplicate_count=stats.duplicate_count,
            overlaps=[OverlapOut(bucket_a=pair.bucket_a, bucket_b=pair.bucket_b, count=pair.count) for pair in stats.overlaps],
            skipped_local_count=stats.skipped_local_count,
        ),
    )


@router.post("/apply", status_code=202)
def apply(body: ApplyRequest, store: DatasetStoreDep, client: ClientDep, registry: JobRegistryDep, batch_store: BatchStoreDep) -> JobAccepted:
    """Materialize chosen buckets as NEW playlists under a named batch (background job).

    Validation happens before the job starts so spec errors surface synchronously; the job then re-runs the pure assignment and performs the
    only writes in the API: create playlist + add tracks per non-empty bucket. Empty buckets are skipped and reported.

    Raises:
        DatasetNotLoadedError: Mapped to 409 when the playlist has no loaded dataset.
        ValueError: Mapped to 400 for invalid specs or bucket_names not present in the spec.
    """
    dataset = store.require(body.playlist_id)
    spec = to_core_spec(body.spec)
    known = {bucket.name for bucket in spec.buckets}
    unknown = [name for name in body.bucket_names if name not in known]
    if unknown:
        raise ValueError(f"bucket_names not in spec: {unknown}")

    def run(progress: ProgressFn) -> dict[str, Any]:
        return _run_apply(body, spec, dataset.df, client, batch_store, progress)

    job_id = registry.submit(kind="apply", fn=run, dedupe_key=f"apply:{body.batch_name}")
    return JobAccepted(job_id=job_id)


@router.get("/batches")
def batches(batch_store: BatchStoreDep) -> BatchesResponse:
    """The local history of Apply batches, newest first."""
    return BatchesResponse(batches=[BatchOut.from_batch(batch) for batch in batch_store.all_batches()])


def _run_apply(body: ApplyRequest, spec: organizer.OrganizerSpec, df: Any, client: SpotifyClient, batch_store: BatchStore, progress: ProgressFn) -> dict[str, Any]:
    """Job body for Apply: create one playlist per chosen non-empty bucket and record the batch."""
    assignment = organizer.assign(df, spec)
    targets: list[tuple[str, tuple[str, ...]]] = [(name, assignment.by_bucket[name]) for name in body.bucket_names]
    if body.include_rest:
        targets.append((body.rest_name, assignment.rest))

    description = f"created by spotify_project · batch {body.batch_name} · {datetime.now(UTC).date().isoformat()}"
    created: list[CreatedPlaylist] = []
    skipped_empty: list[str] = []
    for index, (bucket_name, track_ids) in enumerate(targets, start=1):
        progress("buckets", index, len(targets))
        if not track_ids:
            skipped_empty.append(bucket_name)
            continue
        playlist_id = client.create_playlist(f"[{body.batch_name}] {bucket_name}", public=body.public, description=description)
        added = client.add_tracks(playlist_id, track_ids, on_progress=progress)
        created.append(CreatedPlaylist(bucket_name=bucket_name, playlist_id=playlist_id, url=f"https://open.spotify.com/playlist/{playlist_id}", added=added))

    batch = Batch(batch_name=body.batch_name, created_at=datetime.now(UTC).isoformat(), source_playlist_id=body.playlist_id, created=tuple(created))
    batch_store.append(batch)
    return {
        "batch_name": body.batch_name,
        "created": [{"bucket_name": c.bucket_name, "playlist_id": c.playlist_id, "url": c.url, "added": c.added} for c in created],
        "skipped_empty": skipped_empty,
        "skipped_local": len(assignment.skipped_local),
    }
