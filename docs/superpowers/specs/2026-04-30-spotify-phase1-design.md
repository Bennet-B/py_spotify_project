# py_spotify_project — Phase 1 Design Spec

**Date:** 2026-04-30
**Project:** INFPROG2 FS26 semester project (ZHAW), 20% of grade
**Status:** Draft, pending user approval

---

## 1. Goal and scope

A Jupyter notebook that authenticates as a Spotify user and analyzes one of their playlists from multiple analytical angles. The notebook is a thin demo over a small reusable Python library in `src/spotify_project/`.

**In scope (Phase 1):**

- OAuth via spotipy (Authorization Code flow)
- Fetch one playlist, all its tracks, and the artists for genre lookup
- Transform to a `pandas.DataFrame` with one row per track
- Run 5–6 analyses, each as an `Analyzer` subclass
- Render plots in the notebook
- File-based API cache with 7-day default TTL
- Unit tests: 3 minimum (rubric floor, hit at end of Sprint A); ~9 by end of Sprint B
- Optional parquet export of the analyzed DataFrame

**Out of scope (Phase 2 or never):**

- Cross-playlist comparison
- Playlist mutation (split / merge / dedupe / re-sort)
- Web UI (Streamlit vs FastAPI — undecided, Phase 2)
- Recommendations, mood-map, audio features, related artists — *deprecated by Spotify in Nov 2024 for new apps; never implemented*

---

## 2. Architecture overview

```
Spotify Web API
    │  raw JSON
    ▼
FileCache (.cache/api/*.json, 7-day TTL)
    │  cached JSON
    ▼
SpotifyClient — pagination, retries, parses to ↓
    │
    ▼
@dataclass(frozen) Track / Playlist / Artist
    │  flatten via PlaylistAnalyzer.from_playlist()
    ▼
pandas.DataFrame (one row per track, schema in §4)
    │
    ├──► Analyzer subclasses ──► matplotlib/seaborn plots
    │       (genre, year, artist, popularity, duration, timeline)
    │
    └──► to_parquet(data/<playlist>.parquet)   [optional]
```

**Modules:**

- `src/spotify_project/models.py` — Track, Playlist, Artist (frozen dataclasses)
- `src/spotify_project/cache.py` — FileCache class
- `src/spotify_project/client.py` — SpotifyClient class
- `src/spotify_project/analyzer.py` — Analyzer ABC, concrete subclasses, PlaylistAnalyzer orchestrator
- `notebooks/01_explore_playlist.ipynb` — demo notebook
- `tests/` — pytest

Class count: 3 dataclasses + 1 cache + 1 client + 1 ABC + 6 analyzer subclasses + 1 orchestrator = **13 classes**. Inheritance is real (Analyzer hierarchy with overridden `analyze` and `plot`). Composition is real (SpotifyClient holds FileCache; PlaylistAnalyzer holds DataFrame and a list of Analyzers).

---

## 3. Module specs

### 3.1 `models.py`

Three frozen dataclasses, no inheritance, plain data carriers. Each has a `from_api` classmethod that parses a spotipy dict; `__post_init__` enforces invariants only where bugs can plausibly occur (e.g. popularity range).

```python
@dataclass(slots=True, frozen=True)
class Artist:
    """A Spotify artist with their genres and popularity."""
    id: str
    name: str
    genres: tuple[str, ...]      # tuple, not list, for hashability
    popularity: int               # 0-100

    def __post_init__(self) -> None:
        if not 0 <= self.popularity <= 100:
            raise ValueError(f"popularity {self.popularity} outside [0,100]")

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "Artist": ...


@dataclass(slots=True, frozen=True)
class Track:
    """A single track in a Spotify playlist.

    Holds full `Artist` references (not just IDs) — domain-faithful object
    graph, traversable as `track.primary_artist.genres`. Local files have
    `artists = ()` because Spotify gives us no artist API data for them.
    """
    id: str | None                   # None for local files
    name: str
    artists: tuple[Artist, ...]      # Full Artist refs with genres. () for local files.
    album_name: str
    release_date: str | None         # ISO date string; may be year-only
    duration_ms: int
    popularity: int                  # 0-100
    explicit: bool
    added_at: datetime | None        # None for Spotify-curated playlists
    is_local: bool

    def __post_init__(self) -> None:
        if not 0 <= self.popularity <= 100:
            raise ValueError(f"popularity {self.popularity} outside [0,100]")

    @property
    def primary_artist(self) -> Artist | None:
        """The first artist on the track, or None for local files."""
        return self.artists[0] if self.artists else None

    @classmethod
    def from_api(
        cls,
        item: dict[str, Any],
        artist_by_id: dict[str, Artist],
    ) -> "Track":
        """Parse a playlist-item dict, looking up full Artists by ID.

        `artist_by_id` is supplied by SpotifyClient.playlist after batch-
        fetching all unique artist IDs in a single phase.
        """


@dataclass(slots=True, frozen=True)
class Playlist:
    """A Spotify playlist with metadata and its tracks."""
    id: str
    name: str
    owner_display_name: str
    public: bool
    collaborative: bool
    description: str
    tracks: tuple[Track, ...]

    @classmethod
    def from_api(cls, data: dict[str, Any], tracks: list[Track]) -> "Playlist": ...
```

Genres are NOT on `Track`; they live on `Artist` and are joined into the DataFrame at flattening time.

### 3.2 `cache.py`

A simple file-based cache with TTL; one JSON file per cache key.

```python
class FileCache:
    """File-based cache for Spotify API responses, keyed by stable URL fragments.

    JSON serialization, configurable TTL (default 7 days). `force_refresh`
    bypasses lookup and always overwrites.
    """

    def __init__(self, root: Path, ttl_days: float = 7.0) -> None: ...

    def get(self, key: str) -> dict[str, Any] | None:
        """Return cached JSON for `key` if present and within TTL; else None."""

    def put(self, key: str, value: dict[str, Any]) -> None:
        """Write `value` to disk under `key`."""

    def clear(self) -> None:
        """Remove all cached entries."""
```

Cache keys use a stable form like `playlist/<id>` or `artists/<comma-joined-ids>`. TTL is checked via file mtime. Keys containing `..` segments or that resolve outside the cache root are rejected with `ValueError` — callers are responsible for constructing safe keys, but the cache enforces the contract defensively.

### 3.3 `client.py`

```python
class SpotifyClient:
    """Authenticated Spotify Web API client with caching, pagination, and retry.

    Wraps spotipy. Auth uses Authorization Code flow with credentials read
    from environment (.env or OS vars). Token cached locally by spotipy in
    `.cache`. All read methods consult the FileCache first; cache hits skip
    the API.
    """

    DEFAULT_SCOPES: ClassVar[list[str]] = [
        "user-read-private",
        "playlist-read-private",
        "playlist-read-collaborative",
        "user-library-read",
        "user-top-read",
    ]

    def __init__(
        self,
        cache: FileCache,
        scopes: list[str] | None = None,
    ) -> None: ...

    def current_user(self) -> dict[str, Any]:
        """Return the authenticated user's profile dict (id, display_name, country, ...)."""

    def user_playlists(self) -> list[dict[str, Any]]:
        """List the authenticated user's playlists (id + name + count, not full tracks)."""

    def playlist(
        self,
        playlist_id: str,
        *,
        force_refresh: bool = False,
    ) -> Playlist:
        """Fetch a playlist by ID, fully enriched.

        Two-phase: (1) fetch playlist metadata + paginated track items
        (artist IDs only); (2) collect unique artist IDs across all tracks
        and batch-fetch them. Each Track is constructed with full `Artist`
        objects embedded (not just IDs), so callers can write
        `track.primary_artist.genres` directly.
        """

    def artists(
        self,
        artist_ids: Iterable[str],
        *,
        force_refresh: bool = False,
    ) -> list[Artist]:
        """Fetch a batch of artists; respects Spotify's 50-IDs-per-call cap.

        Used internally by `playlist` to enrich track artists with genres,
        and exposed publicly for callers who want artist data on its own.
        """
```

**Pagination:** `playlist` internally calls `sp.next(results)` until exhausted (typically up to 100 items per page). 5000-track playlists yield 50 pages.

**Retry / rate-limit:** spotipy's session handles 429 with `Retry-After` and 5xx with exponential backoff by default. We configure `max_retries` and `backoff_factor` explicitly when constructing the session.

**No deprecated endpoints:** No `audio_features`, `recommendations`, `related_artists`, or any other endpoint that returns 403 for new apps. See README §"What this means for the codebase".

### 3.4 `analyzer.py`

```python
class Analyzer(ABC):
    """Abstract analyzer over a track DataFrame.

    Subclasses implement `analyze` (compute summary DataFrame) and `plot`
    (render the result onto a Matplotlib Axes provided by the caller).
    """

    title: ClassVar[str]   # short title for plot

    @abstractmethod
    def analyze(self, df: pd.DataFrame) -> pd.DataFrame:
        """Return a summary DataFrame derived from the track-level df."""

    @abstractmethod
    def plot(self, ax: Axes, summary: pd.DataFrame) -> None:
        """Render `summary` onto `ax`. No figure-level mutation."""


class GenreAnalyzer(Analyzer):
    """Top genres by track count (genres come from primary artist).

    Reports both top-N genres AND coverage ratio (% of tracks with ≥1 genre tag),
    because Spotify genre data is sparse for smaller artists.
    """
    title = "Top Genres"

class YearAnalyzer(Analyzer):
    """Release-year histogram. Buckets by decade for visual clarity."""
    title = "Release Year Distribution"

class ArtistAnalyzer(Analyzer):
    """Top artists by track count and total duration."""
    title = "Top Artists"

class PopularityAnalyzer(Analyzer):
    """Popularity score distribution with mean line."""
    title = "Popularity"

class DurationAnalyzer(Analyzer):
    """Track duration histogram and total runtime."""
    title = "Duration"

class TimelineAnalyzer(Analyzer):
    """`added_at` timestamps over time — when did this playlist grow?"""
    title = "Added-at Timeline"


class PlaylistAnalyzer:
    """Orchestrator: holds a track DataFrame and runs registered Analyzers.

    The DataFrame schema is defined in §4. Each Analyzer is independent;
    `run_all` returns {Analyzer.title: summary_df} and `plot_all(fig)`
    draws each analyzer onto its own subplot in a grid.
    """

    def __init__(self, df: pd.DataFrame, analyzers: list[Analyzer]) -> None: ...

    @classmethod
    def from_playlist(
        cls,
        playlist: Playlist,
        analyzers: list[Analyzer] | None = None,
    ) -> "PlaylistAnalyzer":
        """Build the track DataFrame from a Playlist (artists already embedded).

        Flattens `track.primary_artist.genres` into the DataFrame's `genres`
        column, etc. If `analyzers` is None, registers the default set (all
        six concrete subclasses above).
        """

    def run_all(self) -> dict[str, pd.DataFrame]: ...

    def plot_all(self, fig: Figure) -> None:
        """Lay out a subplot grid sized to the analyzer count."""

    def to_parquet(self, path: Path) -> None: ...
```

The polymorphism is exercised on every notebook run: `for a in self._analyzers: result = a.analyze(self._df); a.plot(axes[i], result)`. Adding a 7th analysis (e.g. `ExplicitRatioAnalyzer`) is *one new subclass*, registered via the constructor — no other code changes.

---

## 4. DataFrame schema

One row per track. Defined columns:

| Column | dtype | Notes |
|---|---|---|
| `track_id` | string\|NA | None for local files |
| `name` | string | Track name |
| `primary_artist_id` | string\|NA | None for local files |
| `primary_artist_name` | string | First artist |
| `all_artists` | string | Pipe-joined: `"Artist A | Artist B"` |
| `album_name` | string | |
| `release_date` | string\|NA | ISO date or year-only string from Spotify |
| `release_year` | Int64 | Nullable int extracted from release_date |
| `duration_ms` | int64 | |
| `duration_min` | float64 | duration_ms / 60_000, derived |
| `popularity` | Int64 | 0–100 |
| `explicit` | boolean | Nullable bool |
| `added_at` | datetime64[ns, UTC] | NaT for Spotify-curated playlists |
| `is_local` | boolean | |
| `genres` | object (list[str]) | From primary artist; empty list if untagged |

Genre-related analyzers use `df.explode("genres")` for groupby aggregation.

---

## 5. Auth and configuration

Credentials read by spotipy from environment variables:

- `SPOTIPY_CLIENT_ID`
- `SPOTIPY_CLIENT_SECRET`
- `SPOTIPY_REDIRECT_URI`

Resolution order:

1. OS env vars (set via `setx` on Windows, persistent in HKCU, UserSecrets-style)
2. `.env` file in repo root, loaded via `python-dotenv` at notebook start

`.env` is gitignored. `.env.example` (committed) documents the keys.

Redirect URI: `http://127.0.0.1:8888/callback`. Must be registered exactly in the Spotify Developer Dashboard.

OAuth token cached locally by spotipy in `.cache` (gitignored).

---

## 6. Edge cases the code must survive without crashing

- **Empty playlist (0 tracks)** → empty DataFrame; analyzers return empty summaries; plots show "no data" annotation
- **Local files (`is_local=True`)** → no Spotify ID, no genres, partial data; analyzers that can't use them filter and report
- **Artists with no genres assigned** → `genres = []`; GenreAnalyzer reports both top-N AND coverage ratio
- **Tracks with `added_at = None`** (Spotify-curated playlists) → TimelineAnalyzer falls back to release_date or skips with annotation
- **Episodes (podcasts) accidentally in a playlist** → filtered out at parse time with a logged warning; only `track`-type items reach the DataFrame
- **Year-only release_date** ("1979", no month/day) → parsed to year 1979, month/day NaT
- **Playlist with all genres empty** → GenreAnalyzer plots an "No genre data available" annotation rather than an empty bar chart
- **Network failure during fetch** → spotipy retries 429/5xx; unrecoverable failures propagate as exceptions (notebook will error visibly, not silently)

---

## 7. Testing strategy

Tests use pytest, run with `.venv/Scripts/python.exe -m pytest`.

**`tests/test_analyzer.py`** (~5 tests): each Analyzer fed small synthetic DataFrames. Asserts:

- Empty DataFrame returns empty summary, doesn't crash
- Single-row DataFrame returns expected single-row summary
- Multi-row with mixed genres returns correct top-N
- GenreAnalyzer handles entirely missing genres gracefully (returns empty + 0% coverage)
- YearAnalyzer handles year-only release_date strings

**`tests/test_client.py`** (~2 tests): SpotifyClient with `unittest.mock.patch` on the spotipy module:

- `playlist` paginates correctly across multiple pages of mocked results
- `artists` batches IDs in groups of 50

**`tests/test_cache.py`** (~2 tests):

- `put` then `get` within TTL returns the value
- `get` after TTL returns None (uses monkeypatched `time.time` or `os.utime` to age the file)

Total ~9 tests; rubric requires ≥3.

---

## 8. Build order

After every sprint the project should be in a submittable state — never half-implemented modules.

**Sprint A (MVP — submittable on its own, ~300 LOC):**

1. `cache.py` — smallest, easiest to test
2. `models.py` — dataclasses + `from_api` parsers
3. `client.py` — auth, `current_user`, `playlist`, `artists`
4. `analyzer.py`: `Analyzer` ABC + `GenreAnalyzer` + `YearAnalyzer` + `PlaylistAnalyzer` orchestrator
5. 3 unit tests (one analyzer, one client, one cache)
6. `01_explore_playlist.ipynb` — auth, fetch, 2–3 plots

**Sprint B (rich feature set — target):**

7. `ArtistAnalyzer`, `PopularityAnalyzer`, `DurationAnalyzer`, `TimelineAnalyzer`
8. Parquet export
9. Polish all plots (seaborn theming, axis labels, legends, titles)
10. Expand tests to ~9 total

**Sprint C (polish — if time allows):**

11. Subtitle annotations on plots, coverage ratios visible in the chart
12. Notebook narrative — markdown cells explaining each analysis section
13. README install/usage section filled in with concrete commands

---

## 9. Out of scope (Phase 2 or never)

- Playlist mutation (split / merge / dedupe / re-sort) — Phase 2
- Cross-playlist comparison — Phase 2
- Web UI (Streamlit vs FastAPI) — Phase 2, choice deferred
- Recommendations, mood-map, audio features, related artists — *deprecated by Spotify, will never be implemented*
- Untrusted-input validation — there is no untrusted input source in this project

---

## 10. Policies and constraints (inherited)

From project memory and feedback:

- **No untestable code:** no try/catch around dead endpoints, no flags for unreachable paths. Limitations are documented in README, not encoded as dead code branches.
- **Comment / docstring style:** C#-XML-doc-style docstrings on classes and public methods (Google-style for parameters / returns / raises sections). Sparse inline `#` comments only where the *why* is non-obvious.
- **Plan-first workflow:** each new module gets a short brainstorm/spec round before code; large pivots get explicit user sign-off.
- **Type hints everywhere except in notebook cells** (per global Python style rule).
- **PEP 8 / Black 88-col**; consistent naming (`snake_case` / `PascalCase` / `UPPER_SNAKE_CASE`).
- **Library choices that were considered and rejected:**
  - `pydantic` — rejected; data source is consistent and trusted, no untrusted input. `__post_init__` validation is sufficient where validation is justified.
  - `keyring` — rejected; overkill for single-user course project; `.env` + OS env vars cover it.
  - `Cookiecutter` scaffolding — rejected; generates code we'd have to defend in oral exam.

---

## 11. Open / deferred items

- **Seaborn theme:** start with `seaborn-v0_8-whitegrid`; trivial to swap.
- **Phase 2 web UI framework:** Streamlit vs FastAPI — decide after Phase 1 ships.
- **Number of tracks per playlist for the demo:** TBD by the user during their first run.
