"""Set-analysis endpoints: the scoped scan (overlaps, duplication, unorganized report), the placeholder sweep, and suggest-split.

The scan loads every selected playlist (cache-first) inside a job, stores the datasets for instant exploring afterwards, and records its typed
result as the job result; ``scan-result`` re-validates it into the OpenAPI schema so the frontend gets generated types instead of a blob.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

from fastapi import APIRouter

from ... import set_analysis
from ...analyzer import PlaylistAnalyzer
from ...client import ProgressFn, SpotifyClient
from ...suggest_split import SplitParams, suggest_split
from ..batches import Batch, CreatedPlaylist
from ..dataset import Dataset
from ..deps import BatchStoreDep, ClientDep, DatasetStoreDep, JobRegistryDep
from ..errors import NotFoundError
from ..jobs import JobStatus
from ..schemas import (
    DuplicatedTrackOut,
    JobAccepted,
    OverlapPairOut,
    ScannedPlaylistOut,
    ScanRequest,
    ScanResultResponse,
    SuggestSplitRequest,
    SuggestSplitResponse,
    SweepRequest,
    UnorganizedOut,
    from_core_spec,
)
from .playlists import LIKED_PLAYLIST_ID

router = APIRouter(prefix="/analysis", tags=["analysis"])

# Display cap for the duplication table; the full count still ships as duplication_total.
_DUPLICATION_ROW_CAP = 200
_UNORGANIZED_SAMPLE_SIZE = 50


def _fetch(client: SpotifyClient, playlist_id: str, on_progress: ProgressFn | None = None) -> Any:
    """Cache-first fetch of a real playlist or the Liked Songs pseudo-playlist."""
    if playlist_id == LIKED_PLAYLIST_ID:
        return client.fetch_liked_songs(on_progress=on_progress)
    return client.fetch_playlist(playlist_id, on_progress=on_progress)


@router.post("/scan", status_code=202)
def scan(body: ScanRequest, client: ClientDep, store: DatasetStoreDep, registry: JobRegistryDep) -> JobAccepted:
    """Load the selected sources and subsets (cache-first, background job) and compute the full set-analysis.

    Raises:
        ValueError: Mapped to 400 when a playlist appears in both roles.
    """
    both = set(body.source_ids) & set(body.subset_ids)
    if both:
        raise ValueError(f"Playlists cannot be source and subset at once: {sorted(both)}")

    def run(progress: ProgressFn) -> dict[str, Any]:
        all_ids = [*body.source_ids, *body.subset_ids]
        sets_by_id: dict[str, set_analysis.PlaylistTrackSet] = {}
        names_by_track: dict[str, str] = {}
        scanned: list[ScannedPlaylistOut] = []
        for index, playlist_id in enumerate(all_ids, start=1):
            progress("playlists", index, len(all_ids))
            playlist = _fetch(client, playlist_id)
            store.put(playlist_id, Dataset(playlist=playlist, df=PlaylistAnalyzer.from_playlist(playlist).df, loaded_at=datetime.now(UTC)))
            track_ids = frozenset(track.id for track in playlist.tracks if track.id is not None and not track.is_local)
            sets_by_id[playlist_id] = set_analysis.PlaylistTrackSet(playlist_id=playlist_id, name=playlist.name, track_ids=track_ids)
            for track in playlist.tracks:
                if track.id is not None:
                    names_by_track[track.id] = f"{track.name} — {track.primary_artist.name}" if track.primary_artist is not None else track.name
            scanned.append(ScannedPlaylistOut(id=playlist_id, name=playlist.name, track_count=len(track_ids), role="source" if playlist_id in body.source_ids else "subset"))

        sources = [sets_by_id[playlist_id] for playlist_id in body.source_ids]
        subsets = [sets_by_id[playlist_id] for playlist_id in body.subset_ids]
        pairs = set_analysis.overlap_pairs([*sources, *subsets])
        membership = set_analysis.track_membership(subsets)
        duplicated = membership[membership["n_playlists"] > 1]
        uncovered = sorted(set_analysis.unorganized(sources, subsets))

        result = ScanResultResponse(
            playlists=scanned,
            pairs=[OverlapPairOut(**record) for record in cast("list[dict[str, Any]]", pairs.to_dict("records"))],
            duplication=[
                DuplicatedTrackOut(
                    track_id=str(row["track_id"]),
                    name=names_by_track.get(str(row["track_id"]), str(row["track_id"])),
                    n_playlists=int(row["n_playlists"]),
                    playlist_names=list(row["playlist_names"]),
                )
                for row in cast("list[dict[str, Any]]", duplicated.head(_DUPLICATION_ROW_CAP).to_dict("records"))
            ],
            duplication_total=len(duplicated),
            unorganized=UnorganizedOut(
                count=len(uncovered), track_ids=list(uncovered), sample_names=[names_by_track.get(track_id, track_id) for track_id in uncovered[:_UNORGANIZED_SAMPLE_SIZE]]
            ),
        )
        return result.model_dump(mode="json")

    job_id = registry.submit(kind="scan", fn=run, dedupe_key=f"scan:{','.join(sorted([*body.source_ids, *body.subset_ids]))}")
    return JobAccepted(job_id=job_id)


@router.get("/scan-result/{job_id}")
def scan_result(job_id: str, registry: JobRegistryDep) -> ScanResultResponse:
    """The typed result of a finished scan job.

    Raises:
        NotFoundError: Mapped to 404 for unknown jobs, jobs that are not scans, or jobs that have not finished successfully.
    """
    snap = registry.get(job_id)
    if snap is None or snap.kind != "scan" or snap.status is not JobStatus.DONE or snap.result is None:
        raise NotFoundError(f"No finished scan result for job {job_id}")
    return ScanResultResponse.model_validate(snap.result)


@router.post("/sweep", status_code=202)
def sweep(body: SweepRequest, client: ClientDep, registry: JobRegistryDep, batch_store: BatchStoreDep) -> JobAccepted:
    """Create a placeholder playlist from unorganized tracks so they can be sorted manually (background job)."""

    def run(progress: ProgressFn) -> dict[str, Any]:
        user = client.fetch_current_user()
        description = f"created by spotify_project · unorganized sweep · {datetime.now(UTC).date().isoformat()}"
        playlist_id = client.create_playlist(user.id, body.name, public=False, description=description)
        added = client.add_tracks(playlist_id, body.track_ids, on_progress=progress)
        url = f"https://open.spotify.com/playlist/{playlist_id}"
        batch_store.append(
            Batch(
                batch_name=body.name,
                created_at=datetime.now(UTC).isoformat(),
                source_playlist_id="unorganized-sweep",
                created=(CreatedPlaylist(bucket_name="Unorganized", playlist_id=playlist_id, url=url, added=added),),
            )
        )
        return {"playlist_id": playlist_id, "url": url, "added": added}

    job_id = registry.submit(kind="sweep", fn=run, dedupe_key=f"sweep:{body.name}")
    return JobAccepted(job_id=job_id)


@router.post("/suggest-split")
def suggest(body: SuggestSplitRequest, store: DatasetStoreDep) -> SuggestSplitResponse:
    """Propose an even bucket layout for the playlist — pure computation, nothing written; load the spec into the organizer to use it.

    Raises:
        DatasetNotLoadedError: Mapped to 409 when the playlist has no loaded dataset.
    """
    dataset = store.require(body.playlist_id)
    report = suggest_split(dataset.df, SplitParams(target_buckets=body.target_buckets, duplication_tolerance=body.duplication_tolerance))
    return SuggestSplitResponse(
        spec=from_core_spec(report.spec),
        bucket_sizes=dict(report.bucket_sizes),
        duplication_rate=report.duplication_rate,
        coverage_pct=report.coverage_pct,
        notes=list(report.notes),
    )
