from __future__ import annotations

import json
import logging
import os
import re
import time
import urllib.parse
from typing import Any, ClassVar, cast
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .cache import FileCache

logger = logging.getLogger(__name__)

# Matches any char that's not a Unicode word char and not a space, OR an underscore.
# Word-class `\w` already covers letters and digits in any script (so accented tags like `björk` survive);
# underscore is a word char per Python regex but we treat it as a separator.
_DISALLOWED_TAG_CHAR_RE: re.Pattern[str] = re.compile(r"[^\w ]|_")


class LastFmClient:
    """Last.fm Web API client used to enrich Spotify artists with tags.

    Wraps the unauthenticated ``artist.getTopTags`` endpoint. The cache holds tags as they came off the wire (just JSON-shape and whitespace cleaned);
    lowercasing, separator collapse, synonym canonicalization, and deduplication happen on every read.
    That keeps the cache forward-compatible: tweaking TAG_SYNONYMS or the separator rule never invalidates existing cache entries.

    Attributes:
        api_key: Last.fm API key.
        cache: FileCache used to persist per-artist tag lists.
    """

    BASE_URL: ClassVar[str] = "https://ws.audioscrobbler.com/2.0/"
    # Sleep before the single retry after a rate-limit response. There is no inter-request throttle in this class — per-artist caching makes an aborted run resumable, which caps the damage.
    RATE_LIMIT_RETRY_BACKOFF_SECONDS: ClassVar[float] = 1.0
    CACHE_TTL_DAYS: ClassVar[float] = 365.0
    REQUEST_TIMEOUT_SECONDS: ClassVar[float] = 10.0

    # Word-level synonyms applied AFTER generalized normalization (lowercase, strip, every char that's not a word char or space becomes a space, multi-space collapse).
    # Keys must already be in canonical form (lowercase, only word chars and single spaces).
    # Add entries here only for genuine word-substitution cases, not for separator/casing/punctuation variants — those are handled mechanically by ``_normalize_tag``.
    TAG_SYNONYMS: ClassVar[dict[str, str]] = {
        "hiphop": "hip hop",
        # R&B: every spelling collapses to "r b" after &-stripping, plus "r and b" from the spelled-out form. Canonical chart label "rnb" is the most readable.
        "r b": "rnb",
        "r and b": "rnb",
        # Drum and Bass: "drum & bass" → "drum bass" after &-stripping; "drum n bass" and "dnb" are abbreviation forms. Canonical "drum and bass" is the most readable.
        "drum bass": "drum and bass",
        "drum n bass": "drum and bass",
        "dnb": "drum and bass",
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

        Reads the key from ``os.environ``. Returns None and emits a single INFO log line when the key is unset or empty — Last.fm enrichment is optional;
        the notebook degrades gracefully and TagAnalyzer/GenreAnalyzer get skipped instead of producing empty panels.

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
        """Return the artist's tags in canonical form.

        On a fresh fetch, the raw tag strings from Last.fm are stored as-is (JSON-shape cleaned, whitespace stripped, but otherwise unmodified).
        Whether the result comes from a fresh fetch or the cache, it then goes through the read-time pipeline:
        lowercase → separator/whitespace collapse → ``TAG_SYNONYMS`` → order-preserving dedupe.

        Cached under ``lastfm_artist/<spotify_artist_id>.json`` with a 365-day TTL. Negative results (artist not found) are cached as an empty tag list.
        Rate-limit responses trigger a single retry; persistent rate-limit raises.

        Args:
            spotify_artist_id: Spotify artist ID, used as the cache key.
            artist_name: Display name, sent to Last.fm with ``autocorrect=1``.
            force_refresh: If True, skip the cache and refetch.

        Returns:
            Tuple of canonical, unique tags in descending-weight order. Empty tuple when Last.fm has no tags for the artist or the artist is unknown.

        Raises:
            RuntimeError: On persistent rate-limit (code 29 twice), any non-"not found" Last.fm error, a network/transport failure, or a non-JSON response body.
        """
        cache_key = f"lastfm_artist/{spotify_artist_id}"
        cached = None if force_refresh else self.cache.get(cache_key, ttl_days=self.CACHE_TTL_DAYS)
        if cached is not None:
            cached_tags = cached.get("tags")
            if isinstance(cached_tags, list):
                return self._normalize_and_dedupe(cast(list[str], cached_tags))
            # Self-healing like FileCache's corrupt-entry recovery: an entry without a usable tags list falls through to a refetch that overwrites it.
            logger.warning("Cache entry for artist %s (id=%s) has no usable 'tags' list; refetching", artist_name, spotify_artist_id)

        for attempt in range(2):
            data = self._call_get_top_tags(artist_name)
            error_code = data.get("error")
            if error_code is None:
                raw_tags = self._extract_raw_tags(data)
                self.cache.put(cache_key, {"tags": raw_tags})
                return self._normalize_and_dedupe(raw_tags)
            if error_code == 6:
                # Artist not found — log once, cache empty result, move on.
                logger.warning("Last.fm has no entry for artist %r (id=%s); recording empty tags", artist_name, spotify_artist_id)
                self.cache.put(cache_key, {"tags": []})
                return ()
            if error_code == 29:
                if attempt == 0:
                    logger.warning("Last.fm rate limit hit; sleeping %.1fs and retrying", self.RATE_LIMIT_RETRY_BACKOFF_SECONDS)
                    time.sleep(self.RATE_LIMIT_RETRY_BACKOFF_SECONDS)
                    continue
                break  # attempt 1 still rate-limited — fall to post-loop raise
            message = data.get("message", "<no message>")
            raise RuntimeError(f"Last.fm error {error_code} for artist {artist_name!r}: {message}")
        raise RuntimeError(
            f"Last.fm rate-limit persisted after a {self.RATE_LIMIT_RETRY_BACKOFF_SECONDS:.1f}s retry for artist {artist_name!r}; aborting. Re-run the notebook after a short cooldown."
        )

    def _call_get_top_tags(self, artist_name: str) -> dict[str, Any]:
        """Make a single HTTP GET to the Last.fm artist.getTopTags endpoint.

        Last.fm usually reports failures as HTTP 200 with an ``error`` code in the body, but some error codes arrive with a non-2xx status —
        those ``HTTPError`` bodies are parsed through the same JSON path so the caller's error-code branches (not-found, rate-limit) still apply.

        Args:
            artist_name: Display name, URL-encoded into the query string.

        Returns:
            The parsed JSON body. The caller must inspect the ``error`` key.

        Raises:
            RuntimeError: On transport-level failures (DNS, connection reset, timeout) or a non-JSON response body.
                The message points out that a re-run resumes from the per-artist cache, so a multi-hundred-artist enrichment doesn't restart from zero.
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
        try:
            with urlopen(request, timeout=self.REQUEST_TIMEOUT_SECONDS) as response:
                body = response.read()
        except HTTPError as e:  # HTTPError before URLError — it's a subclass
            body = e.read()
        except (URLError, TimeoutError) as e:
            raise RuntimeError(f"Network error calling Last.fm for artist {artist_name!r}: {e}. Re-run to resume — already-fetched artists are served from cache.") from e
        try:
            return cast(dict[str, Any], json.loads(body))
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Last.fm returned a non-JSON body for artist {artist_name!r}") from e

    def _extract_raw_tags(self, data: dict[str, Any]) -> list[str]:
        """Pull raw tag names from a Last.fm response body.

        Handles two wire-format quirks: Last.fm's XML-to-JSON layer sometimes returns a single tag as a bare dict instead of a 1-element list,
        and tag names occasionally come with leading/trailing whitespace. Tags whose names are empty after stripping are dropped.
        No lowercasing, separator collapse, synonym mapping, or deduplication happens here — those are read-time concerns so the cache survives future normalization tweaks.

        Args:
            data: Parsed JSON body from the Last.fm API.

        Returns:
            List of raw tag-name strings (whitespace stripped, empties dropped) in the order Last.fm returned them.
        """
        toptags_raw: Any = data.get("toptags", {})
        if not isinstance(toptags_raw, dict):
            return []
        toptags = cast(dict[str, Any], toptags_raw)
        raw: Any = toptags.get("tag", [])
        if isinstance(raw, dict):
            raw = [raw]
        if not isinstance(raw, list):
            return []
        items = (cast(dict[str, Any], item) for item in cast(list[Any], raw) if isinstance(item, dict))
        stripped = (str(item.get("name", "")).strip() for item in items)
        return [name for name in stripped if name]

    @classmethod
    def _normalize_and_dedupe(cls, raw_tags: list[str]) -> tuple[str, ...]:
        """Apply the read-time normalization pipeline to a raw tag list.

        Pipeline: ``_normalize_tag`` per element (lowercase + separator collapse + synonym lookup), drop empties, order-preserving dedupe via ``dict.fromkeys``.

        Args:
            raw_tags: Tag names as stored on disk (already JSON-shape-cleaned and whitespace-stripped by ``_extract_raw_tags``, but otherwise raw).

        Returns:
            Tuple of canonical, unique tags in first-occurrence order.
        """
        normalized = (cls._normalize_tag(t) for t in raw_tags)
        non_empty = (n for n in normalized if n)
        return tuple(dict.fromkeys(non_empty))

    @classmethod
    def _normalize_tag(cls, raw_name: str) -> str:
        """Canonicalize a single raw tag.

        Pipeline: lowercase + strip → replace every non-word non-space character (and underscore) with space → collapse multi-space → ``TAG_SYNONYMS`` lookup.
        The character rule handles all separator and punctuation variants of the same concept (``hip-hop``, ``hip_hop``, ``rock'n'roll``, ``drum & bass``
        all canonicalize without synonym entries); the synonym map is reserved for genuine word-level cases (``hiphop`` → ``hip hop``, ``r b`` → ``rnb``).

        Args:
            raw_name: Raw tag string from Last.fm.

        Returns:
            Canonical form. Returns ``""`` when the input is all-whitespace or all-disallowed-chars so the caller can filter.
        """
        normalized = raw_name.strip().lower()
        normalized = _DISALLOWED_TAG_CHAR_RE.sub(" ", normalized)
        normalized = " ".join(normalized.split())
        return cls.TAG_SYNONYMS.get(normalized, normalized)
