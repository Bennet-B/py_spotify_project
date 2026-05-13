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


def test_fetch_artist_tags_returns_full_list_no_top_n_truncation(cache: FileCache) -> None:
    # The client used to slice to DEFAULT_TOP_N=10 at storage time; that was wrong (lost data we already paid to fetch).
    # Slicing, if any, is now a downstream concern (e.g. TagAnalyzer's own top_n).
    client = LastFmClient(api_key="test-key", cache=cache)
    payload = {"toptags": {"tag": [{"name": f"tag{i}", "count": 100 - i} for i in range(20)]}}
    with patch("spotify_project.lastfm_client.urlopen", return_value=_mock_urlopen_response(payload)):
        tags = client.fetch_artist_tags("x", "X")
    assert len(tags) == 20
    assert tags[0] == "tag0"
    assert tags[-1] == "tag19"


def test_fetch_artist_tags_applies_synonym_normalization(cache: FileCache) -> None:
    client = LastFmClient(api_key="test-key", cache=cache)
    payload = {
        "toptags": {
            "tag": [
                {"name": "Hip-Hop", "count": 100},
                {"name": "RNB", "count": 80},
                {"name": "DnB", "count": 60},
            ]
        }
    }
    with patch("spotify_project.lastfm_client.urlopen", return_value=_mock_urlopen_response(payload)):
        tags = client.fetch_artist_tags("x", "X")
    # "Hip-Hop" -> hyphen replaced by space -> "hip hop". "RNB" stays "rnb". "DnB" lowercase "dnb" -> synonym -> "drum and bass".
    assert tags == ("hip hop", "rnb", "drum and bass")


def test_fetch_artist_tags_strips_ampersand_and_other_punctuation(cache: FileCache) -> None:
    # Every non-word non-space character collapses to space (then multi-space → single space). Synonym map maps the post-strip form to the readable canonical.
    client = LastFmClient(api_key="test-key", cache=cache)
    payload = {
        "toptags": {
            "tag": [
                {"name": "R&B", "count": 100},
                {"name": "Drum & Bass", "count": 80},
                {"name": "rock'n'roll", "count": 60},
                {"name": "indie/rock", "count": 40},
                {"name": "psy.trance", "count": 20},
            ]
        }
    }
    with patch("spotify_project.lastfm_client.urlopen", return_value=_mock_urlopen_response(payload)):
        tags = client.fetch_artist_tags("x", "X")
    # "R&B" → "r b" → synonym "rnb". "Drum & Bass" → "drum  bass" → "drum bass" → synonym "drum and bass". "rock'n'roll" → "rock n roll" (no synonym). "indie/rock" → "indie rock". "psy.trance" → "psy trance".
    assert tags == ("rnb", "drum and bass", "rock n roll", "indie rock", "psy trance")


def test_fetch_artist_tags_preserves_accented_word_chars(cache: FileCache) -> None:
    # `\w` matches Unicode word chars by default in Python 3, so accented letters survive normalization.
    client = LastFmClient(api_key="test-key", cache=cache)
    payload = {"toptags": {"tag": [{"name": "Björk-Style", "count": 100}]}}
    with patch("spotify_project.lastfm_client.urlopen", return_value=_mock_urlopen_response(payload)):
        tags = client.fetch_artist_tags("x", "X")
    assert tags == ("björk style",)


def test_fetch_artist_tags_dedupes_normalized_variants_preserving_order(cache: FileCache) -> None:
    # If Last.fm returns both "hip-hop" and "hip hop" for one artist, they collapse to a single entry at the earlier (higher-weight) position.
    client = LastFmClient(api_key="test-key", cache=cache)
    payload = {
        "toptags": {
            "tag": [
                {"name": "rock", "count": 100},
                {"name": "Hip-Hop", "count": 80},
                {"name": "hip hop", "count": 60},
                {"name": "Pop", "count": 40},
            ]
        }
    }
    with patch("spotify_project.lastfm_client.urlopen", return_value=_mock_urlopen_response(payload)):
        tags = client.fetch_artist_tags("x", "X")
    assert tags == ("rock", "hip hop", "pop")


def test_fetch_artist_tags_normalizes_separators_without_synonym_entry(cache: FileCache) -> None:
    # Underscores, hyphens, and multi-space all collapse to single-space via the generalized separator rule. No TAG_SYNONYMS entry needed for these spellings.
    client = LastFmClient(api_key="test-key", cache=cache)
    payload = {
        "toptags": {
            "tag": [
                {"name": "Lo_Fi", "count": 100},
                {"name": "post - rock", "count": 80},
                {"name": "K-POP", "count": 60},
                {"name": "drum  and  bass", "count": 40},
            ]
        }
    }
    with patch("spotify_project.lastfm_client.urlopen", return_value=_mock_urlopen_response(payload)):
        tags = client.fetch_artist_tags("x", "X")
    assert tags == ("lo fi", "post rock", "k pop", "drum and bass")


def test_cache_stores_raw_tags_so_normalization_changes_survive(cache: FileCache, monkeypatch: pytest.MonkeyPatch) -> None:
    # Cache holds tag names exactly as Last.fm sent them. Mutating TAG_SYNONYMS after the cache is warm produces a different result on the next read without a re-fetch.
    client = LastFmClient(api_key="test-key", cache=cache)
    payload = {"toptags": {"tag": [{"name": "Funky-Town", "count": 100}]}}
    with patch("spotify_project.lastfm_client.urlopen", return_value=_mock_urlopen_response(payload)) as mocked:
        first = client.fetch_artist_tags("x", "X")
    assert first == ("funky town",)
    assert mocked.call_count == 1

    # Inspect the on-disk cache directly: it should hold the original "Funky-Town" string, not the normalized "funky town".
    cached_entry = cache.get("lastfm_artist/x")
    assert cached_entry is not None
    assert cached_entry["tags"] == ["Funky-Town"]

    # Now extend TAG_SYNONYMS to map "funky town" to "funk". The cache is unchanged; the read-time pipeline re-normalizes.
    monkeypatch.setitem(LastFmClient.TAG_SYNONYMS, "funky town", "funk")
    with patch("spotify_project.lastfm_client.urlopen", return_value=_mock_urlopen_response(payload)) as mocked_after:
        second = client.fetch_artist_tags("x", "X")
    assert second == ("funk",)
    assert mocked_after.call_count == 0  # served from cache, no re-fetch


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
        pytest.raises(RuntimeError, match="rate.?limit persisted"),
    ):
        client.fetch_artist_tags("x", "X")
    assert mock_sleep.call_count == 1
    assert mock_sleep.call_args[0][0] == pytest.approx(LastFmClient.RATE_LIMIT_DELAY_SECONDS * 5)  # pyright: ignore[reportUnknownMemberType]


def test_fetch_artist_tags_raises_on_other_errors(cache: FileCache) -> None:
    client = LastFmClient(api_key="test-key", cache=cache)
    error_payload = {"error": 10, "message": "Invalid API key"}
    with patch("spotify_project.lastfm_client.urlopen", return_value=_mock_urlopen_response(error_payload)), pytest.raises(RuntimeError, match="Invalid API key"):
        client.fetch_artist_tags("x", "X")


def test_from_env_returns_client_when_key_set(cache: FileCache, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LASTFM_API_KEY", "real-key-xyz")
    client = LastFmClient.from_env(cache=cache)
    assert client is not None
    assert client.api_key == "real-key-xyz"
    assert client.cache is cache


def test_from_env_returns_none_when_key_missing(cache: FileCache, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    monkeypatch.delenv("LASTFM_API_KEY", raising=False)
    with caplog.at_level("INFO", logger="spotify_project.lastfm_client"):
        client = LastFmClient.from_env(cache=cache)
    assert client is None
    assert any("LASTFM_API_KEY" in rec.message for rec in caplog.records)


def test_from_env_returns_none_when_key_blank(cache: FileCache, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LASTFM_API_KEY", "")
    client = LastFmClient.from_env(cache=cache)
    assert client is None
