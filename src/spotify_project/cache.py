from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, cast

# src/spotify_project/cache.py → parents[0] = src/spotify_project, parents[1] = src, parents[2] = repo root
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CACHE_DIR = _PROJECT_ROOT / ".cache" / "api"


class FileCache:
    """File-based cache for Spotify API responses.

    Stores each value as a single JSON file under ``root/<key>.json``.
    A cached entry is fresh if the file's mtime is within ``ttl_days``.
    Slashes in keys create subdirectories; keep keys filesystem-safe.

    The default ``root`` is ``<repo-root>/.cache`` (resolved relative to this file,
    not to CWD), so notebooks and scripts share the same cache regardless of working directory.
    Pass an explicit ``root`` (e.g. ``tmp_path`` in tests) to override.
    TTL is the default; individual ``get()`` calls can override it per-call with the ``ttl_days`` parameter.

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
            The deserialized JSON, or ``None`` if missing / stale.
        """
        effective_ttl = ttl_days if ttl_days is not None else self.ttl_days
        path = self._path_for(key)
        if not path.exists():
            return None
        age_seconds = time.time() - path.stat().st_mtime
        if age_seconds > effective_ttl * 86_400:
            return None
        return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))

    def put(self, key: str, value: dict[str, Any]) -> None:
        """Write ``value`` to disk under ``key``.

        Args:
            key: Cache key (filesystem-safe path fragment).
            value: JSON-serializable mapping to store.
        """
        path = self._path_for(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")

    def clear(self) -> None:
        """Remove every cached entry under ``root``."""
        for f in self.root.rglob("*.json"):
            f.unlink()

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
