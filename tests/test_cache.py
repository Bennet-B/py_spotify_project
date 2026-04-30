from __future__ import annotations

import os
import time
from pathlib import Path

from spotify_project.cache import FileCache


def test_put_then_get_within_ttl_returns_value(tmp_path: Path) -> None:
    """A put followed by a get within the TTL window returns the same value."""
    cache = FileCache(root=tmp_path, ttl_days=7.0)
    cache.put("playlist/abc", {"name": "Test", "id": "abc"})
    assert cache.get("playlist/abc") == {"name": "Test", "id": "abc"}


def test_get_after_ttl_returns_none(tmp_path: Path) -> None:
    """A get after the TTL has expired returns None."""
    cache = FileCache(root=tmp_path, ttl_days=1.0)
    cache.put("playlist/abc", {"name": "Test"})
    cache_file = tmp_path / "playlist" / "abc.json"
    two_days_ago = time.time() - 2 * 86_400
    os.utime(cache_file, (two_days_ago, two_days_ago))
    assert cache.get("playlist/abc") is None
