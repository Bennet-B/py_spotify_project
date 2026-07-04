"""Tests for the background JobRegistry — threading, progress, dedupe, and error capture."""

from __future__ import annotations

import threading
import time
from typing import Any

import pytest

from spotify_project.client import ProgressFn
from spotify_project.web.jobs import JobRegistry, JobSnapshot, JobStatus


def _wait_until_finished(registry: JobRegistry, job_id: str, *, timeout: float = 5.0) -> JobSnapshot:
    """Poll the registry until the job reaches a terminal state, failing the test on timeout."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        snap = registry.get(job_id)
        assert snap is not None, f"job {job_id} vanished from the registry"
        if snap.status in (JobStatus.DONE, JobStatus.ERROR):
            return snap
        time.sleep(0.01)
    pytest.fail(f"Job {job_id} did not finish within {timeout}s")


@pytest.fixture
def registry() -> Any:
    """A fresh single-worker registry, shut down after the test."""
    reg = JobRegistry(max_workers=1, max_jobs=10)
    yield reg
    reg.shutdown()


class TestJobLifecycle:
    """Success, progress, and error paths."""

    def test_success_reports_progress_and_result(self, registry: JobRegistry) -> None:
        """A finished job exposes DONE status, its result dict, and the last progress report."""

        def work(progress: ProgressFn) -> dict[str, Any]:
            progress("artists", 3, 7)
            return {"track_count": 42}

        job_id = registry.submit(kind="refresh", fn=work)
        snap = _wait_until_finished(registry, job_id)

        assert snap.status is JobStatus.DONE
        assert snap.result == {"track_count": 42}
        assert (snap.phase, snap.done, snap.total) == ("artists", 3, 7)
        assert snap.error_code is None

    def test_exception_lands_in_error_state(self, registry: JobRegistry) -> None:
        """A raising job records ERROR with the exception class name and message; the worker survives."""

        def work(progress: ProgressFn) -> dict[str, Any]:
            raise ValueError("boom")

        job_id = registry.submit(kind="refresh", fn=work)
        snap = _wait_until_finished(registry, job_id)

        assert snap.status is JobStatus.ERROR
        assert snap.error_code == "ValueError"
        assert snap.error_message == "boom"
        assert snap.result is None

    def test_unknown_job_returns_none(self, registry: JobRegistry) -> None:
        """Unknown ids yield None rather than raising."""
        assert registry.get("nope") is None


class TestDedupe:
    """The dedupe_key semantics: join active jobs, never finished ones."""

    def test_same_key_joins_running_job(self, registry: JobRegistry) -> None:
        """While a keyed job runs, resubmitting the key returns the same id; after it finishes, a new job starts."""
        release = threading.Event()

        def blocked(progress: ProgressFn) -> dict[str, Any]:
            release.wait(timeout=5)
            return {}

        first = registry.submit(kind="refresh", fn=blocked, dedupe_key="refresh:pl1")
        joined = registry.submit(kind="refresh", fn=blocked, dedupe_key="refresh:pl1")
        other = registry.submit(kind="refresh", fn=lambda progress: {}, dedupe_key="refresh:pl2")
        assert joined == first
        assert other != first

        release.set()
        _wait_until_finished(registry, first)
        fresh = registry.submit(kind="refresh", fn=lambda progress: {}, dedupe_key="refresh:pl1")
        assert fresh != first
        _wait_until_finished(registry, fresh)
        _wait_until_finished(registry, other)


class TestEviction:
    """Finished jobs are evicted beyond max_jobs; running jobs never are."""

    def test_oldest_finished_evicted_beyond_max_jobs(self) -> None:
        """Submitting past the cap drops the oldest finished job from polling."""
        reg = JobRegistry(max_workers=1, max_jobs=2)
        try:
            ids = [reg.submit(kind="quick", fn=lambda progress: {}) for _ in range(2)]
            for job_id in ids:
                _wait_until_finished(reg, job_id)
            third = reg.submit(kind="quick", fn=lambda progress: {})
            _wait_until_finished(reg, third)
            assert reg.get(ids[0]) is None
            assert reg.get(third) is not None
        finally:
            reg.shutdown()
