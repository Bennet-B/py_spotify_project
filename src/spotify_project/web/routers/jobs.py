"""Job polling endpoint."""

from __future__ import annotations

from fastapi import APIRouter

from ..deps import JobRegistryDep
from ..errors import NotFoundError
from ..schemas import JobOut

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("/{job_id}")
def get_job(job_id: str, registry: JobRegistryDep) -> JobOut:
    """Return the current snapshot of a background job.

    Raises:
        NotFoundError: Mapped to HTTP 404 when the job id is unknown or already evicted.
    """
    snap = registry.get(job_id)
    if snap is None:
        raise NotFoundError(f"Unknown job id: {job_id}")
    return JobOut.from_snapshot(snap)
