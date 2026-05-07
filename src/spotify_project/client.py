from __future__ import annotations

# pyright: reportUnknownMemberType=false
# spotipy's inline annotations leave several core methods partially typed (next, playlist, artist). 
# Their parameter types are `Unknown` because spotipy uses `**kwargs` forwarding internally. 
# All call sites already wrap the return value with `cast(dict[str, Any], …)`, so the Unknown only surfaces at the method-type level, not in our downstream usage.
import logging
import os
import time
from collections.abc import Iterable
from pathlib import Path
from typing import Any, ClassVar, cast

import spotipy
from spotipy.oauth2 import SpotifyOAuth

from .cache import FileCache
from .models import Artist, Playlist, Track

logger = logging.getLogger(__name__)


class SpotifyClient:
    """Authenticated Spotify Web API client with caching and pagination.

    Wraps a ``spotipy.Spotify`` instance. The constructor accepts an injected client (for testing); production code uses ``from_env`` to build one from environment variables.

    Attributes:
        sp: The wrapped spotipy.Spotify client.
        cache: FileCache for API response persistence.
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

    DEFAULT_TOKEN_CACHE: ClassVar[str] = ".cache/spotify_token"

    # Artist genres / popularity rarely change; long TTL avoids re-paying the per-artist API cost on every notebook re-run. 
    # Spotify's Feb 2026 batch-artists deprecation made these calls expensive (one round-trip per artist), and a 3000-track library can easily reference 2000+ unique artists.
    ARTIST_CACHE_TTL_DAYS: ClassVar[float] = 365.0

    # Inter-call sleep applied AFTER each uncached artist fetch. ~4 req/sec stays well under Spotify's rolling-window rate limit. 
    # Cache hits skip the sleep, so a warm cache pays no overhead.
    ARTIST_FETCH_DELAY_SECONDS: ClassVar[float] = 0.25

    def __init__(self, sp: spotipy.Spotify, cache: FileCache) -> None:
        self.sp = sp
        self.cache = cache

    @classmethod
    def from_env(cls, cache: FileCache, scopes: list[str] | None = None) -> SpotifyClient:
        """Build an OAuth-authenticated client from SPOTIPY_* env vars.

        Reads required credentials from the process environment (loaded from ``.env`` via python-dotenv at notebook startup, or set as OS env vars). 
        Fails loud at construction time if any are missing, rather than letting spotipy surface a cryptic HTTP 400 later.

        Args:
            cache: FileCache for API response persistence.
            scopes: OAuth scopes; defaults to ``DEFAULT_SCOPES`` (read-only).

        Returns:
            An authenticated SpotifyClient. Triggers a browser-based OAuth flow on first run; subsequent runs use spotipy's local token cache.

        Raises:
            RuntimeError: If any of the required ``SPOTIPY_*`` env vars are unset or empty.
        """
        missing = [k for k in cls.REQUIRED_ENV_VARS if not os.environ.get(k)]
        if missing:
            raise RuntimeError(f"Missing required env var(s): {', '.join(missing)}. Copy .env.example to .env and fill them in, or set them with `setx` (Windows) / `export` (Unix).")
        scope_str = " ".join(scopes or cls.DEFAULT_SCOPES)
        token_cache_path = Path(cls.DEFAULT_TOKEN_CACHE)
        token_cache_path.parent.mkdir(parents=True, exist_ok=True)
        oauth = SpotifyOAuth(
            client_id=os.environ["SPOTIPY_CLIENT_ID"],
            client_secret=os.environ["SPOTIPY_CLIENT_SECRET"],
            redirect_uri=os.environ["SPOTIPY_REDIRECT_URI"],
            scope=scope_str,
            cache_path=str(token_cache_path),
        )
        sp = spotipy.Spotify(auth_manager=oauth)
        return cls(sp=sp, cache=cache)

    def current_user(self) -> dict[str, Any]:
        """Return the authenticated user's profile dict."""
        return cast(dict[str, Any], self.sp.current_user())

    def user_playlists(self) -> list[dict[str, Any]]:
        """List the authenticated user's playlists (id, name, track count).

        Filters out ``None`` entries — Spotify occasionally returns null slots in the array for deleted or otherwise inaccessible playlists.
        """
        results = cast(dict[str, Any], self.sp.current_user_playlists())
        items: list[dict[str, Any]] = [p for p in results["items"] if p is not None]
        while results.get("next"):
            results = cast(dict[str, Any], self.sp.next(results))
            items.extend(p for p in results["items"] if p is not None)
        return items

    def playlist(self, playlist_id: str, *, force_refresh: bool = False) -> Playlist:
        """Fetch a playlist by ID, fully enriched with Artist objects.

        Two-phase: paginated track fetch, then a batched artist fetch for unique artist IDs across all tracks. 
        Each Track ends up holding full ``Artist`` references (with genres) — callers can read ``track.primary_artist.genres`` directly.

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
            data = cast(dict[str, Any], self.sp.playlist(playlist_id))
            if not data.get("items"):
                raise ValueError(f"Playlist {playlist_id} returned no track details.")
            track_items: list[dict[str, Any]] = list(data["items"]["items"])
            page: dict[str, Any] = data["items"]
            while page.get("next"):
                page = cast(dict[str, Any], self.sp.next(page))
                track_items.extend(page["items"])
            data["items"]["items"] = track_items
            data["items"].pop("next", None)
            self.cache.put(cache_key, data)
        else:
            data = cached
            track_items = data["items"]["items"]

        track_items = [it for it in track_items if it.get("item") and it["item"].get("type") == "track"]

        artist_ids: set[str] = set()
        for item in track_items:
            for a in item["item"].get("artists", []):
                if a.get("id"):
                    artist_ids.add(a["id"])

        artist_by_id: dict[str, Artist] = {a.id: a for a in self.artists(artist_ids, force_refresh=force_refresh)}

        tracks = [Track.from_api(item, artist_by_id) for item in track_items]
        return Playlist.from_api(data, tracks)

    def liked_songs(self, *, force_refresh: bool = False) -> Playlist:
        """Fetch the authenticated user's saved tracks as a pseudo-Playlist.

        Spotify's "Liked Songs" is not a real playlist — it has no id, no owner, no description. 
        We model it as a synthesized ``Playlist`` with ``id="__liked__"`` so the rest of the pipeline (Track parsing, PlaylistAnalyzer, every analyzer) consumes it unchanged.

        Two-phase like ``playlist()``: paginate ``current_user_saved_tracks`` (50/page), then batch-fetch unique artists.
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
            first = cast(dict[str, Any], self.sp.current_user_saved_tracks(limit=50))
            # Convert legacy {"track": ...} → {"item": ...} so the rest of the pipeline (which reads item["item"]) can consume unchanged.
            raw_items: list[dict[str, Any]] = list(first["items"])
            page: dict[str, Any] = first
            while page.get("next"):
                page = cast(dict[str, Any], self.sp.next(page))
                raw_items.extend(page["items"])
            items: list[dict[str, Any]] = [
                {
                    "item": it["track"],
                    "added_at": it.get("added_at"),
                    "is_local": False,
                }
                for it in raw_items if it.get("track")
            ]
            data = {
                "id": "__liked__",
                "name": "Liked Songs",
                "owner": {"display_name": self.current_user().get("display_name", "")},
                "public": False,
                "collaborative": False,
                "description": "",
                "items": {"items": items},
            }
            self.cache.put(cache_key, data)
        else:
            data = cached
            items = data["items"]["items"]

        track_items = [it for it in items if it.get("item") and it["item"].get("type") == "track"]

        artist_ids: set[str] = set()
        for item in track_items:
            for a in item["item"].get("artists", []):
                if a.get("id"):
                    artist_ids.add(a["id"])

        artist_by_id: dict[str, Artist] = {a.id: a for a in self.artists(artist_ids, force_refresh=force_refresh)}

        tracks = [Track.from_api(item, artist_by_id) for item in track_items]
        return Playlist.from_api(data, tracks)

    def artists(self, artist_ids: Iterable[str], *,force_refresh: bool = False) -> list[Artist]:
        """Fetch artists by ID, one call per artist.

        Spotify removed the batch ``GET /artists?ids=...`` endpoint in February 2026 (403 Forbidden for new apps). The only path now is single-artist ``GET /artists/{id}``. Each result is cached individually under ``artist/<id>``, so a refresh of the same playlist hits the cache instead of the API.

        Args:
            artist_ids: Iterable of Spotify artist IDs.
            force_refresh: Skip the cache and refetch from the API.

        Returns:
            List of Artist objects with full genre data, sorted by id (the deduplication order — not the input order).
        """
        ids = sorted(set(artist_ids))
        if not ids:
            return []
        out: list[Artist] = []
        for artist_id in ids:
            cache_key = f"artist/{artist_id}"
            cached = (None if force_refresh else self.cache.get(cache_key, ttl_days=self.ARTIST_CACHE_TTL_DAYS))
            data: dict[str, Any]
            if cached is None:
                data = cast(dict[str, Any], self.sp.artist(artist_id))
                self.cache.put(cache_key, data)
                time.sleep(self.ARTIST_FETCH_DELAY_SECONDS)
            else:
                data = cached
            out.append(Artist.from_api(data))
        return out
