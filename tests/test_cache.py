from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

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


def test_unsafe_key_with_traversal_raises(tmp_path: Path) -> None:
    """A key containing `..` segments is rejected as a traversal attempt."""
    cache = FileCache(root=tmp_path)
    with pytest.raises(ValueError, match="Unsafe cache key"):
        cache.put("../escape", {"x": 1})


def test_get_missing_key_returns_none(tmp_path: Path) -> None:
    """A get for a key that was never put returns None (no exception, no warning)."""
    cache = FileCache(root=tmp_path)
    assert cache.get("playlist/never-written") is None


def test_corrupt_entry_treated_as_miss(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """Undecodable bytes on disk degrade to a miss with a warning instead of raising."""
    cache = FileCache(root=tmp_path)
    cache.put("playlist/abc", {"name": "Test"})
    (tmp_path / "playlist" / "abc.json").write_text("{ not valid json", encoding="utf-8")
    with caplog.at_level("WARNING", logger="spotify_project.cache"):
        assert cache.get("playlist/abc") is None
    assert any("Corrupted cache entry" in rec.message for rec in caplog.records)


def test_non_object_json_treated_as_miss(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """Valid JSON that is not an object (e.g. a bare array) is a miss, not a bogus dict handed to callers."""
    cache = FileCache(root=tmp_path)
    cache.put("playlist/abc", {"name": "Test"})
    (tmp_path / "playlist" / "abc.json").write_text("[1, 2, 3]", encoding="utf-8")
    with caplog.at_level("WARNING", logger="spotify_project.cache"):
        assert cache.get("playlist/abc") is None
    assert any("not an object" in rec.message for rec in caplog.records)


def test_clear_removes_all_entries(tmp_path: Path) -> None:
    """clear() wipes every entry, including nested keys; subsequent gets miss."""
    cache = FileCache(root=tmp_path)
    cache.put("playlist/abc", {"name": "A"})
    cache.put("artist/a1", {"name": "B"})
    cache.clear()
    assert cache.get("playlist/abc") is None
    assert cache.get("artist/a1") is None
    assert list(tmp_path.rglob("*.json")) == []


def test_put_leaves_no_temp_file_behind(tmp_path: Path) -> None:
    """The atomic-write temp file is renamed away by a successful put."""
    cache = FileCache(root=tmp_path)
    cache.put("playlist/abc", {"name": "Test"})
    assert list(tmp_path.rglob("*.tmp")) == []


def test_get_with_ttl_override_overrides_instance_default(tmp_path: Path) -> None:
    """FileCache.get accepts a per-call ttl_days override.

    A value past the instance's default TTL but within the override returns; without the override (instance default) it returns None.
    """
    cache = FileCache(root=tmp_path, ttl_days=1.0)
    cache.put("artist/a1", {"name": "Alice"})
    cache_file = tmp_path / "artist" / "a1.json"
    five_days_ago = time.time() - 5 * 86_400
    os.utime(cache_file, (five_days_ago, five_days_ago))

    assert cache.get("artist/a1") is None
    assert cache.get("artist/a1", ttl_days=10.0) == {"name": "Alice"}
