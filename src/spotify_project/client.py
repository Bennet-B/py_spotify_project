from __future__ import annotations

# pyright: reportUnknownMemberType=false
# spotipy's inline annotations leave several core methods partially typed
# (next, playlist, artist).  Their parameter types are `Unknown` because
# spotipy uses `**kwargs` forwarding internally.  All call sites already
# wrap the return value with `cast(dict[str, Any], …)`, so the Unknown
# only surfaces at the method-type level, not in our downstream usage.
import logging
import os
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

    Wraps a ``spotipy.Spotify`` instance. The constructor accepts an
    injected client (for testing); production code uses ``from_env`` to
    build one from environment variables.

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

    def __init__(self, sp: spotipy.Spotify, cache: FileCache) -> None:
        self.sp = sp
        self.cache = cache

    @classmethod
    def from_env(
        cls,
        cache: FileCache,
        scopes: list[str] | None = None,
    ) -> SpotifyClient:
        """Build an OAuth-authenticated client from SPOTIPY_* env vars.

        Reads required credentials from the process environment (loaded
        from ``.env`` via python-dotenv at notebook startup, or set as OS
        env vars). Fails loud at construction time if any are missing,
        rather than letting spotipy surface a cryptic HTTP 400 later.

        Args:
            cache: FileCache for API response persistence.
            scopes: OAuth scopes; defaults to ``DEFAULT_SCOPES`` (read-only).

        Returns:
            An authenticated SpotifyClient. Triggers a browser-based OAuth
            flow on first run; subsequent runs use spotipy's local token cache.

        Raises:
            RuntimeError: If any of the required ``SPOTIPY_*`` env vars are
                unset or empty.
        """
        missing = [k for k in cls.REQUIRED_ENV_VARS if not os.environ.get(k)]
        if missing:
            raise RuntimeError(
                f"Missing required env var(s): {', '.join(missing)}. "
                "Copy .env.example to .env and fill them in, "
                "or set them with `setx` (Windows) / `export` (Unix)."
            )
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

        Filters out ``None`` entries — Spotify occasionally returns null
        slots in the array for deleted or otherwise inaccessible playlists.
        """
        results = cast(dict[str, Any], self.sp.current_user_playlists())
        items: list[dict[str, Any]] = [p for p in results["items"] if p is not None]
        while results.get("next"):
            results = cast(dict[str, Any], self.sp.next(results))
            items.extend(p for p in results["items"] if p is not None)
        return items

    def playlist(
        self,
        playlist_id: str,
        *,
        force_refresh: bool = False,
    ) -> Playlist:
        """Fetch a playlist by ID, fully enriched with Artist objects.

        Two-phase: paginated track fetch, then a batched artist fetch for
        unique artist IDs across all tracks. Each Track ends up holding
        full ``Artist`` references (with genres) — callers can read
        ``track.primary_artist.genres`` directly.

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
                raise ValueError(
                    f"Playlist {playlist_id} returned no track details. "
                    "Spotify's Feb 2026 API only includes tracks for "
                    "playlists you own or collaborate on. Pick a playlist "
                    "where the 'owner' column shows your display name."
                )
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

        track_items = [
            it
            for it in track_items
            if it.get("item") and it["item"].get("type") == "track"
        ]

        artist_ids: set[str] = set()
        for item in track_items:
            for a in item["item"].get("artists", []):
                if a.get("id"):
                    artist_ids.add(a["id"])

        artist_by_id: dict[str, Artist] = {
            a.id: a for a in self.artists(artist_ids, force_refresh=force_refresh)
        }

        tracks = [Track.from_api(item, artist_by_id) for item in track_items]
        return Playlist.from_api(data, tracks)

    def artists(
        self,
        artist_ids: Iterable[str],
        *,
        force_refresh: bool = False,
    ) -> list[Artist]:
        """Fetch artists by ID, one call per artist.

        Spotify removed the batch ``GET /artists?ids=...`` endpoint in
        February 2026 (403 Forbidden for new apps). The only path now is
        single-artist ``GET /artists/{id}``. Each result is cached
        individually under ``artist/<id>``, so a refresh of the same
        playlist hits the cache instead of the API.

        Args:
            artist_ids: Iterable of Spotify artist IDs.
            force_refresh: Skip the cache and refetch from the API.

        Returns:
            List of Artist objects with full genre data, sorted by id
            (the deduplication order — not the input order).
        """
        ids = sorted(set(artist_ids))
        if not ids:
            return []
        out: list[Artist] = []
        for artist_id in ids:
            cache_key = f"artist/{artist_id}"
            cached = None if force_refresh else self.cache.get(cache_key)
            data: dict[str, Any]
            if cached is None:
                data = cast(dict[str, Any], self.sp.artist(artist_id))
                self.cache.put(cache_key, data)
            else:
                data = cached
            out.append(Artist.from_api(data))
        return out
