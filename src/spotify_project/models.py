from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(slots=True, frozen=True)
class Artist:
    """A Spotify artist with their genres and popularity.

    Attributes:
        id: Spotify artist ID.
        name: Display name.
        genres: Tuple of genre tags assigned by Spotify (often empty).
        popularity: Integer 0-100; higher means more popular.

    Raises:
        ValueError: If popularity is outside [0, 100].
    """

    id: str
    name: str
    genres: tuple[str, ...]
    popularity: int

    def __post_init__(self) -> None:
        if not 0 <= self.popularity <= 100:
            raise ValueError(f"Artist popularity must be in [0, 100], got {self.popularity}")

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> Artist:
        """Parse a Spotify artist API response.

        Args:
            data: A spotipy artist dict with keys id/name/genres/popularity.

        Returns:
            The constructed Artist.
        """
        return cls(
            id=data["id"],
            name=data["name"],
            genres=tuple(data.get("genres", [])),
            popularity=int(data.get("popularity", 0)),
        )


@dataclass(slots=True, frozen=True)
class Track:
    """A single track in a Spotify playlist with full Artist references.

    Attributes:
        id: Spotify track ID; None for local files.
        name: Track name.
        artists: Tuple of Artist objects on this track. Empty for local files.
        album_name: Name of the track's album.
        release_date: ISO date string from Spotify; may be year-only.
        duration_ms: Length in milliseconds.
        popularity: 0-100 score.
        explicit: Whether the track has explicit content.
        added_at: When the track was added to the playlist. None for Spotify-curated playlists.
        is_local: True for user-uploaded local files.

    Raises:
        ValueError: If popularity is outside [0, 100], or if duration_ms is negative.
    """

    id: str | None
    name: str
    artists: tuple[Artist, ...]
    album_name: str
    release_date: str | None
    duration_ms: int
    popularity: int
    explicit: bool
    added_at: datetime | None
    is_local: bool

    def __post_init__(self) -> None:
        if not 0 <= self.popularity <= 100:
            raise ValueError(f"Track popularity must be in [0, 100], got {self.popularity}")
        if self.duration_ms < 0:
            raise ValueError(f"Track duration_ms must be >= 0, got {self.duration_ms}")

    @property
    def primary_artist(self) -> Artist | None:
        """The first artist on the track, or None for local files."""
        return self.artists[0] if self.artists else None

    @classmethod
    def from_api(cls, item: dict[str, Any], artist_by_id: dict[str, Artist]) -> Track:
        """Parse a playlist-item dict into a Track.

        Args:
            item: A spotipy playlist-item dict (with keys ``track``, ``added_at``, ``is_local``).
            artist_by_id: Lookup of fully-fetched Artist objects, populated by ``SpotifyClient.playlist``.

        Returns:
            The constructed Track. Tracks whose ``item.type`` is not ``"track"`` (e.g. podcast episodes) should be filtered out by the caller before this is called.
        """
        track_data = item["item"]
        is_local = item.get("is_local", False)
        resolved: list[Artist] = []
        for a in track_data.get("artists", []):
            aid = a.get("id")
            if not aid:
                continue
            if aid not in artist_by_id:
                logger.warning("artist %s not in lookup; track may lose primary_artist", aid)
                continue
            resolved.append(artist_by_id[aid])
        added_at_raw = item.get("added_at")
        added_at: datetime | None = None
        if added_at_raw:
            try:
                added_at = datetime.fromisoformat(added_at_raw)
            except ValueError:
                logger.warning("Unparseable added_at %r for track %s", added_at_raw, track_data.get("id", "<unknown>"))
        return cls(
            id=track_data.get("id"),
            name=track_data.get("name", ""),
            artists=tuple(resolved),
            album_name=track_data.get("album", {}).get("name", ""),
            release_date=track_data.get("album", {}).get("release_date"),
            duration_ms=int(track_data.get("duration_ms", 0)),
            popularity=int(track_data.get("popularity", 0)),
            explicit=bool(track_data.get("explicit", False)),
            added_at=added_at,
            is_local=is_local,
        )


@dataclass(slots=True, frozen=True)
class User:
    """Authenticated Spotify user profile.

    Attributes:
        id: Spotify user ID.
        display_name: Public display name.
        email: Account email; may be absent depending on granted scopes.
    """

    id: str
    display_name: str
    email: str | None


@dataclass(slots=True, frozen=True)
class PlaylistSummary:
    """Lightweight playlist entry as returned by the user-playlists listing.

    Distinct from ``Playlist`` (which holds enriched tracks and artists).

    Attributes:
        id: Spotify playlist ID.
        name: Display name.
        owner_name: Display name of the playlist's owner.
        track_count: Total number of tracks reported by the API.
        public: Whether the playlist is publicly visible.
    """

    id: str
    name: str
    owner_name: str
    track_count: int
    public: bool


@dataclass(slots=True, frozen=True)
class Playlist:
    """A Spotify playlist with metadata and its tracks.

    Attributes:
        id: Spotify playlist ID.
        name: Display name.
        owner_display_name: Display name of the playlist's owner.
        public: Visible to the world.
        collaborative: Other users can edit.
        description: Free-text description.
        tracks: Tuple of all Tracks (including local files).
    """

    id: str
    name: str
    owner_display_name: str
    public: bool
    collaborative: bool
    description: str
    tracks: tuple[Track, ...]

    @classmethod
    def from_api(cls, data: dict[str, Any], tracks: list[Track]) -> Playlist:
        """Parse a Spotify playlist API response.

        Args:
            data: A spotipy playlist dict with metadata fields.
            tracks: Pre-parsed Track list (built separately by SpotifyClient).

        Returns:
            The constructed Playlist.
        """
        return cls(
            id=data["id"],
            name=data.get("name", ""),
            owner_display_name=data.get("owner", {}).get("display_name", ""),
            public=bool(data.get("public", False)),
            collaborative=bool(data.get("collaborative", False)),
            description=data.get("description", ""),
            tracks=tuple(tracks),
        )
