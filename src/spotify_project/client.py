from __future__ import annotations

import logging
import os
import time
from collections.abc import Callable, Iterable
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, cast

if TYPE_CHECKING:
    from .lastfm_client import LastFmClient

import spotipy
from spotipy.exceptions import SpotifyException
from spotipy.oauth2 import SpotifyOAuth
from tqdm import tqdm as _tqdm_cls

from .cache import FileCache
from .models import Artist, Playlist, PlaylistSummary, Track, User

logger = logging.getLogger(__name__)


class SpotifyClient:
    """Authenticated Spotify Web API client with caching and pagination.

    Wraps a ``spotipy.Spotify`` instance. The constructor accepts an injected client (for testing); production code uses ``from_env`` to build one from environment variables.

    Attributes:
        sp: The wrapped spotipy.Spotify client.
        cache: FileCache for API response persistence.
        genre_enricher: Optional Last.fm client. When set, ``_enrich_with_artists`` calls ``fetch_artist_tags`` per artist after Spotify resolves; when None, ``Artist.tags`` stays empty.
    """

    DEFAULT_SCOPES: ClassVar[list[str]] = [
        "user-read-private",
        "user-read-email",
        "playlist-read-private",
        "playlist-read-collaborative",
        "user-library-read",
        "user-top-read",
    ]

    REQUIRED_ENV_VARS: ClassVar[tuple[str, ...]] = (
        "SPOTIPY_CLIENT_ID",
        "SPOTIPY_CLIENT_SECRET",
        "SPOTIPY_REDIRECT_URI",
    )

    # Anchored to the repo root (like FileCache's default dir), not the CWD — a Jupyter kernel's CWD is the notebook's directory,
    # which used to mint a second token at notebooks/.cache/spotify_token.
    DEFAULT_TOKEN_CACHE: ClassVar[Path] = Path(__file__).resolve().parents[2] / ".cache" / "spotify_token"

    # Artist data rarely changes; long TTL avoids re-paying the per-artist API cost on every notebook re-run.
    # Spotify's Feb 2026 batch-artists deprecation made these calls expensive (one round-trip per artist), and a 3000-track library can easily reference 2000+ unique artists.
    ARTIST_CACHE_TTL_DAYS: ClassVar[float] = 365.0

    # Inter-call sleep applied AFTER each uncached artist fetch. ~4 req/sec stays well under Spotify's rolling-window rate limit.
    # Cache hits skip the sleep, so a warm cache pays no overhead.
    ARTIST_FETCH_DELAY_SECONDS: ClassVar[float] = 0.25

    # Upper bound for honoring a Spotify Retry-After. Beyond this, the call raises instead of sleeping —
    # a single 429 with Retry-After: 86400s used to freeze the notebook kernel with no way to interrupt cleanly.
    MAX_RATE_LIMIT_WAIT_SECONDS: ClassVar[int] = 20 * 60

    # status_forcelist for spotipy.Spotify's urllib3 Retry adapter. spotipy's default includes 429,
    # which makes urllib3 silently sleep through Retry-After (up to 24h) before raising — exactly the freeze we want to avoid.
    # Excluding 429 lets it bubble up as SpotifyException(http_status=429, headers={"Retry-After": ...}) so ``_call`` can decide.
    RETRY_STATUS_FORCELIST: ClassVar[tuple[int, ...]] = (500, 502, 503, 504)

    def __init__(self, sp: spotipy.Spotify, cache: FileCache, *, genre_enricher: LastFmClient | None = None) -> None:
        self.sp = sp
        self.cache = cache
        self.genre_enricher = genre_enricher

    @classmethod
    def from_env(cls, cache: FileCache, scopes: list[str] | None = None, *, genre_enricher: LastFmClient | None = None) -> SpotifyClient:
        """Build an OAuth-authenticated client from SPOTIPY_* env vars.

        Reads required credentials from the process environment (loaded from ``.env`` via python-dotenv at notebook startup, or set as OS env vars).
        Fails loud at construction time if any are missing, rather than letting spotipy surface a cryptic HTTP 400 later.

        Args:
            cache: FileCache for API response persistence.
            scopes: OAuth scopes; defaults to ``DEFAULT_SCOPES`` (read-only).
            genre_enricher: Optional Last.fm client for tag enrichment. When None (default), Artist.tags stays empty and the TagAnalyzer / GenreAnalyzer panels are skipped downstream.

        Returns:
            An authenticated SpotifyClient. Triggers a browser-based OAuth flow on first run; subsequent runs use spotipy's local token cache.

        Raises:
            RuntimeError: If any of the required ``SPOTIPY_*`` env vars are unset or empty.
        """
        missing = [k for k in cls.REQUIRED_ENV_VARS if not os.environ.get(k)]
        if missing:
            raise RuntimeError(f"Missing required env var(s): {', '.join(missing)}. Copy .env.example to .env and fill them in, or set them with `setx` (Windows) / `export` (Unix).")
        scope_str = " ".join(scopes or cls.DEFAULT_SCOPES)
        token_cache_path = cls.DEFAULT_TOKEN_CACHE
        token_cache_path.parent.mkdir(parents=True, exist_ok=True)
        oauth = SpotifyOAuth(
            client_id=os.environ["SPOTIPY_CLIENT_ID"],
            client_secret=os.environ["SPOTIPY_CLIENT_SECRET"],
            redirect_uri=os.environ["SPOTIPY_REDIRECT_URI"],
            scope=scope_str,
            cache_path=str(token_cache_path),
        )
        sp = spotipy.Spotify(auth_manager=oauth, status_forcelist=cls.RETRY_STATUS_FORCELIST)
        return cls(sp=sp, cache=cache, genre_enricher=genre_enricher)

    def _call(self, fn: Callable[..., Any], /, *args: Any, **kwargs: Any) -> Any:
        """Invoke a spotipy call with a Retry-After-aware rate-limit guard.

        Internal plumbing; callers go through the ``_sp_*`` wrappers below, which absorb the cast back to ``dict[str, Any]``.
        On HTTP 429, reads ``Retry-After`` from the response headers:
        if the cooldown is within ``MAX_RATE_LIMIT_WAIT_SECONDS``, sleeps and retries once.
        If the cooldown exceeds the threshold (e.g. Spotify's 24h block), logs an ERROR with a human-readable HH:MM:SS duration,
        and raises ``RuntimeError`` instead of sleeping — the historical behavior froze the notebook kernel with no way to interrupt cleanly.
        Non-429 ``SpotifyException`` instances pass through unchanged.

        Args:
            fn: Bound spotipy method (e.g. ``self.sp.artist``).
            *args: Positional arguments forwarded to ``fn``.
            **kwargs: Keyword arguments forwarded to ``fn``.

        Returns:
            Whatever ``fn`` returned (typed ``Any`` because spotipy methods are untyped — the ``_sp_*`` wrappers cast back to the concrete shape).

        Raises:
            RuntimeError: If Retry-After exceeds ``MAX_RATE_LIMIT_WAIT_SECONDS``, or if a second consecutive 429 occurs (regardless of its Retry-After value).
            SpotifyException: For any non-429 API error, unchanged.
        """
        for attempt in range(2):
            try:
                return fn(*args, **kwargs)
            except SpotifyException as exc:
                if exc.http_status != 429:
                    raise
                retry_after = self._parse_retry_after(exc)
                if retry_after > self.MAX_RATE_LIMIT_WAIT_SECONDS:
                    duration = self._format_duration(retry_after)
                    logger.error(
                        "Spotify rate-limit cooldown is %s (%ds) — refusing to wait. Stop here and re-run the notebook after the cooldown expires.",
                        duration,
                        retry_after,
                    )
                    raise RuntimeError(f"Spotify rate-limit cooldown is {duration} ({retry_after}s); refusing to wait. Re-run the notebook after the cooldown expires.") from exc
                if attempt == 0:
                    logger.warning("Spotify rate-limited; sleeping %ds and retrying once.", retry_after)
                    time.sleep(retry_after)
                    continue
                raise RuntimeError(f"Spotify rate-limit persisted after a retry (second Retry-After: {retry_after}s); aborting.") from exc
        # Unreachable — the loop either returns, sleeps-and-continues, or raises. The bare raise placates pyright's exhaustiveness check.
        raise AssertionError("unreachable")

    @staticmethod
    def _parse_retry_after(exc: SpotifyException) -> int:
        """Extract a usable Retry-After value (seconds) from a SpotifyException.

        Falls back to ``MAX_RATE_LIMIT_WAIT_SECONDS + 1`` (just above the threshold) when the header is missing, blank, or non-numeric — that way the bail-out path triggers,
        which is the safer default than retrying immediately and re-tripping the limit. spotipy's urllib3-retry exhaustion path sets ``headers={}``, so this case is real.

        Args:
            exc: The SpotifyException raised on a 429 response.

        Returns:
            Retry-After in seconds, or a sentinel above the threshold when unavailable.
        """
        headers = cast(dict[str, Any] | None, exc.headers)  # pyright: ignore[reportUnknownMemberType]
        raw: Any = headers.get("Retry-After") if headers else None
        if raw is None:
            return SpotifyClient.MAX_RATE_LIMIT_WAIT_SECONDS + 1
        try:
            return int(str(raw).strip())
        except ValueError:
            logger.warning("Unparseable Retry-After header %r; treating as over-threshold.", raw)
            return SpotifyClient.MAX_RATE_LIMIT_WAIT_SECONDS + 1

    @staticmethod
    def _format_duration(seconds: int) -> str:
        """Format a seconds count as ``H:MM:SS`` for log messages."""
        hours, remainder = divmod(seconds, 3600)
        minutes, secs = divmod(remainder, 60)
        return f"{hours:d}:{minutes:02d}:{secs:02d}"

    # region spotipy method wrappers
    # spotipy is untyped, so every direct ``self.sp.*`` call surfaces as Unknown and forces a cast plus a ``# pyright: ignore`` at the call site.
    # These thin wrappers absorb that noise once per method and give the business-logic methods (``fetch_playlist``, ``fetch_liked_songs``, …) concrete return types.
    # Each wrapper goes through ``_call`` so the Retry-After-aware rate-limit guard still applies.

    def _sp_current_user(self) -> dict[str, Any]:
        return cast(dict[str, Any], self._call(self.sp.current_user))

    def _sp_current_user_playlists(self) -> dict[str, Any]:
        return cast(dict[str, Any], self._call(self.sp.current_user_playlists))

    def _sp_next(self, page: dict[str, Any]) -> dict[str, Any]:
        return cast(dict[str, Any], self._call(self.sp.next, page))  # pyright: ignore[reportUnknownArgumentType, reportUnknownMemberType]

    def _sp_playlist(self, playlist_id: str) -> dict[str, Any]:
        return cast(dict[str, Any], self._call(self.sp.playlist, playlist_id))  # pyright: ignore[reportUnknownArgumentType, reportUnknownMemberType]

    def _sp_current_user_saved_tracks(self, *, limit: int) -> dict[str, Any]:
        return cast(dict[str, Any], self._call(self.sp.current_user_saved_tracks, limit=limit))  # pyright: ignore[reportUnknownArgumentType, reportUnknownMemberType]

    def _sp_artist(self, artist_id: str) -> dict[str, Any]:
        return cast(dict[str, Any], self._call(self.sp.artist, artist_id))  # pyright: ignore[reportUnknownArgumentType, reportUnknownMemberType]

    # endregion

    def fetch_current_user(self) -> User:
        """Return the authenticated user's profile.

        Returns:
            Parsed ``User`` with id, display_name, and email (None if scope not granted).

        Raises:
            RuntimeError: If the API returns a user payload without an ``id`` (stale or invalid token).
        """
        data = self._sp_current_user()
        if not data.get("id"):
            raise RuntimeError(f"Spotify returned a user payload with no id; check token validity. Keys: {list(data.keys())}")
        return User(
            id=data["id"],
            display_name=data.get("display_name", "") or "",
            email=data.get("email"),
        )

    def fetch_user_playlists(self) -> list[PlaylistSummary]:
        """List the authenticated user's playlists.

        Filters out ``None`` slots in the API response (Spotify occasionally returns null entries for deleted or inaccessible playlists).

        Returns:
            List of ``PlaylistSummary`` objects, one per playlist.
        """
        results = self._sp_current_user_playlists()
        raw: list[dict[str, Any]] = [p for p in results["items"] if p is not None]
        dropped = len(results["items"]) - len(raw)
        while results.get("next"):
            results = self._sp_next(results)
            batch = [p for p in results["items"] if p is not None]
            dropped += len(results["items"]) - len(batch)
            raw.extend(batch)
        if dropped > 0:
            logger.info("Dropped %d deleted/inaccessible playlists", dropped)
        return [
            PlaylistSummary(
                id=str(p.get("id") or ""),
                name=str(p.get("name") or ""),
                owner_name=str((p.get("owner") or {}).get("display_name") or ""),  # pyright: ignore[reportUnknownArgumentType, reportUnknownMemberType]
                # Spotify renamed tracks → items in Feb 2026
                track_count=int((p.get("items") or {}).get("total", 0)),  # pyright: ignore[reportUnknownArgumentType, reportUnknownMemberType]
                public=bool(p.get("public", False)),
            )
            for p in raw
        ]

    def fetch_playlist(self, playlist_id: str, *, force_refresh: bool = False) -> Playlist:
        """Fetch a playlist by ID, fully enriched with Artist objects.

        Two-phase: paginated track fetch, then a batched artist fetch for unique artist IDs across all tracks.
        Each Track ends up holding full ``Artist`` references — callers can read ``track.primary_artist.tags`` and ``.genres`` directly (genres is derived from tags via Last.fm enrichment when enabled).
        Cached with default TTL (see ``FileCache``); pass ``force_refresh=True`` to bypass.

        Args:
            playlist_id: Spotify playlist ID.
            force_refresh: Skip the cache and refetch from the API.

        Returns:
            A fully-enriched Playlist.
        """
        cache_key = f"playlist/{playlist_id}"
        cached = None if force_refresh else self.cache.get(cache_key)
        data: dict[str, Any]
        if cached is None:
            logger.info("Fetching playlist %s from API", playlist_id)
            data = self._sp_playlist(playlist_id)
            if "items" not in data:
                owner_name = str((data.get("owner") or {}).get("display_name") or "<unknown>")  # pyright: ignore[reportUnknownArgumentType, reportUnknownMemberType]
                playlist_name = data.get("name", "<unknown>")
                raise ValueError(f"Playlist {playlist_id} [Owner: {owner_name}, Name: {playlist_name}] returned no track details.")
            track_items: list[dict[str, Any]] = list(data["items"]["items"])
            page: dict[str, Any] = data["items"]
            while page.get("next"):
                page = self._sp_next(page)
                track_items.extend(page["items"])
            data["items"]["items"] = track_items
            data["items"].pop("next", None)
            self.cache.put(cache_key, data)
        else:
            logger.debug("Cache hit for playlist %s", playlist_id)
            data = cached
            track_items = data["items"]["items"]

        tracks = self._enrich_with_artists(track_items, force_refresh=force_refresh)
        return Playlist.from_api(data, tracks)

    def fetch_liked_songs(self, *, force_refresh: bool = False) -> Playlist:
        """Fetch the authenticated user's saved tracks as a pseudo-Playlist.

        Spotify's "Liked Songs" is not a real playlist — it has no id, no owner, no description.
        We model it as a synthesized ``Playlist`` with ``id="__liked__"`` so the rest of the pipeline (Track parsing, PlaylistAnalyzer, every analyzer) consumes it unchanged.

        Two-phase like ``fetch_playlist()``: paginate ``current_user_saved_tracks`` (50/page), then batch-fetch unique artists.
        The cached blob can be several MB for 3000+ saved tracks; the default 7-day ``FileCache`` TTL applies (cached artists default TTL 365-day too).

        Args:
            force_refresh: Skip the cache and refetch from the API.

        Returns:
            A pseudo-Playlist with id ``"__liked__"`` and name ``"Liked Songs"``.
        """
        cache_key = "liked/me"
        cached = None if force_refresh else self.cache.get(cache_key)
        data: dict[str, Any]
        if cached is None:
            logger.info("Fetching liked songs from API")
            first = self._sp_current_user_saved_tracks(limit=50)
            # Schema normalization: current_user_saved_tracks returns {"track": ...} per item, while the playlist endpoints return {"item": ...}
            # (Feb 2026 rename — never propagated to the saved-tracks endpoint).
            # Renaming the key here lets the rest of the pipeline (Track.from_api reads item["item"]) consume both sources uniformly.
            raw_items: list[dict[str, Any]] = list(first["items"])
            dropped = sum(1 for it in first["items"] if it.get("track") is None)
            page: dict[str, Any] = first
            while page.get("next"):
                page = self._sp_next(page)
                raw_items.extend(page["items"])
                dropped += sum(1 for it in page["items"] if it.get("track") is None)
            items: list[dict[str, Any]] = [
                {
                    "item": it["track"],
                    "added_at": it.get("added_at"),
                    "is_local": False,
                }
                for it in raw_items
                if it.get("track")
            ]
            if dropped > 0:
                logger.info("Dropped %d null tracks from liked songs", dropped)
            data = {
                "id": "__liked__",
                "name": "Liked Songs",
                "owner": {"display_name": self.fetch_current_user().display_name},
                "public": False,
                "collaborative": False,
                "description": "",
                "items": {"items": items},
            }
            self.cache.put(cache_key, data)
        else:
            logger.debug("Cache hit for liked songs")
            data = cached
            items = data["items"]["items"]

        tracks = self._enrich_with_artists(items, force_refresh=force_refresh)
        return Playlist.from_api(data, tracks)

    def _enrich_with_artists(self, track_items: list[dict[str, Any]], *, force_refresh: bool = False) -> list[Track]:
        """Filter to audio tracks, resolve artist lookups, and return Track objects.

        One pipeline runs in two stages: filter to audio tracks → collect unique artist IDs → batch-fetch Spotify artists via ``fetch_artists()``. If ``genre_enricher`` is set,
        a second pass over the resolved artists calls ``LastFmClient.fetch_artist_tags`` per artist and rebuilds the in-memory artist map with populated ``tags``;
        the Spotify-side cache is never modified.

        Args:
            track_items: Raw playlist-item dicts using the ``item`` key schema.
            force_refresh: Passed through to both ``fetch_artists()`` and ``LastFmClient.fetch_artist_tags()``.

        Returns:
            List of fully-enriched Track objects. Non-track items (podcast episodes, null slots) are dropped; local files pass through — they carry ``type: "track"`` and are flagged via ``Track.is_local``.
        """
        audio_tracks = [it for it in track_items if it.get("item") and it["item"].get("type") == "track"]
        dropped = len(track_items) - len(audio_tracks)
        if dropped > 0:
            logger.info("Dropped %d non-track items (podcast episodes, null slots)", dropped)
        logger.info("Enriching %d tracks with artist data", len(audio_tracks))
        artist_ids: set[str] = set()
        for item in audio_tracks:
            for a in item["item"].get("artists", []):
                if a.get("id"):
                    artist_ids.add(a["id"])
        artist_by_id: dict[str, Artist] = {a.id: a for a in self.fetch_artists(artist_ids, force_refresh=force_refresh)}

        if self.genre_enricher is not None:
            logger.info("Enriching %d artists with Last.fm tags", len(artist_by_id))
            enriched: dict[str, Artist] = {}
            iter_artists: Iterable[Artist] = _tqdm_cls(artist_by_id.values(), desc="Enriching with Last.fm tags", unit="artist")  # pyright: ignore[reportUnknownVariableType]
            for artist in iter_artists:
                tags = self.genre_enricher.fetch_artist_tags(artist.id, artist.name, force_refresh=force_refresh)
                enriched[artist.id] = replace(artist, tags=tags)
            artist_by_id = enriched

        return [Track.from_api(item, artist_by_id) for item in audio_tracks]

    def fetch_artists(self, artist_ids: Iterable[str], *, force_refresh: bool = False) -> list[Artist]:
        """Fetch artists by ID, one call per artist.

        Spotify removed the batch ``GET /artists?ids=...`` endpoint in February 2026 (403 Forbidden for new apps). The only path now is single-artist ``GET /artists/{id}``. Each result is cached individually under ``artist/<id>``, so a refresh of the same playlist hits the cache instead of the API.
        Cached with default TTL (see ``FileCache``); pass ``force_refresh=True`` to bypass.

        Args:
            artist_ids: Iterable of Spotify artist IDs.
            force_refresh: Skip the cache and refetch from the API.

        Returns:
            List of Artist objects with id and name; ``tags`` stays empty until Last.fm enrichment fills it in ``_enrich_with_artists``. Sorted by id (the deduplication order — not the input order).
        """
        ids = sorted(set(artist_ids))
        if not ids:
            return []
        logger.info("Fetching %d unique artists", len(ids))
        out: list[Artist] = []
        ids_iter: Iterable[str] = _tqdm_cls(ids, desc="Fetching artists", unit="artist")  # pyright: ignore[reportUnknownVariableType]
        for artist_id in ids_iter:
            cache_key = f"artist/{artist_id}"
            cached = None if force_refresh else self.cache.get(cache_key, ttl_days=self.ARTIST_CACHE_TTL_DAYS)
            data: dict[str, Any]
            if cached is None:
                logger.debug("Cache miss — fetching artist %s", artist_id)
                data = self._sp_artist(artist_id)
                self.cache.put(cache_key, data)
                time.sleep(self.ARTIST_FETCH_DELAY_SECONDS)
            else:
                logger.debug("Cache hit for artist %s", artist_id)
                data = cached
            out.append(Artist.from_api(data))
        return out
