from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, cast

logger = logging.getLogger(__name__)

# parents[2] = repo root (src/spotify_project/cache.py → ../../..)
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CACHE_DIR = _PROJECT_ROOT / ".cache" / "api"


class FileCache:
    """File-based cache for Spotify API responses.

    Stores each value as a single JSON file under ``root/<key>.json``.
    A cached entry is fresh if the file's mtime is within ``ttl_days``.
    Slashes in keys create subdirectories; keep keys filesystem-safe.

    The default ``root`` is ``<repo-root>/.cache/api`` (resolved relative to this file, not to CWD), so notebooks and scripts share the same cache regardless of working directory.
    Pass an explicit ``root`` (e.g. ``tmp_path`` in tests) to override. TTL is the default; individual ``get()`` calls can override it per-call with the ``ttl_days`` parameter.

    Attributes:
        root: Directory where cache files are stored.
        ttl_days: How long a cached value stays valid, in days.
    """

    def __init__(self, root: Path | None = None, ttl_days: float = 7.0) -> None:
        self.root = root if root is not None else DEFAULT_CACHE_DIR
        self.ttl_days = ttl_days
        self.root.mkdir(parents=True, exist_ok=True)

    def get(self, key: str, *, ttl_days: float | None = None) -> dict[str, Any] | None:
        """Return the cached JSON for ``key`` if present and within TTL.

        Args:
            key: Cache key (e.g. ``"playlist/<id>"``).
            ttl_days: Per-call TTL override. When ``None`` (default), uses the instance-level ``self.ttl_days``.
                Long-lived data can opt into a longer TTL without requiring a separate cache instance.

        Returns:
            The deserialized JSON object, or ``None`` if missing / stale / corrupt (non-JSON or a non-object top level).
        """
        effective_ttl = ttl_days if ttl_days is not None else self.ttl_days
        path = self._path_for(key)
        # stat() and read happen inside one try so a concurrent delete between the calls degrades to a miss instead of escaping as FileNotFoundError.
        try:
            if time.time() - path.stat().st_mtime > effective_ttl * 86_400:
                return None
            loaded: Any = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Corrupted cache entry %s: %s; treating as miss", key, e)
            return None
        if not isinstance(loaded, dict):
            logger.warning("Cache entry %s is valid JSON but not an object (%s); treating as miss", key, type(loaded).__name__)
            return None
        return cast(dict[str, Any], loaded)

    def put(self, key: str, value: dict[str, Any]) -> None:
        """Write ``value`` to disk under ``key``, atomically.

        Writes to a sibling temp file and ``os.replace``s it into place, so a killed process or a concurrent reader never sees a truncated entry
        (the multi-MB ``liked/me`` blob made mid-write kills a realistic case).

        Args:
            key: Cache key (filesystem-safe path fragment).
            value: JSON-serializable mapping to store.
        """
        path = self._path_for(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_name(path.name + ".tmp")
        tmp_path.write_text(json.dumps(value), encoding="utf-8")
        os.replace(tmp_path, path)

    def clear(self) -> None:
        """Remove every cached entry under ``root``.

        Individual unlink errors (e.g. Windows file locks while a reader holds the file open) are logged and skipped so a single stuck file doesn't abort the sweep.
        """
        for f in self.root.rglob("*.json"):
            try:
                f.unlink()
            except OSError as e:
                logger.warning("Failed to delete cache entry %s: %s; skipping", f, e)

    def _path_for(self, key: str) -> Path:
        """Resolve ``key`` to its on-disk path, rejecting traversal attempts.

        Args:
            key: Cache key fragment (e.g. ``"playlist/<id>"``).

        Returns:
            The full filesystem path under ``self.root``.

        Raises:
            ValueError: If ``key`` contains ``..`` segments or otherwise resolves outside the cache root.
        """
        if ".." in key.split("/"):
            raise ValueError(f"Unsafe cache key: {key!r}")
        path = self.root / f"{key}.json"
        if not path.resolve().is_relative_to(self.root.resolve()):
            raise ValueError(f"Cache key escapes root: {key!r}")
        return path
