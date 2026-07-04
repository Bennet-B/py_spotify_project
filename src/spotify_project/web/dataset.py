"""In-process store of loaded playlist datasets.

A refresh job produces a ``Playlist`` plus its flattened track DataFrame (via ``PlaylistAnalyzer.from_playlist``). Rebuilding that DataFrame from the
multi-MB cache JSON on every request would dominate response time, so the web layer keeps loaded datasets in memory and serves all reads from here.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime

import pandas as pd

from ..models import Playlist


@dataclass(frozen=True, slots=True)
class Dataset:
    """A loaded playlist and its flattened per-track DataFrame.

    Attributes:
        playlist: The fully-enriched source playlist.
        df: One-row-per-track DataFrame from ``PlaylistAnalyzer.from_playlist``.
        loaded_at: When the refresh job stored this dataset (UTC).
    """

    playlist: Playlist
    df: pd.DataFrame
    loaded_at: datetime


class DatasetNotLoadedError(LookupError):
    """Raised when an endpoint needs a playlist's dataset before any refresh job has loaded it.

    Mapped to HTTP 409 ``dataset_not_loaded`` by the web error handlers; the frontend reacts by starting a refresh job.
    """

    def __init__(self, playlist_id: str) -> None:
        super().__init__(f"Playlist {playlist_id!r} is not loaded; start a refresh job first.")
        self.playlist_id = playlist_id


class DatasetStore:
    """Lock-guarded map of ``playlist_id -> Dataset`` shared between job threads and request handlers."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._datasets: dict[str, Dataset] = {}

    def get(self, playlist_id: str) -> Dataset | None:
        """Return the dataset for ``playlist_id``, or None when not loaded."""
        with self._lock:
            return self._datasets.get(playlist_id)

    def require(self, playlist_id: str) -> Dataset:
        """Return the dataset for ``playlist_id``.

        Raises:
            DatasetNotLoadedError: When no refresh job has loaded the playlist yet.
        """
        dataset = self.get(playlist_id)
        if dataset is None:
            raise DatasetNotLoadedError(playlist_id)
        return dataset

    def put(self, playlist_id: str, dataset: Dataset) -> None:
        """Store (or replace) the dataset for ``playlist_id``."""
        with self._lock:
            self._datasets[playlist_id] = dataset

    def loaded_ids(self) -> frozenset[str]:
        """Return the ids of all currently loaded playlists."""
        with self._lock:
            return frozenset(self._datasets)
