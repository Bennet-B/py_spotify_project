# Phase 1 Implementation Plan — py_spotify_project

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Phase 1 MVP — a Spotify-playlist analytics library plus a Jupyter notebook demo — exactly as designed in `docs/superpowers/specs/2026-04-30-spotify-phase1-design.md`.

**Architecture:** Strategy-pattern `Analyzer` hierarchy producing summary DataFrames + matplotlib plots. Frozen dataclasses (`Track`/`Playlist`/`Artist`) form a rich object graph; flattening to pandas happens at the analyzer boundary only. `SpotifyClient` wraps spotipy with dependency injection (testable) and a 7-day file cache. See spec §2 for the full data flow.

**Tech Stack:** Python 3.14, spotipy 2.26, pandas 2.3, matplotlib 3.10 + seaborn 0.13, pytest 8.4, mypy 1.20. All installed in `.venv`.

---

## Pre-flight

Verify the environment before any task. Five seconds of check, lots of mistakes prevented.

- [ ] **Step 0.1: Confirm interpreter and key imports**

  Run:
  ```
  .venv/Scripts/python.exe -c "import spotipy, pandas, matplotlib, seaborn; print('ok')"
  ```
  Expected: prints `ok`. If you get an `ImportError`, the venv is broken — re-run `pip install -r requirements.txt`.

- [ ] **Step 0.2: Confirm test runner and type checker**

  Run:
  ```
  .venv/Scripts/python.exe -m pytest --version && .venv/Scripts/python.exe -m mypy --version
  ```
  Expected: both print version numbers.

- [ ] **Step 0.3: Confirm import path**

  Run:
  ```
  .venv/Scripts/python.exe -c "import sys; sys.path.insert(0, 'src'); import spotify_project; print('importable')"
  ```
  Expected: prints `importable`. We'll teach pytest about `src/` via `pyproject.toml` in the next step.

- [ ] **Step 0.4: Wire pytest to the `src/` layout**

  Add to `pyproject.toml` under `[tool.pytest.ini_options]`:

  ```toml
  pythonpath = ["src"]
  ```

  After (full block):

  ```toml
  [tool.pytest.ini_options]
  testpaths = ["tests"]
  pythonpath = ["src"]
  addopts = "-q"
  ```

- [ ] **Step 0.5: Sanity-check pytest discovers tests**

  Run:
  ```
  .venv/Scripts/python.exe -m pytest --collect-only
  ```
  Expected: collects 0 tests (we have none yet) without errors. If you see import errors, the `pythonpath` line is wrong.

- [ ] **Step 0.6: Commit the pyproject change**

  ```
  git add pyproject.toml
  git commit -m "chore: configure pytest pythonpath for src/ layout"
  ```

---

## File structure (locked)

| File | Created in | Responsibility |
|---|---|---|
| `src/spotify_project/cache.py` | Task 1 | `FileCache` — file-based JSON cache with TTL |
| `src/spotify_project/models.py` | Task 2 | Frozen dataclasses: `Artist`, `Track`, `Playlist` |
| `src/spotify_project/client.py` | Task 3 | `SpotifyClient` — auth (factory), pagination, artist enrichment |
| `src/spotify_project/analyzer.py` | Task 4 | `Analyzer` ABC + `GenreAnalyzer` + `YearAnalyzer` + `PlaylistAnalyzer` |
| `tests/test_cache.py` | Task 1 | TTL-hit and TTL-miss tests |
| `tests/test_models.py` | Task 2 | Popularity-validation test |
| `tests/test_client.py` | Task 3 | Pagination + artist-enrichment test (mocked spotipy) |
| `tests/test_analyzer.py` | Task 4 | GenreAnalyzer + YearAnalyzer tests on synthetic frames |
| `scripts/create_notebook.py` | Task 5 | One-shot script that generates `01_explore_playlist.ipynb` via `nbformat` |
| `notebooks/01_explore_playlist.ipynb` | Task 5 | The demo notebook itself |

A small detour from the spec: `SpotifyClient` takes the underlying `spotipy.Spotify` as a constructor argument (dependency injection); a `from_env` classmethod factory wraps the OAuth setup. This is purely an implementation choice that makes mocked tests trivial — the public, end-user API is still `SpotifyClient.from_env(cache)`.

---

## Sprint A — MVP (detailed)

### Task 1: `FileCache` (test-first)

**Files:**
- Create: `tests/test_cache.py`
- Create: `src/spotify_project/cache.py`

- [ ] **Step 1.1: Write the first failing test**

  Create `tests/test_cache.py`:

  ```python
  from __future__ import annotations

  import os
  import time
  from pathlib import Path

  from spotify_project.cache import FileCache


  def test_put_then_get_within_ttl_returns_value(tmp_path: Path) -> None:
      """A put followed by a get within the TTL window returns the same value."""
      cache = FileCache(root=tmp_path, ttl_days=7.0)
      cache.put("playlist/abc", {"name": "Test", "id": "abc"})
      assert cache.get("playlist/abc") == {"name": "Test", "id": "abc"}
  ```

- [ ] **Step 1.2: Run the test — expect import failure**

  ```
  .venv/Scripts/python.exe -m pytest tests/test_cache.py -v
  ```
  Expected: `ModuleNotFoundError: No module named 'spotify_project.cache'`. That confirms the test runs and fails for the right reason.

- [ ] **Step 1.3: Implement `FileCache`**

  Create `src/spotify_project/cache.py`:

  ```python
  from __future__ import annotations

  import json
  import time
  from pathlib import Path
  from typing import Any, cast


  class FileCache:
      """File-based cache for Spotify API responses.

      Stores each value as a single JSON file under ``root/<key>.json``.
      A cached entry is fresh iff the file's mtime is within ``ttl_days``.
      Slashes in keys create subdirectories; keep keys filesystem-safe.

      Attributes:
          root: Directory where cache files are stored.
          ttl_days: How long a cached value stays valid, in days.
      """

      def __init__(self, root: Path, ttl_days: float = 7.0) -> None:
          self.root = root
          self.ttl_days = ttl_days
          self.root.mkdir(parents=True, exist_ok=True)

      def get(self, key: str) -> dict[str, Any] | None:
          """Return the cached JSON for ``key`` if present and within TTL.

          Args:
              key: Cache key (e.g. ``"playlist/<id>"``).

          Returns:
              The deserialized JSON, or ``None`` if missing / stale.
          """
          path = self._path_for(key)
          if not path.exists():
              return None
          age_seconds = time.time() - path.stat().st_mtime
          if age_seconds > self.ttl_days * 86_400:
              return None
          return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))

      def put(self, key: str, value: dict[str, Any]) -> None:
          """Write ``value`` to disk under ``key``.

          Args:
              key: Cache key (filesystem-safe path fragment).
              value: JSON-serializable mapping to store.
          """
          path = self._path_for(key)
          path.parent.mkdir(parents=True, exist_ok=True)
          path.write_text(json.dumps(value), encoding="utf-8")

      def clear(self) -> None:
          """Remove every cached entry under ``root``."""
          for f in self.root.rglob("*.json"):
              f.unlink()

      def _path_for(self, key: str) -> Path:
          return self.root / f"{key}.json"
  ```

- [ ] **Step 1.4: Run the test — expect pass**

  ```
  .venv/Scripts/python.exe -m pytest tests/test_cache.py -v
  ```
  Expected: `1 passed`.

- [ ] **Step 1.5: Add the TTL-expiry test**

  Append to `tests/test_cache.py`:

  ```python
  def test_get_after_ttl_returns_none(tmp_path: Path) -> None:
      """A get after the TTL has expired returns None."""
      cache = FileCache(root=tmp_path, ttl_days=1.0)
      cache.put("playlist/abc", {"name": "Test"})
      cache_file = tmp_path / "playlist" / "abc.json"
      two_days_ago = time.time() - 2 * 86_400
      os.utime(cache_file, (two_days_ago, two_days_ago))
      assert cache.get("playlist/abc") is None
  ```

- [ ] **Step 1.6: Run all cache tests**

  ```
  .venv/Scripts/python.exe -m pytest tests/test_cache.py -v
  ```
  Expected: `2 passed`.

- [ ] **Step 1.7: Format and lint**

  ```
  .venv/Scripts/python.exe -m black src/spotify_project/cache.py tests/test_cache.py
  .venv/Scripts/python.exe -m ruff check src/spotify_project/cache.py tests/test_cache.py
  .venv/Scripts/python.exe -m mypy src/spotify_project/cache.py
  ```
  Expected: black reports no changes (or reformats), ruff and mypy clean.

- [ ] **Step 1.8: Commit**

  ```
  git add src/spotify_project/cache.py tests/test_cache.py
  git commit -m "feat(cache): FileCache with TTL-based JSON persistence"
  ```

> **CHECKPOINT 1 — STOP HERE.** Confirm with the user that `FileCache`'s shape matches expectations (key naming, TTL semantics, JSON storage) before moving on. Show: `pytest tests/test_cache.py -v` output and the file diff.

---

### Task 2: `models.py` (Artist, Track, Playlist)

**Files:**
- Create: `tests/test_models.py`
- Create: `src/spotify_project/models.py`

- [ ] **Step 2.1: Write the popularity-validation test**

  Create `tests/test_models.py`:

  ```python
  from __future__ import annotations

  import pytest

  from spotify_project.models import Artist


  def test_artist_popularity_out_of_range_raises() -> None:
      """Artist's __post_init__ rejects popularity outside [0, 100]."""
      with pytest.raises(ValueError, match="popularity"):
          Artist(id="abc", name="Test", genres=(), popularity=101)
  ```

- [ ] **Step 2.2: Run — expect import failure**

  ```
  .venv/Scripts/python.exe -m pytest tests/test_models.py -v
  ```
  Expected: import error on `spotify_project.models`.

- [ ] **Step 2.3: Implement `models.py`**

  Create `src/spotify_project/models.py`:

  ```python
  from __future__ import annotations

  from dataclasses import dataclass
  from datetime import datetime
  from typing import Any


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
              raise ValueError(
                  f"Artist popularity must be in [0, 100], got {self.popularity}"
              )

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
          added_at: When the track was added to the playlist.
              None for Spotify-curated playlists.
          is_local: True for user-uploaded local files.

      Raises:
          ValueError: If popularity is outside [0, 100].
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
              raise ValueError(
                  f"Track popularity must be in [0, 100], got {self.popularity}"
              )

      @property
      def primary_artist(self) -> Artist | None:
          """The first artist on the track, or None for local files."""
          return self.artists[0] if self.artists else None

      @classmethod
      def from_api(
          cls,
          item: dict[str, Any],
          artist_by_id: dict[str, Artist],
      ) -> Track:
          """Parse a playlist-item dict into a Track.

          Args:
              item: A spotipy playlist-item dict (with keys ``track``,
                  ``added_at``, ``is_local``).
              artist_by_id: Lookup of fully-fetched Artist objects, populated
                  by ``SpotifyClient.playlist`` after the batch artist call.

          Returns:
              The constructed Track. Tracks whose ``track.type`` is not
              ``"track"`` (e.g. podcast episodes) should be filtered out by
              the caller before this is called.
          """
          track_data = item["track"]
          is_local = item.get("is_local", False)
          artist_refs = track_data.get("artists", [])
          resolved_artists: tuple[Artist, ...] = tuple(
              artist_by_id[a["id"]]
              for a in artist_refs
              if a.get("id") and a["id"] in artist_by_id
          )
          added_at_raw = item.get("added_at")
          added_at = (
              datetime.fromisoformat(added_at_raw.replace("Z", "+00:00"))
              if added_at_raw
              else None
          )
          return cls(
              id=track_data.get("id"),
              name=track_data.get("name", ""),
              artists=resolved_artists,
              album_name=track_data.get("album", {}).get("name", ""),
              release_date=track_data.get("album", {}).get("release_date"),
              duration_ms=int(track_data.get("duration_ms", 0)),
              popularity=int(track_data.get("popularity", 0)),
              explicit=bool(track_data.get("explicit", False)),
              added_at=added_at,
              is_local=is_local,
          )


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
      def from_api(
          cls,
          data: dict[str, Any],
          tracks: list[Track],
      ) -> Playlist:
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
  ```

- [ ] **Step 2.4: Run the test — expect pass**

  ```
  .venv/Scripts/python.exe -m pytest tests/test_models.py -v
  ```
  Expected: `1 passed`.

- [ ] **Step 2.5: Format, lint, type-check**

  ```
  .venv/Scripts/python.exe -m black src/spotify_project/models.py tests/test_models.py
  .venv/Scripts/python.exe -m ruff check src/spotify_project/models.py tests/test_models.py
  .venv/Scripts/python.exe -m mypy src/spotify_project/models.py
  ```
  Expected: clean.

- [ ] **Step 2.6: Commit**

  ```
  git add src/spotify_project/models.py tests/test_models.py
  git commit -m "feat(models): frozen dataclasses Artist/Track/Playlist with from_api parsers"
  ```

> **CHECKPOINT 2 — STOP HERE.** Confirm with the user that the dataclass shape (especially `Track.artists: tuple[Artist, ...]`, `primary_artist` property, `from_api` signatures) matches expectations.

---

### Task 3: `SpotifyClient` (test-first, with DI)

**Files:**
- Create: `tests/test_client.py`
- Create: `src/spotify_project/client.py`

- [ ] **Step 3.1: Write the pagination + artist-enrichment test**

  Create `tests/test_client.py`:

  ```python
  from __future__ import annotations

  from pathlib import Path
  from unittest.mock import MagicMock

  from spotify_project.cache import FileCache
  from spotify_project.client import SpotifyClient


  def _track_item(idx: int, artist_id: str = "a1") -> dict:
      """Build a spotipy-shaped playlist-item dict for one fake track."""
      return {
          "track": {
              "id": f"t{idx}",
              "name": f"Track {idx}",
              "type": "track",
              "artists": [{"id": artist_id, "name": "Artist 1"}],
              "album": {"name": "Album", "release_date": "2020-01-01"},
              "duration_ms": 200_000,
              "popularity": 50,
              "explicit": False,
          },
          "added_at": "2024-06-01T00:00:00Z",
          "is_local": False,
      }


  def test_playlist_paginates_and_enriches_artists(tmp_path: Path) -> None:
      """Client.playlist concatenates pages and embeds full Artist data per Track."""
      cache = FileCache(root=tmp_path)
      fake_sp = MagicMock()

      fake_sp.playlist.return_value = {
          "id": "pl1",
          "name": "Test PL",
          "owner": {"display_name": "Bennet"},
          "public": True,
          "collaborative": False,
          "description": "",
          "tracks": {
              "items": [_track_item(i) for i in range(100)],
              "next": "next_url",
          },
      }
      fake_sp.next.side_effect = [
          {"items": [_track_item(i) for i in range(100, 150)], "next": None},
      ]
      fake_sp.artists.return_value = {
          "artists": [
              {
                  "id": "a1",
                  "name": "Artist 1",
                  "genres": ["rock", "indie"],
                  "popularity": 70,
              },
          ],
      }

      client = SpotifyClient(sp=fake_sp, cache=cache)
      playlist = client.playlist("pl1")

      assert len(playlist.tracks) == 150
      first = playlist.tracks[0].primary_artist
      assert first is not None
      assert first.name == "Artist 1"
      assert "rock" in first.genres
  ```

- [ ] **Step 3.2: Run the test — expect import failure**

  ```
  .venv/Scripts/python.exe -m pytest tests/test_client.py -v
  ```

- [ ] **Step 3.3: Implement `SpotifyClient`**

  Create `src/spotify_project/client.py`:

  ```python
  from __future__ import annotations

  import logging
  from typing import Any, ClassVar, Iterable

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
          return self.sp.current_user()

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
              it for it in track_items
              if it.get("track") and it["track"].get("type") == "track"
          ]

          artist_ids: set[str] = set()
          for item in track_items:
              for a in item["track"].get("artists", []):
                  if a.get("id"):
                      artist_ids.add(a["id"])

          artist_by_id: dict[str, Artist] = {
              a.id: a
              for a in self.artists(artist_ids, force_refresh=force_refresh)
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
  ```

- [ ] **Step 3.4: Run the test — expect pass**

  ```
  .venv/Scripts/python.exe -m pytest tests/test_client.py -v
  ```
  Expected: `1 passed`.

- [ ] **Step 3.5: Run the full suite to confirm no regression**

  ```
  .venv/Scripts/python.exe -m pytest -q
  ```
  Expected: `4 passed` (2 cache + 1 model + 1 client).

- [ ] **Step 3.6: Format, lint, type-check**

  ```
  .venv/Scripts/python.exe -m black src/spotify_project/client.py tests/test_client.py
  .venv/Scripts/python.exe -m ruff check src/spotify_project/client.py tests/test_client.py
  .venv/Scripts/python.exe -m mypy src/spotify_project/client.py
  ```
  Expected: clean (mypy may warn on spotipy because it has no type stubs; the `ignore_missing_imports = true` in `pyproject.toml` handles that).

- [ ] **Step 3.7: Commit**

  ```
  git add src/spotify_project/client.py tests/test_client.py
  git commit -m "feat(client): SpotifyClient with DI, pagination, and artist enrichment"
  ```

> **CHECKPOINT 3 — STOP HERE.** Confirm with the user that the client's two-phase fetch and DI-friendly constructor look right. Show: `pytest -q` output and the file diff.

---

### Task 4: `analyzer.py` — ABC + GenreAnalyzer + YearAnalyzer + PlaylistAnalyzer

**Files:**
- Create: `tests/test_analyzer.py`
- Create: `src/spotify_project/analyzer.py`

- [ ] **Step 4.1: Write tests for both analyzers**

  Create `tests/test_analyzer.py`:

  ```python
  from __future__ import annotations

  import pandas as pd

  from spotify_project.analyzer import GenreAnalyzer, YearAnalyzer


  def _frame(rows: list[dict]) -> pd.DataFrame:
      """Build a DataFrame matching the relevant subset of the spec's track schema."""
      return pd.DataFrame(rows)


  def test_genre_analyzer_returns_top_n_by_count() -> None:
      """GenreAnalyzer counts genre frequency across the playlist."""
      df = _frame([
          {"track_id": "1", "genres": ["rock", "indie"]},
          {"track_id": "2", "genres": ["rock"]},
          {"track_id": "3", "genres": ["pop"]},
          {"track_id": "4", "genres": []},
      ])
      summary = GenreAnalyzer(top_n=10).analyze(df)
      counts = dict(zip(summary["genre"], summary["count"]))
      assert counts["rock"] == 2
      assert counts["indie"] == 1
      assert counts["pop"] == 1


  def test_year_analyzer_extracts_release_year() -> None:
      """YearAnalyzer counts tracks per release year, including year-only dates."""
      df = _frame([
          {"track_id": "1", "release_date": "2020-01-01"},
          {"track_id": "2", "release_date": "2020-06-01"},
          {"track_id": "3", "release_date": "1979"},
          {"track_id": "4", "release_date": None},
      ])
      summary = YearAnalyzer().analyze(df)
      counts = dict(zip(summary["year"], summary["count"]))
      assert counts[2020] == 2
      assert counts[1979] == 1
  ```

- [ ] **Step 4.2: Run the tests — expect import failure**

  ```
  .venv/Scripts/python.exe -m pytest tests/test_analyzer.py -v
  ```

- [ ] **Step 4.3: Implement `analyzer.py`**

  Create `src/spotify_project/analyzer.py`:

  ```python
  from __future__ import annotations

  from abc import ABC, abstractmethod
  from pathlib import Path
  from typing import ClassVar

  import pandas as pd
  from matplotlib.axes import Axes
  from matplotlib.figure import Figure

  from .models import Playlist


  class Analyzer(ABC):
      """Abstract analyzer over a track DataFrame.

      Concrete subclasses override ``analyze`` (returns a summary DataFrame)
      and ``plot`` (renders the result onto a Matplotlib Axes provided by
      the caller).

      Attributes:
          title: Short title; appears as the plot's title.
      """

      title: ClassVar[str] = ""

      @abstractmethod
      def analyze(self, df: pd.DataFrame) -> pd.DataFrame:
          """Return a summary DataFrame derived from the track-level df."""

      @abstractmethod
      def plot(self, ax: Axes, summary: pd.DataFrame) -> None:
          """Render ``summary`` onto ``ax``. No figure-level mutation."""


  class GenreAnalyzer(Analyzer):
      """Top genres by track count, with empty / sparse data handled.

      Args:
          top_n: How many genres to return; default 15.
      """

      title = "Top Genres"

      def __init__(self, top_n: int = 15) -> None:
          self.top_n = top_n

      def analyze(self, df: pd.DataFrame) -> pd.DataFrame:
          if df.empty:
              return pd.DataFrame({"genre": [], "count": []})
          exploded = df.explode("genres").dropna(subset=["genres"])
          if exploded.empty:
              return pd.DataFrame({"genre": [], "count": []})
          return (
              exploded.groupby("genres", as_index=False)
              .size()
              .rename(columns={"genres": "genre", "size": "count"})
              .sort_values("count", ascending=False)
              .head(self.top_n)
              .reset_index(drop=True)
          )

      def plot(self, ax: Axes, summary: pd.DataFrame) -> None:
          if summary.empty:
              ax.text(0.5, 0.5, "No genre data", ha="center", va="center")
              ax.set_title(self.title)
              return
          ax.barh(summary["genre"], summary["count"])
          ax.invert_yaxis()
          ax.set_xlabel("Track count")
          ax.set_title(self.title)


  class YearAnalyzer(Analyzer):
      """Release-year distribution, robust to year-only release_date strings."""

      title = "Release Year Distribution"

      def analyze(self, df: pd.DataFrame) -> pd.DataFrame:
          if df.empty:
              return pd.DataFrame({"year": [], "count": []})
          years = (
              pd.to_numeric(df["release_date"].str.slice(0, 4), errors="coerce")
              .dropna()
              .astype(int)
          )
          if years.empty:
              return pd.DataFrame({"year": [], "count": []})
          return (
              years.value_counts()
              .sort_index()
              .rename_axis("year")
              .reset_index(name="count")
          )

      def plot(self, ax: Axes, summary: pd.DataFrame) -> None:
          if summary.empty:
              ax.text(0.5, 0.5, "No year data", ha="center", va="center")
              ax.set_title(self.title)
              return
          ax.bar(summary["year"], summary["count"])
          ax.set_xlabel("Year")
          ax.set_ylabel("Track count")
          ax.set_title(self.title)


  class PlaylistAnalyzer:
      """Orchestrator: holds a track DataFrame and runs registered Analyzers.

      Attributes:
          df: The track-level DataFrame (one row per track).
          analyzers: Registered Analyzer instances; default is all built-in.
      """

      def __init__(
          self,
          df: pd.DataFrame,
          analyzers: list[Analyzer] | None = None,
      ) -> None:
          self.df = df
          self.analyzers = analyzers if analyzers is not None else [
              GenreAnalyzer(),
              YearAnalyzer(),
          ]

      @classmethod
      def from_playlist(
          cls,
          playlist: Playlist,
          analyzers: list[Analyzer] | None = None,
      ) -> PlaylistAnalyzer:
          """Build a PlaylistAnalyzer from a Playlist by flattening tracks.

          Each Track's ``primary_artist`` is read for the ``primary_artist_*``
          and ``genres`` columns. Local files (``is_local=True``) yield
          empty genres and ``None`` for artist IDs.

          Args:
              playlist: Source Playlist with full Track + Artist data.
              analyzers: Optional Analyzer list; defaults to the built-in set.

          Returns:
              Ready-to-use PlaylistAnalyzer.
          """
          rows: list[dict] = []
          for t in playlist.tracks:
              primary = t.primary_artist
              release_date = t.release_date
              release_year: int | None
              if release_date and release_date[:4].isdigit():
                  release_year = int(release_date[:4])
              else:
                  release_year = None
              rows.append({
                  "track_id": t.id,
                  "name": t.name,
                  "primary_artist_id": primary.id if primary else None,
                  "primary_artist_name": primary.name if primary else "",
                  "all_artists": " | ".join(a.name for a in t.artists),
                  "album_name": t.album_name,
                  "release_date": release_date,
                  "release_year": release_year,
                  "duration_ms": t.duration_ms,
                  "duration_min": t.duration_ms / 60_000,
                  "popularity": t.popularity,
                  "explicit": t.explicit,
                  "added_at": t.added_at,
                  "is_local": t.is_local,
                  "genres": list(primary.genres) if primary else [],
              })
          df = pd.DataFrame(rows)
          return cls(df=df, analyzers=analyzers)

      def run_all(self) -> dict[str, pd.DataFrame]:
          """Run every registered Analyzer; returns ``{title: summary_df}``."""
          return {a.title: a.analyze(self.df) for a in self.analyzers}

      def plot_all(self, fig: Figure) -> None:
          """Lay out one subplot per analyzer in a vertical stack on ``fig``."""
          n = len(self.analyzers)
          axes = fig.subplots(n, 1)
          axes_list = [axes] if n == 1 else list(axes)
          for ax, analyzer in zip(axes_list, self.analyzers):
              summary = analyzer.analyze(self.df)
              analyzer.plot(ax, summary)
          fig.tight_layout()

      def to_parquet(self, path: Path) -> None:
          """Write the underlying DataFrame to parquet for offline use."""
          self.df.to_parquet(path)
  ```

- [ ] **Step 4.4: Run the analyzer tests — expect pass**

  ```
  .venv/Scripts/python.exe -m pytest tests/test_analyzer.py -v
  ```
  Expected: `2 passed`.

- [ ] **Step 4.5: Run the full suite**

  ```
  .venv/Scripts/python.exe -m pytest -q
  ```
  Expected: `6 passed`.

- [ ] **Step 4.6: Format, lint, type-check the whole `src/`**

  ```
  .venv/Scripts/python.exe -m black src/ tests/
  .venv/Scripts/python.exe -m ruff check src/ tests/
  .venv/Scripts/python.exe -m mypy src/
  ```
  Expected: clean.

- [ ] **Step 4.7: Commit**

  ```
  git add src/spotify_project/analyzer.py tests/test_analyzer.py
  git commit -m "feat(analyzer): Analyzer ABC + GenreAnalyzer + YearAnalyzer + PlaylistAnalyzer"
  ```

> **CHECKPOINT 4 — STOP HERE.** Confirm with the user that the analyzer hierarchy and `PlaylistAnalyzer.from_playlist` flattening look right. The library is now feature-complete for Sprint A; the notebook is the last step.

---

### Task 5: Demo notebook

**Files:**
- Create: `scripts/create_notebook.py`
- Create: `notebooks/01_explore_playlist.ipynb` (generated by the script above)

We use a small one-shot Python helper to generate the notebook deterministically — that way the cells are version-controllable as Python source rather than as messy JSON.

- [ ] **Step 5.1: Create the notebook-build script**

  Create `scripts/create_notebook.py`:

  ```python
  """One-shot generator for notebooks/01_explore_playlist.ipynb.

  Run after editing the cell content here:

      .venv/Scripts/python.exe scripts/create_notebook.py
  """

  from __future__ import annotations

  from pathlib import Path

  import nbformat as nbf

  CELLS = [
      ("md", "# Spotify Playlist Explorer\n\n"
             "Phase 1 demo: authenticate, pick a playlist, run "
             "Genre + Year analyses, render plots."),
      ("code", (
          "from pathlib import Path\n"
          "from dotenv import load_dotenv\n"
          "import matplotlib.pyplot as plt\n"
          "import seaborn as sns\n"
          "from spotify_project.cache import FileCache\n"
          "from spotify_project.client import SpotifyClient\n"
          "from spotify_project.analyzer import PlaylistAnalyzer\n\n"
          "load_dotenv()\n"
          "sns.set_theme(style='whitegrid')\n"
          "cache = FileCache(root=Path('.cache') / 'api')\n"
          "client = SpotifyClient.from_env(cache=cache)"
      )),
      ("md", "## 1. Confirm authentication"),
      ("code", (
          "user = client.current_user()\n"
          "print(f\"Hello, {user['display_name']} ({user['id']})\")"
      )),
      ("md", "## 2. List your playlists"),
      ("code", (
          "import pandas as pd\n"
          "playlists = client.user_playlists()\n"
          "summary = pd.DataFrame([\n"
          "    {'id': p['id'], 'name': p['name'], 'tracks': p['tracks']['total']}\n"
          "    for p in playlists\n"
          "])\n"
          "summary.head(20)"
      )),
      ("md", "## 3. Pick a playlist and fetch it\n\n"
             "Replace `PLAYLIST_ID` below with one of the IDs from the table above."),
      ("code", (
          "PLAYLIST_ID = 'REPLACE_WITH_AN_ID_FROM_THE_TABLE_ABOVE'\n"
          "playlist = client.playlist(PLAYLIST_ID)\n"
          "print(f\"{playlist.name}: {len(playlist.tracks)} tracks\")"
      )),
      ("md", "## 4. Build the PlaylistAnalyzer and run analyses"),
      ("code", (
          "analyzer = PlaylistAnalyzer.from_playlist(playlist)\n"
          "results = analyzer.run_all()\n"
          "for title, df in results.items():\n"
          "    print(title)\n"
          "    print(df.head(), end='\\n\\n')"
      )),
      ("md", "## 5. Render plots"),
      ("code", (
          "fig = plt.figure(figsize=(10, 8))\n"
          "analyzer.plot_all(fig)\n"
          "plt.show()"
      )),
  ]


  def main() -> None:
      nb = nbf.v4.new_notebook()
      nb.cells = [
          nbf.v4.new_markdown_cell(content) if kind == "md"
          else nbf.v4.new_code_cell(content)
          for kind, content in CELLS
      ]
      out_path = Path("notebooks") / "01_explore_playlist.ipynb"
      out_path.parent.mkdir(parents=True, exist_ok=True)
      nbf.write(nb, out_path)
      print(f"wrote {out_path}")


  if __name__ == "__main__":
      main()
  ```

- [ ] **Step 5.2: Run the script to generate the notebook**

  ```
  .venv/Scripts/python.exe scripts/create_notebook.py
  ```
  Expected: prints `wrote notebooks/01_explore_playlist.ipynb`.

- [ ] **Step 5.3: Verify the notebook opens**

  ```
  .venv/Scripts/python.exe -c "import nbformat; nb = nbformat.read('notebooks/01_explore_playlist.ipynb', as_version=4); print(f'cells: {len(nb.cells)}')"
  ```
  Expected: `cells: 11`.

- [ ] **Step 5.4: Smoke-test the import path**

  ```
  .venv/Scripts/python.exe -c "from spotify_project.cache import FileCache; from spotify_project.client import SpotifyClient; from spotify_project.analyzer import PlaylistAnalyzer; print('imports ok')"
  ```
  Expected: `imports ok`. If it fails, the package isn't on the path; sanity check `pyproject.toml`'s `pythonpath`.

- [ ] **Step 5.5: User runs the notebook end-to-end**

  > **STOP HERE.** This step is yours, not the agent's: copy `.env.example` → `.env`, fill in your real Spotify Developer Dashboard credentials, then open the notebook in Jupyter / VS Code:
  >
  > ```
  > .venv/Scripts/python.exe -m jupyter notebook notebooks/01_explore_playlist.ipynb
  > ```
  >
  > Walk through the cells. Replace the placeholder `PLAYLIST_ID` in cell 6 with one of your real playlist IDs from cell 4's output. Confirm two plots appear (Genre + Year).
  >
  > If anything errors, paste the traceback back to the agent — that's how we learn the spec misses an edge case.

- [ ] **Step 5.6: Commit (once the notebook ran cleanly for you)**

  Strip outputs from the notebook before committing — they bloat git history and embed personal data:

  ```
  .venv/Scripts/python.exe -m jupyter nbconvert --clear-output --inplace notebooks/01_explore_playlist.ipynb
  git add scripts/create_notebook.py notebooks/01_explore_playlist.ipynb
  git commit -m "feat(notebook): demo notebook for Phase 1 — auth, list, fetch, analyze, plot"
  ```

> **🎉 SPRINT A COMPLETE.** Project is now in a submittable state — passes the rubric's minimum bar on every criterion. Take a breath, walk away, come back fresh. Sprint B starts when you're ready.

---

## Sprint B — outline (target feature set)

Detailed plan to be written *after Sprint A is committed and reviewed* — the lessons from Sprint A (what was harder than expected, what the user wants more or less of) feed into Sprint B's task ordering.

**Tasks:**

- **B.1 ArtistAnalyzer** — top artists by track count *and* by total minutes. Test on synthetic frame; same shape as GenreAnalyzer.
- **B.2 PopularityAnalyzer** — popularity histogram with mean line. Tests: empty df, all-zero df, normal df.
- **B.3 DurationAnalyzer** — duration histogram + total-runtime annotation. Test: empty df, single track, mixed durations.
- **B.4 TimelineAnalyzer** — `added_at` over time. Falls back to `release_date` for Spotify-curated playlists. Tests: all-NaT timeline, fallback path.
- **B.5 Parquet export** — wire `analyzer.to_parquet(path)` into the notebook's last cell as an opt-in. Test that round-trips through pandas.
- **B.6 Plot polish** — consistent seaborn theming, axis labels, legends, sane figure sizes. No tests — visual inspection.
- **B.7 Notebook update** — regenerate `notebooks/01_explore_playlist.ipynb` with the four new analyzers in the `plot_all` grid, plus the parquet-export cell.

**Test-count target:** ~9 total (3 from Sprint A + 1-2 per new analyzer + 1 parquet round-trip).

**Open questions to answer at the start of Sprint B:**

- Decade buckets in YearAnalyzer? (Currently plots per-year — might be noisy for 50-year playlists.)
- Should ArtistAnalyzer have a primary-vs-all-artists toggle?

---

## Sprint C — outline (polish)

Only if Sprint B lands with time to spare. None of these affect the rubric — they affect how nice the project is to demo and use.

- **C.1 Subtitle annotations** — each plot's title gets a coverage / completeness sub-line ("Top genres — 47% of tracks have ≥1 tag").
- **C.2 Coverage ratios visualised** — bottom of GenreAnalyzer's chart shows the % missing as a separate band.
- **C.3 Notebook narrative** — markdown cells between code cells explaining each analysis in plain language. Critical for the oral exam — the grader can read along.
- **C.4 README install/usage section** — fill in the `## How to run` section with the actual concrete commands now that we know what they are.
- **C.5 Sweep tests** — fill in any test gaps spotted during Sprints A/B.

---

## Self-review

Done as the final pass before handing back to the user.

**Spec coverage** (each spec section → task that implements it):

- §1 Goal and scope → all of Sprint A
- §2 Architecture overview → file structure section above
- §3.1 `models.py` → Task 2
- §3.2 `cache.py` → Task 1
- §3.3 `client.py` → Task 3
- §3.4 `analyzer.py` → Task 4 (ABC + GenreAnalyzer + YearAnalyzer + PlaylistAnalyzer); Sprint B for the other 4 analyzers
- §4 DataFrame schema → Task 4 (`from_playlist` flattening)
- §5 Auth and configuration → Task 5 (notebook cells + Step 5.5 user instructions)
- §6 Edge cases — `is_local`, empty playlists, missing genres, year-only dates → handled by Tasks 2 & 4 implementations and asserted by the test suite
- §7 Testing strategy → Tasks 1, 2, 3, 4 each include their tests; ~6 tests at end of Sprint A (matches "≥3 minimum")
- §8 Build order → Sprints A / B / C above
- §9 Out of scope → no tasks (correctly)
- §10 Policies (no untestable code, docstring style) → enforced throughout

**Placeholder scan:** No `TBD` / `TODO` / "fill in later" in any code or test step. The Sprint B/C *outlines* deliberately leave room (we'll plan them concretely after Sprint A); that's a feature, not a placeholder.

**Type / signature consistency:** `Track.from_api(item, artist_by_id)` matches its caller in `client.py`. `Analyzer.analyze` returns `pd.DataFrame` everywhere. `PlaylistAnalyzer.from_playlist(playlist, analyzers=None)` matches both the spec amendment and `notebook` usage.

---

## Execution handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-30-spotify-phase1-plan.md`.

**Two execution options:**

1. **Subagent-Driven (recommended)** — fresh subagent per task, two-stage review between tasks, fast iteration. Good when you want me to drive while you focus on green-lighting at checkpoints.
2. **Inline Execution** — execute tasks in this session, batch checkpoints for review. Good when you want to be in the room while it happens, even if it's slower.

Which approach?
