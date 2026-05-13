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

    The returned object supports the context-manager protocol and a ``read()`` method returning the JSON-encoded payload as bytes.
    """
    mock_response = MagicMock()
    mock_response.__enter__.return_value = mock_response
    mock_response.__exit__.return_value = False
    mock_response.read.return_value = json.dumps(payload).encode("utf-8")
    return mock_response


class TestNormalization:
    """Tests for the read-time normalization pipeline applied by fetch_artist_tags."""

    def test_returns_lowercased_tags_in_order(self, cache: FileCache) -> None:
        """fetch_artist_tags lowercases tag names and preserves Last.fm's descending-weight order."""
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

    def test_returns_full_list_no_top_n_truncation(self, cache: FileCache) -> None:
        """fetch_artist_tags returns every tag Last.fm sends — no fixed cap at storage time.

        The client used to slice to DEFAULT_TOP_N=10 at storage time; that was wrong (lost data we already paid to fetch).
        Slicing, if any, is now a downstream concern (e.g. TagAnalyzer's own top_n).
        """
        client = LastFmClient(api_key="test-key", cache=cache)
        payload = {"toptags": {"tag": [{"name": f"tag{i}", "count": 100 - i} for i in range(20)]}}
        with patch("spotify_project.lastfm_client.urlopen", return_value=_mock_urlopen_response(payload)):
            tags = client.fetch_artist_tags("x", "X")
        assert len(tags) == 20
        assert tags[0] == "tag0"
        assert tags[-1] == "tag19"

    @pytest.mark.parametrize(
        ("raw_names", "expected"),
        [
            # Synonyms via the punctuation/separator path: "Hip-Hop" → "hip hop" (already canonical, no synonym lookup);
            # "RNB" → lowercase → "rnb" (already canonical); "DnB" → "dnb" → synonym → "drum and bass".
            (
                ["Hip-Hop", "RNB", "DnB"],
                ("hip hop", "rnb", "drum and bass"),
            ),
            # Every non-word non-space character (and underscore) collapses to space; multi-space collapses to single space;
            # then the synonym map maps the post-strip form to a readable canonical.
            # "R&B" → "r b" → synonym "rnb". "Drum & Bass" → "drum  bass" → "drum bass" → synonym "drum and bass".
            # "rock'n'roll" → "rock n roll" (no synonym entry). "indie/rock" → "indie rock". "psy.trance" → "psy trance".
            (
                ["R&B", "Drum & Bass", "rock'n'roll", "indie/rock", "psy.trance"],
                ("rnb", "drum and bass", "rock n roll", "indie rock", "psy trance"),
            ),
            # Python 3's `\w` matches Unicode word chars by default, so accented letters survive the regex sub.
            (["Björk-Style"], ("björk style",)),
            # Dedupe-after-normalize: "Hip-Hop" and "hip hop" both canonicalize to "hip hop", collapsing via dict.fromkeys at the earlier (higher-weight) position.
            (
                ["rock", "Hip-Hop", "hip hop", "Pop"],
                ("rock", "hip hop", "pop"),
            ),
            # Generalized separator rule handles underscores, hyphens-with-spaces, and multi-space without needing any TAG_SYNONYMS entries.
            (
                ["Lo_Fi", "post - rock", "K-POP", "drum  and  bass"],
                ("lo fi", "post rock", "k pop", "drum and bass"),
            ),
            # Single-word synonym: "hiphop" (no separators) → TAG_SYNONYMS lookup → "hip hop". Exercises the synonym path independently of the punctuation/separator path.
            (["hiphop"], ("hip hop",)),
            # Spelled-out synonym: "r and b" canonicalizes to "rnb" via its TAG_SYNONYMS entry — distinct from the "&"-stripping path that the "R&B" case in `punctuation_strip` covers.
            (["r and b"], ("rnb",)),
            # A tag that normalizes to an empty string is dropped: "&!?" has no surviving word chars after the regex sub, so `_normalize_and_dedupe`'s empty filter discards it.
            (
                ["rock", "&!?", "indie"],
                ("rock", "indie"),
            ),
        ],
        ids=[
            "synonyms",
            "punctuation_strip",
            "unicode_word_chars",
            "dedupe_after_normalize",
            "separator_rule",
            "single_word_synonym_hiphop",
            "spelled_out_synonym_r_and_b",
            "all_punctuation_drops_to_empty",
        ],
    )
    def test_normalization_rules(self, cache: FileCache, raw_names: list[str], expected: tuple[str, ...]) -> None:
        """fetch_artist_tags applies the read-time pipeline: lowercase, separator/punctuation collapse, synonym lookup, order-preserving dedupe."""
        client = LastFmClient(api_key="test-key", cache=cache)
        payload = {"toptags": {"tag": [{"name": n, "count": 100 - i} for i, n in enumerate(raw_names)]}}
        with patch("spotify_project.lastfm_client.urlopen", return_value=_mock_urlopen_response(payload)):
            tags = client.fetch_artist_tags("x", "X")
        assert tags == expected


class TestCaching:
    """Tests for fetch_artist_tags's cache behavior — raw-tag storage, hit/miss, force-refresh."""

    def test_cache_stores_raw_tags_so_normalization_changes_survive(self, cache: FileCache, monkeypatch: pytest.MonkeyPatch) -> None:
        """Cache holds tag names exactly as Last.fm sent them.

        Mutating TAG_SYNONYMS after the cache is warm produces a different result on the next read without a re-fetch.
        """
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

    def test_caches_results(self, cache: FileCache) -> None:
        """A second call for the same artist is served from cache (no second HTTP call)."""
        client = LastFmClient(api_key="test-key", cache=cache)
        payload = {"toptags": {"tag": [{"name": "rock", "count": 100}]}}
        with patch("spotify_project.lastfm_client.urlopen", return_value=_mock_urlopen_response(payload)) as mocked:
            client.fetch_artist_tags("x", "X")
            client.fetch_artist_tags("x", "X")
        assert mocked.call_count == 1

    def test_force_refresh_bypasses_cache(self, cache: FileCache) -> None:
        """force_refresh=True skips the cache and re-fetches even when an entry exists."""
        client = LastFmClient(api_key="test-key", cache=cache)
        payload = {"toptags": {"tag": [{"name": "rock", "count": 100}]}}
        with patch("spotify_project.lastfm_client.urlopen", return_value=_mock_urlopen_response(payload)) as mocked:
            client.fetch_artist_tags("x", "X")
            client.fetch_artist_tags("x", "X", force_refresh=True)
        assert mocked.call_count == 2

    def test_force_refresh_updates_cache(self, cache: FileCache) -> None:
        """force_refresh=True overwrites the cached entry so subsequent reads see the new value."""
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


class TestMalformedResponses:
    """Tests for fetch_artist_tags's resilience against wire-format quirks of the Last.fm API."""

    def test_returns_empty_when_toptags_key_missing(self, cache: FileCache) -> None:
        """fetch_artist_tags returns an empty tuple when the response has no `toptags` key."""
        client = LastFmClient(api_key="test-key", cache=cache)
        with patch("spotify_project.lastfm_client.urlopen", return_value=_mock_urlopen_response({})):
            tags = client.fetch_artist_tags("x", "X")
        assert tags == ()

    def test_handles_single_tag_dict(self, cache: FileCache) -> None:
        """Last.fm's XML-to-JSON conversion sometimes returns a single dict instead of a 1-element list — both shapes parse correctly."""
        client = LastFmClient(api_key="test-key", cache=cache)
        payload = {"toptags": {"tag": {"name": "Rock", "count": 100}}}
        with patch("spotify_project.lastfm_client.urlopen", return_value=_mock_urlopen_response(payload)):
            tags = client.fetch_artist_tags("x", "X")
        assert tags == ("rock",)

    def test_returns_empty_when_no_tags(self, cache: FileCache) -> None:
        """fetch_artist_tags returns an empty tuple when `toptags.tag` is an empty list."""
        client = LastFmClient(api_key="test-key", cache=cache)
        payload: dict[str, Any] = {"toptags": {"tag": []}}
        with patch("spotify_project.lastfm_client.urlopen", return_value=_mock_urlopen_response(payload)):
            tags = client.fetch_artist_tags("x", "X")
        assert tags == ()


class TestErrorHandling:
    """Tests for fetch_artist_tags's Last.fm error-code branches (not-found, generic errors)."""

    def test_returns_empty_on_artist_not_found(self, cache: FileCache, caplog: pytest.LogCaptureFixture) -> None:
        """Last.fm error 6 (artist not found) returns an empty tuple and logs a warning naming the artist."""
        client = LastFmClient(api_key="test-key", cache=cache)
        # Last.fm returns HTTP 200 even on errors; the error is in the body.
        error_payload = {"error": 6, "message": "The artist you supplied could not be found"}
        with patch("spotify_project.lastfm_client.urlopen", return_value=_mock_urlopen_response(error_payload)), caplog.at_level("WARNING", logger="spotify_project.lastfm_client"):
            tags = client.fetch_artist_tags("x", "ObscureArtist")
        assert tags == ()
        assert any("ObscureArtist" in rec.message for rec in caplog.records)

    def test_caches_artist_not_found_result(self, cache: FileCache) -> None:
        """Negative results (artist not found) are cached too — no point refetching a known-missing artist."""
        client = LastFmClient(api_key="test-key", cache=cache)
        error_payload = {"error": 6, "message": "not found"}
        with patch("spotify_project.lastfm_client.urlopen", return_value=_mock_urlopen_response(error_payload)) as mocked:
            client.fetch_artist_tags("x", "X")
            client.fetch_artist_tags("x", "X")
        assert mocked.call_count == 1

    def test_raises_on_other_errors(self, cache: FileCache) -> None:
        """Last.fm errors other than not-found / rate-limit propagate as RuntimeError with the API message."""
        client = LastFmClient(api_key="test-key", cache=cache)
        error_payload = {"error": 10, "message": "Invalid API key"}
        with patch("spotify_project.lastfm_client.urlopen", return_value=_mock_urlopen_response(error_payload)), pytest.raises(RuntimeError, match="Invalid API key"):
            client.fetch_artist_tags("x", "X")


class TestRateLimitHandling:
    """Tests for fetch_artist_tags's 429 backoff: single retry then bail out."""

    def test_retries_on_rate_limit_then_succeeds(self, cache: FileCache) -> None:
        """A single rate-limit response triggers one retry; the second attempt succeeds."""
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

    def test_raises_when_rate_limit_persists(self, cache: FileCache) -> None:
        """Two consecutive rate-limit responses bail out with RuntimeError after a single retry."""
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


class TestFromEnv:
    """Tests for LastFmClient.from_env — gated construction on LASTFM_API_KEY env var."""

    def test_returns_client_when_key_set(self, cache: FileCache, monkeypatch: pytest.MonkeyPatch) -> None:
        """from_env returns a configured LastFmClient when LASTFM_API_KEY is set to a non-empty value."""
        monkeypatch.setenv("LASTFM_API_KEY", "real-key-xyz")
        client = LastFmClient.from_env(cache=cache)
        assert client is not None
        assert client.api_key == "real-key-xyz"
        assert client.cache is cache

    def test_returns_none_when_key_missing(self, cache: FileCache, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
        """from_env returns None and logs an INFO line mentioning LASTFM_API_KEY when the env var is unset."""
        monkeypatch.delenv("LASTFM_API_KEY", raising=False)
        with caplog.at_level("INFO", logger="spotify_project.lastfm_client"):
            client = LastFmClient.from_env(cache=cache)
        assert client is None
        assert any("LASTFM_API_KEY" in rec.message for rec in caplog.records)

    def test_returns_none_when_key_blank(self, cache: FileCache, monkeypatch: pytest.MonkeyPatch) -> None:
        """from_env returns None when LASTFM_API_KEY is set to an empty string (blank counts as unset)."""
        monkeypatch.setenv("LASTFM_API_KEY", "")
        client = LastFmClient.from_env(cache=cache)
        assert client is None
