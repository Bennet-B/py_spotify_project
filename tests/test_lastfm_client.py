from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from spotify_project.cache import FileCache
from spotify_project.lastfm_client import LastFmClient


@pytest.fixture
def cache(tmp_path: Path) -> FileCache:
    return FileCache(root=tmp_path / "api")


def _mock_urlopen_response(payload: dict[str, Any]) -> MagicMock:
    """Build a MagicMock that mimics urllib.request.urlopen's return.

    The returned object supports the context-manager protocol and a
    ``read()`` method returning the JSON-encoded payload as bytes.
    """
    mock_response = MagicMock()
    mock_response.__enter__.return_value = mock_response
    mock_response.__exit__.return_value = False
    mock_response.read.return_value = json.dumps(payload).encode("utf-8")
    return mock_response


def test_fetch_artist_tags_returns_lowercased_tags_in_order(cache: FileCache) -> None:
    client = LastFmClient(api_key="test-key", cache=cache)
    payload = {
        "toptags": {
            "tag": [
                {"name": "Electronic", "count": 100},
                {"name": "House", "count": 80},
                {"name": "French", "count": 60},
            ]
        }
    }
    with patch("spotify_project.lastfm_client.urlopen", return_value=_mock_urlopen_response(payload)):
        tags = client.fetch_artist_tags("daft-punk-id", "Daft Punk")
    assert tags == ("electronic", "house", "french")


def test_fetch_artist_tags_limits_to_default_top_n(cache: FileCache) -> None:
    client = LastFmClient(api_key="test-key", cache=cache)
    payload = {"toptags": {"tag": [{"name": f"tag{i}", "count": 100 - i} for i in range(20)]}}
    with patch("spotify_project.lastfm_client.urlopen", return_value=_mock_urlopen_response(payload)):
        tags = client.fetch_artist_tags("x", "X")
    assert len(tags) == LastFmClient.DEFAULT_TOP_N


def test_fetch_artist_tags_caches_results(cache: FileCache) -> None:
    client = LastFmClient(api_key="test-key", cache=cache)
    payload = {"toptags": {"tag": [{"name": "rock", "count": 100}]}}
    with patch("spotify_project.lastfm_client.urlopen", return_value=_mock_urlopen_response(payload)) as mocked:
        client.fetch_artist_tags("x", "X")
        client.fetch_artist_tags("x", "X")
    assert mocked.call_count == 1


def test_fetch_artist_tags_force_refresh_bypasses_cache(cache: FileCache) -> None:
    client = LastFmClient(api_key="test-key", cache=cache)
    payload = {"toptags": {"tag": [{"name": "rock", "count": 100}]}}
    with patch("spotify_project.lastfm_client.urlopen", return_value=_mock_urlopen_response(payload)) as mocked:
        client.fetch_artist_tags("x", "X")
        client.fetch_artist_tags("x", "X", force_refresh=True)
    assert mocked.call_count == 2


def test_fetch_artist_tags_force_refresh_updates_cache(cache: FileCache) -> None:
    client = LastFmClient(api_key="test-key", cache=cache)
    original_payload = {"toptags": {"tag": [{"name": "rock", "count": 100}]}}
    refreshed_payload = {"toptags": {"tag": [{"name": "pop", "count": 100}]}}

    with patch("spotify_project.lastfm_client.urlopen", return_value=_mock_urlopen_response(original_payload)):
        client.fetch_artist_tags("x", "X")
    with patch("spotify_project.lastfm_client.urlopen", return_value=_mock_urlopen_response(refreshed_payload)):
        client.fetch_artist_tags("x", "X", force_refresh=True)

    # No mock this time — must be served from cache, which should hold the refreshed value.
    tags = client.fetch_artist_tags("x", "X")
    assert tags == ("pop",)


def test_fetch_artist_tags_returns_empty_when_toptags_key_missing(cache: FileCache) -> None:
    client = LastFmClient(api_key="test-key", cache=cache)
    with patch("spotify_project.lastfm_client.urlopen", return_value=_mock_urlopen_response({})):
        tags = client.fetch_artist_tags("x", "X")
    assert tags == ()


def test_fetch_artist_tags_handles_single_tag_dict(cache: FileCache) -> None:
    # Last.fm's XML-to-JSON conversion sometimes returns a single dict
    # instead of a 1-element list. We normalize.
    client = LastFmClient(api_key="test-key", cache=cache)
    payload = {"toptags": {"tag": {"name": "Rock", "count": 100}}}
    with patch("spotify_project.lastfm_client.urlopen", return_value=_mock_urlopen_response(payload)):
        tags = client.fetch_artist_tags("x", "X")
    assert tags == ("rock",)


def test_fetch_artist_tags_returns_empty_when_no_tags(cache: FileCache) -> None:
    client = LastFmClient(api_key="test-key", cache=cache)
    payload: dict[str, Any] = {"toptags": {"tag": []}}
    with patch("spotify_project.lastfm_client.urlopen", return_value=_mock_urlopen_response(payload)):
        tags = client.fetch_artist_tags("x", "X")
    assert tags == ()
