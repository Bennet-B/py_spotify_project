from __future__ import annotations

import json
import logging
import time
import urllib.parse
from typing import Any, ClassVar, cast
from urllib.request import Request, urlopen

from .cache import FileCache

logger = logging.getLogger(__name__)


class LastFmClient:
    """Last.fm Web API client used to enrich Spotify artists with tags.

    Wraps the unauthenticated ``artist.getTopTags`` endpoint. Tags are
    lowercased here (once) so downstream code (Artist, genre_taxonomy filter,
    analyzers) can rely on lowercase invariants.

    Attributes:
        api_key: Last.fm API key.
        cache: FileCache used to persist per-artist tag lists.
    """

    BASE_URL: ClassVar[str] = "https://ws.audioscrobbler.com/2.0/"
    RATE_LIMIT_DELAY_SECONDS: ClassVar[float] = 0.2
    CACHE_TTL_DAYS: ClassVar[float] = 365.0
    DEFAULT_TOP_N: ClassVar[int] = 10
    REQUEST_TIMEOUT_SECONDS: ClassVar[float] = 10.0

    def __init__(self, api_key: str, cache: FileCache) -> None:
        """Construct a LastFmClient with explicit dependencies.

        Args:
            api_key: Non-empty Last.fm API key. The factory ``from_env``
                enforces non-empty-ness; direct callers are trusted to pass
                a real key.
            cache: FileCache used to persist per-artist tag lists under the
                ``lastfm_artist/<spotify_artist_id>`` key prefix.
        """
        self.api_key = api_key
        self.cache = cache

    def fetch_artist_tags(
        self,
        spotify_artist_id: str,
        artist_name: str,
        *,
        force_refresh: bool = False,
    ) -> tuple[str, ...]:
        """Return the top-N Last.fm tags for an artist.

        Tags are lowercased and returned in descending-weight order. Cached
        under ``lastfm_artist/<spotify_artist_id>.json`` with a 365-day TTL.
        Negative results (artist not found) are cached too. Rate-limit
        responses trigger a single retry; persistent rate-limit raises.

        Args:
            spotify_artist_id: Spotify artist ID, used as the cache key.
            artist_name: Display name, sent to Last.fm with ``autocorrect=1``.
            force_refresh: If True, skip the cache and refetch.

        Returns:
            Tuple of up to DEFAULT_TOP_N lowercased tags, descending-weight order.

        Raises:
            RuntimeError: On persistent rate-limit (code 29 twice) or any
                non-"not found" Last.fm error.
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
        # Rate limit persisted across both attempts.
        raise RuntimeError(f"Last.fm rate limit persisted after retry for artist {artist_name!r}")

    def _call_get_top_tags(self, artist_name: str) -> dict[str, Any]:
        """Make a single HTTP GET to the Last.fm artist.getTopTags endpoint.

        Args:
            artist_name: Display name, URL-encoded into the query string.

        Returns:
            The parsed JSON body. The caller must inspect the ``error`` key
            (Last.fm uses HTTP 200 + error code in body to report failures).
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
        """Pull and normalize the tag list from a Last.fm response body.

        Last.fm's XML-to-JSON layer sometimes returns a single tag as a
        bare dict instead of a 1-element list; we normalize both shapes.
        Tags are lowercased and trimmed.

        Args:
            data: Parsed JSON body from the Last.fm API.

        Returns:
            Tuple of up to DEFAULT_TOP_N lowercased tags.
        """
        toptags = cast(dict[str, Any], data.get("toptags", {}))
        raw: Any = toptags.get("tag", [])
        if isinstance(raw, dict):
            raw = [raw]
        items = cast(list[dict[str, Any]], raw)
        names = [str(item.get("name", "")).strip().lower() for item in items]
        names = [n for n in names if n]
        return tuple(names[: self.DEFAULT_TOP_N])
