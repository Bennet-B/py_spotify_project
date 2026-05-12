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


def test_fetch_artist_tags_returns_empty_on_artist_not_found(cache: FileCache, caplog: pytest.LogCaptureFixture) -> None:
    client = LastFmClient(api_key="test-key", cache=cache)
    # Last.fm returns HTTP 200 even on errors; the error is in the body.
    error_payload = {"error": 6, "message": "The artist you supplied could not be found"}
    with patch("spotify_project.lastfm_client.urlopen", return_value=_mock_urlopen_response(error_payload)), caplog.at_level("WARNING", logger="spotify_project.lastfm_client"):
        tags = client.fetch_artist_tags("x", "ObscureArtist")
    assert tags == ()
    assert any("ObscureArtist" in rec.message for rec in caplog.records)


def test_fetch_artist_tags_caches_artist_not_found_result(cache: FileCache) -> None:
    # Negative results are cached too — no point refetching a known-missing artist.
    client = LastFmClient(api_key="test-key", cache=cache)
    error_payload = {"error": 6, "message": "not found"}
    with patch("spotify_project.lastfm_client.urlopen", return_value=_mock_urlopen_response(error_payload)) as mocked:
        client.fetch_artist_tags("x", "X")
        client.fetch_artist_tags("x", "X")
    assert mocked.call_count == 1


def test_fetch_artist_tags_retries_on_rate_limit_then_succeeds(cache: FileCache) -> None:
    client = LastFmClient(api_key="test-key", cache=cache)
    rate_limit_payload = {"error": 29, "message": "Rate limit exceeded"}
    success_payload = {"toptags": {"tag": [{"name": "rock", "count": 100}]}}
    side_effects = [
        _mock_urlopen_response(rate_limit_payload),
        _mock_urlopen_response(success_payload),
    ]
    with patch("spotify_project.lastfm_client.urlopen", side_effect=side_effects), patch("spotify_project.lastfm_client.time.sleep") as mock_sleep:
        # The first response triggers a single retry; the second succeeds.
        tags = client.fetch_artist_tags("x", "X")
    assert tags == ("rock",)
    assert mock_sleep.call_count == 1
    assert mock_sleep.call_args[0][0] == pytest.approx(LastFmClient.RATE_LIMIT_DELAY_SECONDS * 5)  # pyright: ignore[reportUnknownMemberType]


def test_fetch_artist_tags_raises_when_rate_limit_persists(cache: FileCache) -> None:
    client = LastFmClient(api_key="test-key", cache=cache)
    rate_limit_payload = {"error": 29, "message": "Rate limit exceeded"}
    side_effects = [
        _mock_urlopen_response(rate_limit_payload),
        _mock_urlopen_response(rate_limit_payload),
    ]
    with (
        patch("spotify_project.lastfm_client.urlopen", side_effect=side_effects),
        patch("spotify_project.lastfm_client.time.sleep") as mock_sleep,
        pytest.raises(RuntimeError, match="rate limit"),
    ):
        client.fetch_artist_tags("x", "X")
    assert mock_sleep.call_count == 1
    assert mock_sleep.call_args[0][0] == pytest.approx(LastFmClient.RATE_LIMIT_DELAY_SECONDS * 5)  # pyright: ignore[reportUnknownMemberType]


def test_fetch_artist_tags_raises_on_other_errors(cache: FileCache) -> None:
    client = LastFmClient(api_key="test-key", cache=cache)
    error_payload = {"error": 10, "message": "Invalid API key"}
    with patch("spotify_project.lastfm_client.urlopen", return_value=_mock_urlopen_response(error_payload)), pytest.raises(RuntimeError, match="Invalid API key"):
        client.fetch_artist_tags("x", "X")
