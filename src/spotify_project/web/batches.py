"""Local persistence of Apply batches.

Spotify has no folder API, so "grouping" created playlists means: a shared name prefix, a description marker, and this local history — the
in-app "created batches" view reads from here. Stored as one JSON file under the gitignored ``.cache`` tree.
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, cast

from ..cache import DEFAULT_CACHE_DIR

logger = logging.getLogger(__name__)

DEFAULT_BATCHES_PATH = DEFAULT_CACHE_DIR.parent / "web" / "batches.json"


@dataclass(frozen=True, slots=True)
class CreatedPlaylist:
    """One playlist created by an Apply."""

    bucket_name: str
    playlist_id: str
    url: str
    added: int


@dataclass(frozen=True, slots=True)
class Batch:
    """One Apply run: the batch name, when and from which source it ran, and what it created."""

    batch_name: str
    created_at: str
    source_playlist_id: str
    created: tuple[CreatedPlaylist, ...]


class BatchStore:
    """Lock-guarded JSON-file store of Apply batches, newest first.

    A corrupt or missing file degrades to an empty history (the batches are a convenience view; Spotify holds the actual playlists).
    """

    def __init__(self, path: Path | None = None) -> None:
        self.path = path if path is not None else DEFAULT_BATCHES_PATH
        self._lock = threading.Lock()

    def all_batches(self) -> tuple[Batch, ...]:
        """Return every recorded batch, newest first."""
        with self._lock:
            return self._read()

    def append(self, batch: Batch) -> None:
        """Persist a new batch at the front of the history."""
        with self._lock:
            batches = (batch, *self._read())
            self.path.parent.mkdir(parents=True, exist_ok=True)
            payload = [asdict(entry) for entry in batches]
            self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _read(self) -> tuple[Batch, ...]:
        """Load the history; malformed content is logged and treated as empty. Caller holds the lock."""
        try:
            raw: Any = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return ()
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Batch history at %s unreadable (%s); treating as empty", self.path, exc)
            return ()
        if not isinstance(raw, list):
            logger.warning("Batch history at %s is not a list; treating as empty", self.path)
            return ()
        batches: list[Batch] = []
        for entry in cast("list[Any]", raw):
            try:
                created = tuple(CreatedPlaylist(**item) for item in entry.pop("created"))
                batches.append(Batch(created=created, **entry))
            except (KeyError, TypeError, AttributeError) as exc:
                logger.warning("Skipping malformed batch entry in %s: %s", self.path, exc)
        return tuple(batches)
