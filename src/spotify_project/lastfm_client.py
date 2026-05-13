from __future__ import annotations

import json
import logging
import os
import time
import urllib.parse
from typing import Any, ClassVar, cast
from urllib.request import Request, urlopen

from .cache import FileCache

logger = logging.getLogger(__name__)


class LastFmClient:
    """Last.fm Web API client used to enrich Spotify artists with tags.

    Wraps the unauthenticated ``artist.getTopTags`` endpoint. Tags are lowercased, stripped, synonym-canonicalized, and deduplicated (order-preserving) here so downstream code (Artist, genre_taxonomy filter, analyzers) can rely on the invariant "lowercase, unique, descending-weight order."

    The full normalized tag list is cached; no top-N truncation happens at storage time. Callers that want a top-N slice (e.g. TagAnalyzer) apply it after reading.

    Attributes:
        api_key: Last.fm API key.
        cache: FileCache used to persist per-artist tag lists.
    """

    BASE_URL: ClassVar[str] = "https://ws.audioscrobbler.com/2.0/"
    RATE_LIMIT_DELAY_SECONDS: ClassVar[float] = 0.2
    CACHE_TTL_DAYS: ClassVar[float] = 365.0
    REQUEST_TIMEOUT_SECONDS: ClassVar[float] = 10.0

    # Maps known Last.fm tag variants to a canonical form. Lowercase-keyed.
    # Add an entry here when two spellings show up as separate bars in the Top Tags / Top Genres chart for what is the same concept.
    TAG_SYNONYMS: ClassVar[dict[str, str]] = {
        "hip-hop": "hip hop",
        "hiphop": "hip hop",
        "rnb": "r&b",
        "r and b": "r&b",
        "dnb": "drum and bass",
        "drum n bass": "drum and bass",
        "drum & bass": "drum and bass",
    }

    def __init__(self, api_key: str, cache: FileCache) -> None:
        """Construct a LastFmClient with explicit dependencies.

        Args:
            api_key: Non-empty Last.fm API key. The factory ``from_env`` enforces non-empty-ness; direct callers are trusted to pass a real key.
            cache: FileCache used to persist per-artist tag lists under the ``lastfm_artist/<spotify_artist_id>`` key prefix.
        """
        self.api_key = api_key
        self.cache = cache

    @classmethod
    def from_env(cls, cache: FileCache) -> LastFmClient | None:
        """Build a LastFmClient from the LASTFM_API_KEY env var.

        Reads the key from ``os.environ``. Returns None and emits a single INFO log line when the key is unset or empty — Last.fm enrichment is optional; the notebook degrades gracefully and TagAnalyzer/GenreAnalyzer get skipped instead of producing empty panels.

        Args:
            cache: FileCache for response persistence.

        Returns:
            A configured LastFmClient, or None when LASTFM_API_KEY is unset or blank.
        """
        key = os.environ.get("LASTFM_API_KEY", "").strip()
        if not key:
            logger.info("Last.fm enrichment disabled — set LASTFM_API_KEY to enable. Tag and Genre panels will be skipped.")
            return None
        return cls(api_key=key, cache=cache)

    def fetch_artist_tags(self, spotify_artist_id: str, artist_name: str, *, force_refresh: bool = False) -> tuple[str, ...]:
        """Return the full list of Last.fm tags for an artist.

        Tags are lowercased, stripped, synonym-canonicalized, and deduplicated (order-preserving) so the result is unique and in descending-weight order. The complete list is returned and cached — no top-N truncation here. Downstream consumers (e.g. TagAnalyzer) can slice if they want.

        Cached under ``lastfm_artist/<spotify_artist_id>.json`` with a 365-day TTL. Negative results (artist not found) are cached too. Rate-limit responses trigger a single retry; persistent rate-limit raises.

        Args:
            spotify_artist_id: Spotify artist ID, used as the cache key.
            artist_name: Display name, sent to Last.fm with ``autocorrect=1``.
            force_refresh: If True, skip the cache and refetch.

        Returns:
            Tuple of lowercased, unique tags in descending-weight order. Empty tuple when Last.fm has no tags for the artist or the artist is unknown.

        Raises:
            RuntimeError: On persistent rate-limit (code 29 twice) or any non-"not found" Last.fm error.
        """
        cache_key = f"lastfm_artist/{spotify_artist_id}"
        cached = None if force_refresh else self.cache.get(cache_key, ttl_days=self.CACHE_TTL_DAYS)
        if cached is not None:
            return tuple(cast(list[str], cached["tags"]))

        for attempt in range(2):
            data = self._call_get_top_tags(artist_name)
            error_code = data.get("error")
            if error_code is None:
                tags = self._extract_tags(data)
                self.cache.put(cache_key, {"tags": list(tags)})
                return tags
            if error_code == 6:
                # Artist not found — log once, cache empty result, move on.
                logger.warning("Last.fm has no entry for artist %r (id=%s); recording empty tags", artist_name, spotify_artist_id)
                self.cache.put(cache_key, {"tags": []})
                return ()
            if error_code == 29:
                if attempt == 0:
                    logger.warning("Last.fm rate limit hit; sleeping %.1fs and retrying", self.RATE_LIMIT_DELAY_SECONDS * 5)
                    time.sleep(self.RATE_LIMIT_DELAY_SECONDS * 5)
                    continue
                break  # attempt 1 still rate-limited — fall to post-loop raise
            message = data.get("message", "<no message>")
            raise RuntimeError(f"Last.fm error {error_code} for artist {artist_name!r}: {message}")
        raise RuntimeError(f"Last.fm rate limit persisted after retry for artist {artist_name!r}")

    def _call_get_top_tags(self, artist_name: str) -> dict[str, Any]:
        """Make a single HTTP GET to the Last.fm artist.getTopTags endpoint.

        Args:
            artist_name: Display name, URL-encoded into the query string.

        Returns:
            The parsed JSON body. The caller must inspect the ``error`` key (Last.fm uses HTTP 200 + error code in body to report failures).
        """
        params = {
            "method": "artist.getTopTags",
            "artist": artist_name,
            "api_key": self.api_key,
            "autocorrect": "1",
            "format": "json",
        }
        url = f"{self.BASE_URL}?{urllib.parse.urlencode(params)}"
        request = Request(url, headers={"User-Agent": "py_spotify_project/0.1"})
        with urlopen(request, timeout=self.REQUEST_TIMEOUT_SECONDS) as response:
            body = response.read()
        return cast(dict[str, Any], json.loads(body))

    def _extract_tags(self, data: dict[str, Any]) -> tuple[str, ...]:
        """Pull, normalize, and deduplicate the full tag list from a Last.fm response body.

        Last.fm's XML-to-JSON layer sometimes returns a single tag as a bare dict instead of a 1-element list; both shapes are normalized. Each tag is lowercased, stripped, mapped via ``TAG_SYNONYMS`` if a known variant, and deduplicated with first-occurrence order preservation. The complete list is returned — no top-N slicing here.

        Args:
            data: Parsed JSON body from the Last.fm API.

        Returns:
            Tuple of unique, lowercased, canonicalized tags in descending-weight order.
        """
        toptags = cast(dict[str, Any], data.get("toptags", {}))
        raw: Any = toptags.get("tag", [])
        if isinstance(raw, dict):
            raw = [raw]
        items = cast(list[dict[str, Any]], raw)
        normalized = (self._normalize_tag(str(item.get("name", ""))) for item in items)
        non_empty = (n for n in normalized if n)
        # dict.fromkeys preserves first-occurrence order while deduplicating; cheaper than a manual seen-set loop.
        return tuple(dict.fromkeys(non_empty))

    @classmethod
    def _normalize_tag(cls, raw_name: str) -> str:
        """Lowercase, strip, and synonym-canonicalize a single tag.

        Args:
            raw_name: Tag text as returned by Last.fm.

        Returns:
            Canonical form: lowercased, stripped of surrounding whitespace, then mapped via ``TAG_SYNONYMS`` if a known variant. Returns ``""`` for an all-whitespace input so the caller can filter it out.
        """
        normalized = raw_name.strip().lower()
        return cls.TAG_SYNONYMS.get(normalized, normalized)
