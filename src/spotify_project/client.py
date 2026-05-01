from __future__ import annotations

import logging
from collections.abc import Iterable
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
        "playlist-read-private",
        "playlist-read-collaborative",
        "user-library-read",
        "user-top-read",
    ]

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

        Args:
            cache: FileCache for API response persistence.
            scopes: OAuth scopes; defaults to ``DEFAULT_SCOPES`` (read-only).

        Returns:
            An authenticated SpotifyClient. Triggers a browser-based OAuth
            flow on first run; subsequent runs use spotipy's local token cache.
        """
        scope_str = " ".join(scopes or cls.DEFAULT_SCOPES)
        oauth = SpotifyOAuth(scope=scope_str)
        sp = spotipy.Spotify(auth_manager=oauth)
        return cls(sp=sp, cache=cache)

    def current_user(self) -> dict[str, Any]:
        """Return the authenticated user's profile dict."""
        return cast(dict[str, Any], self.sp.current_user())

    def user_playlists(self) -> list[dict[str, Any]]:
        """List the authenticated user's playlists (id, name, track count)."""
        results = self.sp.current_user_playlists()
        items: list[dict[str, Any]] = list(results["items"])
        while results.get("next"):
            results = self.sp.next(results)
            items.extend(results["items"])
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
        if cached is None:
            data = self.sp.playlist(playlist_id)
            track_items: list[dict[str, Any]] = list(data["tracks"]["items"])
            page = data["tracks"]
            while page.get("next"):
                page = self.sp.next(page)
                track_items.extend(page["items"])
            data["tracks"]["items"] = track_items
            self.cache.put(cache_key, data)
        else:
            data = cached
            track_items = data["tracks"]["items"]

        track_items = [
            it
            for it in track_items
            if it.get("track") and it["track"].get("type") == "track"
        ]

        artist_ids: set[str] = set()
        for item in track_items:
            for a in item["track"].get("artists", []):
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
        """Fetch a batch of artists; respects Spotify's 50-IDs-per-call cap.

        Args:
            artist_ids: Iterable of Spotify artist IDs.
            force_refresh: Skip the cache and refetch from the API.

        Returns:
            List of Artist objects with full genre data, in arbitrary order.
        """
        ids = sorted(set(artist_ids))
        if not ids:
            return []
        out: list[Artist] = []
        for i in range(0, len(ids), 50):
            batch = ids[i : i + 50]
            cache_key = f"artists/{','.join(batch)}"
            cached = None if force_refresh else self.cache.get(cache_key)
            if cached is None:
                data = self.sp.artists(batch)
                self.cache.put(cache_key, data)
            else:
                data = cached
            for a in data.get("artists", []):
                if a is not None:
                    out.append(Artist.from_api(a))
        return out
