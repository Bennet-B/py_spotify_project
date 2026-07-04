"""Background job registry for the web layer.

Cold-cache Spotify fetches take minutes (one API call per artist), so they must not run inside a request cycle. Routers submit work here and immediately
return a job id; the frontend polls ``GET /api/jobs/{job_id}`` for status and progress. spotipy is synchronous, so jobs run on a small worker-thread pool
while the FastAPI event loop stays free.
"""

from __future__ import annotations

import logging
import threading
import uuid
from collections import OrderedDict
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from ..client import ProgressFn

logger = logging.getLogger(__name__)


class JobStatus(StrEnum):
    """Lifecycle states of a background job."""

    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class JobSnapshot:
    """Immutable point-in-time view of a job, safe to hand across threads.

    Attributes:
        id: Registry-assigned job id.
        kind: Free-form job category (e.g. ``"refresh"``), surfaced to clients.
        status: Current lifecycle state.
        phase: Progress phase reported by the job function (e.g. ``"artists"``).
        done: Items completed within the current phase.
        total: Item count of the current phase, or None while unknown.
        message: Optional human-readable progress message.
        result: The job function's return value once status is DONE, else None.
        error_code: Exception class name once status is ERROR, else None.
        error_message: Stringified exception once status is ERROR, else None.
    """

    id: str
    kind: str
    status: JobStatus
    phase: str
    done: int
    total: int | None
    message: str
    result: dict[str, Any] | None
    error_code: str | None
    error_message: str | None


class _JobState:
    """Mutable internal job record; every access happens under the registry lock."""

    __slots__ = ("done", "error_code", "error_message", "id", "kind", "phase", "result", "status", "total")

    def __init__(self, job_id: str, kind: str) -> None:
        self.id = job_id
        self.kind = kind
        self.status = JobStatus.QUEUED
        self.phase = ""
        self.done = 0
        self.total: int | None = None
        self.result: dict[str, Any] | None = None
        self.error_code: str | None = None
        self.error_message: str | None = None


class JobRegistry:
    """Thread-safe registry that runs job functions on a bounded worker pool.

    Jobs are plain callables taking a progress callback and returning a JSON-serializable result dict. State transitions and progress updates all happen
    under a single lock, and ``get`` returns immutable snapshots, so callers never observe a torn read.
    """

    def __init__(self, *, max_workers: int = 2, max_jobs: int = 50) -> None:
        """Create a registry.

        Args:
            max_workers: Worker threads; 2 keeps a slow cold refresh from blocking a second quick job without inviting rate-limit trouble.
            max_jobs: Total jobs retained for polling; the oldest *finished* jobs beyond this are evicted, running jobs never are.
        """
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="job")
        self._lock = threading.Lock()
        self._jobs: OrderedDict[str, _JobState] = OrderedDict()
        self._active_by_key: dict[str, str] = {}
        self._max_jobs = max_jobs

    def submit(self, *, kind: str, fn: Callable[[ProgressFn], dict[str, Any]], dedupe_key: str | None = None) -> str:
        """Queue ``fn`` for execution and return its job id.

        Args:
            kind: Job category label surfaced to clients.
            fn: Job body; receives a thread-safe progress callback and returns the job result.
            dedupe_key: When set and a job with the same key is queued or running, that job's id is returned instead of starting a duplicate.

        Returns:
            The id of the newly created job, or of the deduplicated existing one.
        """
        with self._lock:
            if dedupe_key is not None:
                existing = self._active_by_key.get(dedupe_key)
                if existing is not None:
                    logger.info("Deduplicated %s job onto %s (key %s)", kind, existing, dedupe_key)
                    return existing
            job_id = uuid.uuid4().hex
            self._jobs[job_id] = _JobState(job_id, kind)
            if dedupe_key is not None:
                self._active_by_key[dedupe_key] = job_id
            self._evict_finished_locked()
        self._executor.submit(self._run, job_id, fn, dedupe_key)
        return job_id

    def get(self, job_id: str) -> JobSnapshot | None:
        """Return an immutable snapshot of the job, or None if unknown (never created, or already evicted)."""
        with self._lock:
            state = self._jobs.get(job_id)
            if state is None:
                return None
            return JobSnapshot(
                id=state.id,
                kind=state.kind,
                status=state.status,
                phase=state.phase,
                done=state.done,
                total=state.total,
                message="",
                result=state.result,
                error_code=state.error_code,
                error_message=state.error_message,
            )

    def shutdown(self) -> None:
        """Stop accepting work and wait for running jobs to finish (used by tests and app shutdown)."""
        self._executor.shutdown(wait=True)

    def _run(self, job_id: str, fn: Callable[[ProgressFn], dict[str, Any]], dedupe_key: str | None) -> None:
        """Worker-thread entry point: execute ``fn`` and record its outcome."""

        def report(phase: str, done: int, total: int | None) -> None:
            with self._lock:
                state = self._jobs.get(job_id)
                if state is not None:
                    state.phase = phase
                    state.done = done
                    state.total = total

        with self._lock:
            state = self._jobs.get(job_id)
            if state is None:
                return
            state.status = JobStatus.RUNNING
        try:
            result = fn(report)
        except Exception as exc:  # job boundary: whatever the job raises must land in its status, not kill the worker thread
            logger.exception("Job %s failed", job_id)
            with self._lock:
                state = self._jobs.get(job_id)
                if state is not None:
                    state.status = JobStatus.ERROR
                    state.error_code = type(exc).__name__
                    state.error_message = str(exc)
                self._release_key_locked(dedupe_key, job_id)
            return
        with self._lock:
            state = self._jobs.get(job_id)
            if state is not None:
                state.status = JobStatus.DONE
                state.result = result
            self._release_key_locked(dedupe_key, job_id)

    def _release_key_locked(self, dedupe_key: str | None, job_id: str) -> None:
        """Free the dedupe key if it still points at this job; caller holds the lock."""
        if dedupe_key is not None and self._active_by_key.get(dedupe_key) == job_id:
            del self._active_by_key[dedupe_key]

    def _evict_finished_locked(self) -> None:
        """Drop the oldest finished jobs beyond ``max_jobs``; caller holds the lock."""
        overflow = len(self._jobs) - self._max_jobs
        if overflow <= 0:
            return
        finished = [jid for jid, s in self._jobs.items() if s.status in (JobStatus.DONE, JobStatus.ERROR)]
        for jid in finished[:overflow]:
            del self._jobs[jid]
