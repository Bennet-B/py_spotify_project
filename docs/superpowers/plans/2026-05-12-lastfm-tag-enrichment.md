# Last.fm Tag Enrichment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire Last.fm's `artist.getTopTags` endpoint into the existing Spotify analytics pipeline so the notebook produces real `Top Tags` and `Top Genres` panels (with graceful skip when `LASTFM_API_KEY` is unset).

**Architecture:** `Artist` gains a raw `tags: tuple[str, ...]` field; `genres` becomes a derived `@property` filtered through a whitelist module. A new `LastFmClient` (stdlib `urllib`, FileCache-backed, 365-day TTL) is plugged into `SpotifyClient._enrich_with_artists` as an optional `genre_enricher`. Spotify's artist cache stays read-only. A new `Analyzer.skip_message` hook lets `PlaylistAnalyzer.run_all`/`plot_all` cleanly skip Tag/Genre panels at zero coverage. A new `TagAnalyzer` joins `GenreAnalyzer` as a second concrete `Analyzer` subclass over a list-column.

**Tech Stack:** Python 3.11+, stdlib `urllib.request`, `dataclasses.replace`, existing `FileCache`, `pytest` with mocked HTTP via `unittest.mock`.

**Spec:** `docs/superpowers/specs/2026-05-11-lastfm-genre-enrichment.md`

---

## File Structure

**Create:**
- `src/spotify_project/genre_taxonomy.py` — `GENRE_WHITELIST` + `filter_to_genres`.
- `src/spotify_project/lastfm_client.py` — `LastFmClient` class.
- `tests/test_genre_taxonomy.py` — filter behavior tests.
- `tests/test_lastfm_client.py` — `LastFmClient` tests with mocked HTTP and cache.

**Modify:**
- `src/spotify_project/models.py` — `Artist`: replace `genres` field with `tags` field + derived `genres` @property.
- `src/spotify_project/client.py` — `SpotifyClient.__init__` and `from_env` accept `genre_enricher: LastFmClient | None`; `_enrich_with_artists` runs the Last.fm loop in-memory after Spotify resolves.
- `src/spotify_project/analyzer.py` — add `Analyzer.skip_message` class attr; add `TagAnalyzer`; `GenreAnalyzer` gets `skip_message`; `PlaylistAnalyzer.run_all`/`plot_all` skip on zero coverage when `skip_message` set; `PlaylistAnalyzer.from_playlist` materializes `tags` + `genres` columns; `TagAnalyzer()` registered in default list before `YearAnalyzer()`.
- `tests/test_models.py` — replace existing `Artist(genres=...)` assertions with `Artist(tags=...)` + `genres` property tests.
- `tests/test_analyzer.py` — add `TagAnalyzer` tests; update `GenreAnalyzer` test fixtures to populate via tags; add skip-when-zero-coverage tests.
- `tests/test_playlist_analyzer.py` — assert `tags` and `genres` columns produced by `from_playlist`.
- `tests/test_client.py` — add tests covering `_enrich_with_artists` with mocked `genre_enricher`, and with `genre_enricher=None`.
- `notebooks/01_explore_user_account.ipynb` — wire `LastFmClient.from_env` and pass to `SpotifyClient.from_env`.
- `README.md` — new subsection under "Spotify Web API limitations": "Restoring genres (and adding tags) via Last.fm".
- `CLAUDE.md` — update gotcha #3 to reflect the new `Artist.tags` + derived `genres` model.

---

## Conventions and pre-flight (read once)

- All new Python files start with `from __future__ import annotations`.
- Strict type annotations everywhere; project runs `pyright` strict (see `~/.claude/rules/python-style.md`).
- Docstrings: Google-style on every class and non-trivial public method.
- Run tests with `.venv\Scripts\python.exe -m pytest <path> -v` (Windows, no activation required).
- `ruff check src tests` and `ruff format --check src tests` must stay clean.
- Last.fm fetched tags are **lowercased once in `LastFmClient.fetch_artist_tags`**. Downstream code (Artist, filter, analyzers) assumes lowercase.
- The cache stores `{"tags": [...]}` (FileCache JSON-serializes dicts; tuples become lists in JSON anyway).
- Commit after every task with a short imperative message; never use `--no-verify`. Co-author trailer is added by the harness if applicable; otherwise just the subject.

---

## Task 1: `genre_taxonomy` module

**Files:**
- Create: `src/spotify_project/genre_taxonomy.py`
- Create: `tests/test_genre_taxonomy.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_genre_taxonomy.py`:
```python
from __future__ import annotations

from spotify_project.genre_taxonomy import GENRE_WHITELIST, filter_to_genres


def test_filter_to_genres_keeps_whitelisted_tags_in_order() -> None:
    result = filter_to_genres(("rock", "seen live", "indie", "british"))
    assert result == ["rock", "indie"]


def test_filter_to_genres_returns_empty_for_empty_input() -> None:
    assert filter_to_genres(()) == []


def test_filter_to_genres_drops_unknown_tags() -> None:
    assert filter_to_genres(("seen live", "british", "00s")) == []


def test_filter_to_genres_preserves_descending_weight_order() -> None:
    # If both rock and indie are in the whitelist, the order in the output
    # must match the order in the input (Last.fm returns descending weight).
    assert filter_to_genres(("indie", "rock")) == ["indie", "rock"]
    assert filter_to_genres(("rock", "indie")) == ["rock", "indie"]


def test_genre_whitelist_is_frozenset_of_str() -> None:
    assert isinstance(GENRE_WHITELIST, frozenset)
    assert all(isinstance(g, str) for g in GENRE_WHITELIST)
    # Spot-check that a defensible baseline is present.
    for g in ("rock", "pop", "indie", "electronic", "jazz", "metal"):
        assert g in GENRE_WHITELIST
```

- [ ] **Step 2: Run tests to verify they fail**

```
.venv\Scripts\python.exe -m pytest tests/test_genre_taxonomy.py -v
```
Expected: ImportError / ModuleNotFoundError (module doesn't exist yet).

- [ ] **Step 3: Implement the module**

Create `src/spotify_project/genre_taxonomy.py`:
```python
from __future__ import annotations

GENRE_WHITELIST: frozenset[str] = frozenset({
    # Baseline of widely-recognized genres. Iteratively refined during the
    # tag-cleaning notebook session (compare Top Tags vs Top Genres panels).
    # All entries lowercase; LastFmClient lowercases tags before they reach
    # this filter.
    "rock", "pop", "indie", "indie pop", "indie rock", "alternative",
    "alternative rock", "metal", "heavy metal", "black metal", "death metal",
    "doom metal", "thrash metal", "metalcore", "hardcore", "punk", "post-punk",
    "pop punk", "ska", "emo",
    "jazz", "blues", "soul", "funk", "r&b", "rnb",
    "rap", "hip-hop", "hip hop", "trap", "grime",
    "electronic", "electronica", "house", "deep house", "tech house", "techno",
    "trance", "ambient", "drum and bass", "dnb", "dubstep", "edm", "idm",
    "synthwave", "synthpop", "electropop", "industrial",
    "classical", "baroque", "opera", "orchestral", "soundtrack", "score",
    "folk", "folk rock", "country", "americana", "bluegrass",
    "reggae", "ska", "dub", "dancehall",
    "disco", "post-rock", "post-metal", "shoegaze", "dream pop", "noise",
    "experimental", "psychedelic", "psychedelic rock", "garage rock",
    "indietronica", "lo-fi", "j-pop", "k-pop", "j-rock",
    "gospel", "world", "latin", "tango", "salsa", "bossa nova", "afrobeat",
    "new wave", "no wave", "math rock", "progressive rock", "prog",
    "singer-songwriter", "acoustic",
})


def filter_to_genres(tags: tuple[str, ...]) -> list[str]:
    """Return the whitelisted subset of ``tags``, preserving input order.

    Tags are expected lowercase (lowercasing happens upstream in
    ``LastFmClient.fetch_artist_tags``), so the filter is a pure membership
    check with no normalization.

    Args:
        tags: Lowercased tags in descending-weight order, as stored on Artist.

    Returns:
        A new list containing only the tags that appear in GENRE_WHITELIST,
        in the same order they appeared in ``tags``.
    """
    return [t for t in tags if t in GENRE_WHITELIST]
```

- [ ] **Step 4: Run tests to verify they pass**

```
.venv\Scripts\python.exe -m pytest tests/test_genre_taxonomy.py -v
```
Expected: 5 passed.

- [ ] **Step 5: Lint and typecheck**

```
.venv\Scripts\python.exe -m ruff check src/spotify_project/genre_taxonomy.py tests/test_genre_taxonomy.py
.venv\Scripts\python.exe -m ruff format --check src/spotify_project/genre_taxonomy.py tests/test_genre_taxonomy.py
.venv\Scripts\python.exe -m pyright src/spotify_project/genre_taxonomy.py tests/test_genre_taxonomy.py
```
Expected: clean output, no errors.

- [ ] **Step 6: Commit**

```
git add src/spotify_project/genre_taxonomy.py tests/test_genre_taxonomy.py
git commit -m "add genre_taxonomy module with whitelist and filter"
```

---

## Task 2: `Artist.tags` field + derived `Artist.genres` property

**Files:**
- Modify: `src/spotify_project/models.py:11-39` — replace `Artist` class body and `from_api`.
- Modify: `tests/test_models.py` — replace `Artist(genres=...)` assertions with `tags`/`genres` property assertions.

- [ ] **Step 1: Inspect current `test_models.py` to identify Artist-related tests**

```
.venv\Scripts\python.exe -m pytest tests/test_models.py -v --collect-only
```
Note any test that constructs `Artist` with `genres=...` — those need rewriting in step 4.

- [ ] **Step 2: Write the failing tests for the new model**

Add to `tests/test_models.py` (place near existing `Artist` tests; do not delete the test_models.py header / imports):
```python
def test_artist_tags_defaults_to_empty_tuple() -> None:
    from spotify_project.models import Artist
    a = Artist(id="x", name="y")
    assert a.tags == ()
    assert a.genres == ()


def test_artist_genres_filters_tags_through_whitelist() -> None:
    from spotify_project.models import Artist
    a = Artist(id="x", name="y", tags=("rock", "seen live", "indie", "british"))
    assert a.genres == ("rock", "indie")


def test_artist_genres_preserves_descending_weight_order() -> None:
    from spotify_project.models import Artist
    a = Artist(id="x", name="y", tags=("indie", "rock"))
    assert a.genres == ("indie", "rock")
    b = Artist(id="x", name="y", tags=("rock", "indie"))
    assert b.genres == ("rock", "indie")


def test_artist_from_api_ignores_legacy_genres_field() -> None:
    # Spotify still emits an empty `genres` list for our app; we drop the field.
    # If they ever started returning values, we'd ignore them — Last.fm is the source.
    from spotify_project.models import Artist
    a = Artist.from_api({"id": "x", "name": "y", "genres": ["leftover"]})
    assert a.tags == ()
    assert a.genres == ()
```

- [ ] **Step 3: Run the new tests to verify they fail**

```
.venv\Scripts\python.exe -m pytest tests/test_models.py::test_artist_tags_defaults_to_empty_tuple tests/test_models.py::test_artist_genres_filters_tags_through_whitelist tests/test_models.py::test_artist_genres_preserves_descending_weight_order tests/test_models.py::test_artist_from_api_ignores_legacy_genres_field -v
```
Expected: TypeError on `tags=` (Artist doesn't have that field yet), or `AttributeError: 'Artist' object has no attribute 'genres'` if you've already removed `genres`.

- [ ] **Step 4: Replace the Artist class body**

Open `src/spotify_project/models.py` and replace the `Artist` class definition (lines ~11-39) with:
```python
@dataclass(slots=True, frozen=True)
class Artist:
    """A Spotify artist enriched with Last.fm tags.

    Attributes:
        id: Spotify artist ID.
        name: Display name.
        tags: Raw Last.fm tags, lowercased, in descending-weight order.
            Empty when Last.fm enrichment is disabled or the artist is
            unknown to Last.fm.
    """

    id: str
    name: str
    tags: tuple[str, ...] = ()

    @property
    def genres(self) -> tuple[str, ...]:
        """Whitelist-filtered subset of tags, preserving descending-weight order.

        Recomputed on every access (cheap: a tuple comprehension over <=10 items).
        Whitelist edits in genre_taxonomy.py take effect immediately on next read,
        with no need to rebuild Artist instances or re-fetch from Last.fm.

        Returns:
            Tuple of whitelisted genre tags in the same order they appear in tags.
        """
        return tuple(filter_to_genres(self.tags))

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> Artist:
        """Parse a Spotify artist API response.

        Args:
            data: A spotipy artist dict with keys id and name. The legacy
                ``genres`` field (always empty for our app) is ignored;
                tags come from Last.fm enrichment, attached later by
                ``SpotifyClient._enrich_with_artists`` via dataclasses.replace.

        Returns:
            The constructed Artist with empty tags. Enrichment fills tags later.
        """
        return cls(
            id=data["id"],
            name=data["name"],
        )
```

Also add the import at the top of `models.py`, near the existing imports:
```python
from .genre_taxonomy import filter_to_genres
```

- [ ] **Step 5: Update existing Artist-related tests in `tests/test_models.py`**

Find any existing test that constructs `Artist(..., genres=("rock", ...))` or asserts `artist.genres == ("rock", ...)` and rewrite it to construct via `tags=`. Example transformation:
```python
# Before:
a = Artist(id="x", name="y", genres=("rock", "pop"))
assert a.genres == ("rock", "pop")

# After:
a = Artist(id="x", name="y", tags=("rock", "pop"))
assert a.tags == ("rock", "pop")
assert a.genres == ("rock", "pop")   # both are whitelisted
```
For tests that asserted `Artist.from_api({..., "genres": [...]})` produced non-empty genres: rewrite to assert `Artist.from_api({..., "genres": [...]}).tags == ()` since `from_api` no longer reads that field.

- [ ] **Step 6: Run the full models test file**

```
.venv\Scripts\python.exe -m pytest tests/test_models.py -v
```
Expected: all green. If failures, they are stale `genres=` constructor calls — fix them per Step 5 pattern.

- [ ] **Step 7: Lint and typecheck**

```
.venv\Scripts\python.exe -m ruff check src/spotify_project/models.py tests/test_models.py
.venv\Scripts\python.exe -m ruff format --check src/spotify_project/models.py tests/test_models.py
.venv\Scripts\python.exe -m pyright src/spotify_project/models.py tests/test_models.py
```
Expected: clean.

- [ ] **Step 8: Commit**

```
git add src/spotify_project/models.py tests/test_models.py
git commit -m "store raw tags on Artist; derive genres via whitelist property"
```

---

## Task 3: `LastFmClient` happy-path fetch with cache

**Files:**
- Create: `src/spotify_project/lastfm_client.py`
- Create: `tests/test_lastfm_client.py`

This task delivers the working core: construct a client, fetch tags for a known artist, cache the result. Error handling (artist-not-found, rate-limit) is Task 4. `from_env` is Task 5.

- [ ] **Step 1: Write the failing happy-path tests**

Create `tests/test_lastfm_client.py`:
```python
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from spotify_project.cache import FileCache
from spotify_project.lastfm_client import LastFmClient


@pytest.fixture
def cache(tmp_path: Path) -> FileCache:
    return FileCache(root=tmp_path / "api")


def _mock_urlopen_response(payload: dict[str, Any]) -> MagicMock:
    """Build a MagicMock that mimics urllib.request.urlopen's return.

    The returned object supports the context-manager protocol and a
    ``read()`` method returning the JSON-encoded payload as bytes.
    """
    mock_response = MagicMock()
    mock_response.__enter__.return_value = mock_response
    mock_response.__exit__.return_value = False
    mock_response.read.return_value = json.dumps(payload).encode("utf-8")
    return mock_response


def test_fetch_artist_tags_returns_lowercased_tags_in_order(cache: FileCache) -> None:
    client = LastFmClient(api_key="test-key", cache=cache)
    payload = {
        "toptags": {
            "tag": [
                {"name": "Electronic", "count": 100},
                {"name": "House", "count": 80},
                {"name": "French", "count": 60},
            ]
        }
    }
    with patch("spotify_project.lastfm_client.urlopen", return_value=_mock_urlopen_response(payload)):
        tags = client.fetch_artist_tags("daft-punk-id", "Daft Punk")
    assert tags == ("electronic", "house", "french")


def test_fetch_artist_tags_limits_to_default_top_n(cache: FileCache) -> None:
    client = LastFmClient(api_key="test-key", cache=cache)
    payload = {
        "toptags": {
            "tag": [{"name": f"tag{i}", "count": 100 - i} for i in range(20)]
        }
    }
    with patch("spotify_project.lastfm_client.urlopen", return_value=_mock_urlopen_response(payload)):
        tags = client.fetch_artist_tags("x", "X")
    assert len(tags) == LastFmClient.DEFAULT_TOP_N


def test_fetch_artist_tags_caches_results(cache: FileCache) -> None:
    client = LastFmClient(api_key="test-key", cache=cache)
    payload = {"toptags": {"tag": [{"name": "rock", "count": 100}]}}
    with patch("spotify_project.lastfm_client.urlopen", return_value=_mock_urlopen_response(payload)) as mocked:
        client.fetch_artist_tags("x", "X")
        client.fetch_artist_tags("x", "X")
    assert mocked.call_count == 1


def test_fetch_artist_tags_force_refresh_bypasses_cache(cache: FileCache) -> None:
    client = LastFmClient(api_key="test-key", cache=cache)
    payload = {"toptags": {"tag": [{"name": "rock", "count": 100}]}}
    with patch("spotify_project.lastfm_client.urlopen", return_value=_mock_urlopen_response(payload)) as mocked:
        client.fetch_artist_tags("x", "X")
        client.fetch_artist_tags("x", "X", force_refresh=True)
    assert mocked.call_count == 2


def test_fetch_artist_tags_handles_single_tag_dict(cache: FileCache) -> None:
    # Last.fm's XML-to-JSON conversion sometimes returns a single dict
    # instead of a 1-element list. We normalize.
    client = LastFmClient(api_key="test-key", cache=cache)
    payload = {"toptags": {"tag": {"name": "Rock", "count": 100}}}
    with patch("spotify_project.lastfm_client.urlopen", return_value=_mock_urlopen_response(payload)):
        tags = client.fetch_artist_tags("x", "X")
    assert tags == ("rock",)


def test_fetch_artist_tags_returns_empty_when_no_tags(cache: FileCache) -> None:
    client = LastFmClient(api_key="test-key", cache=cache)
    payload = {"toptags": {"tag": []}}
    with patch("spotify_project.lastfm_client.urlopen", return_value=_mock_urlopen_response(payload)):
        tags = client.fetch_artist_tags("x", "X")
    assert tags == ()
```

- [ ] **Step 2: Run tests to verify they fail**

```
.venv\Scripts\python.exe -m pytest tests/test_lastfm_client.py -v
```
Expected: ModuleNotFoundError on `spotify_project.lastfm_client`.

- [ ] **Step 3: Implement the LastFmClient core**

Create `src/spotify_project/lastfm_client.py`:
```python
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
        api_key: Last.fm API key (read from LASTFM_API_KEY env var by from_env).
        cache: FileCache used to persist per-artist tag lists.
    """

    BASE_URL: ClassVar[str] = "https://ws.audioscrobbler.com/2.0/"
    RATE_LIMIT_DELAY_SECONDS: ClassVar[float] = 0.2
    CACHE_TTL_DAYS: ClassVar[float] = 365.0
    DEFAULT_TOP_N: ClassVar[int] = 10
    REQUEST_TIMEOUT_SECONDS: ClassVar[float] = 10.0

    def __init__(self, api_key: str, cache: FileCache) -> None:
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

        Tags are lowercased and returned in descending-weight order (Last.fm's
        native ordering). Cached under ``lastfm_artist/<spotify_artist_id>.json``
        with a 365-day TTL — tags drift slowly and re-fetching every notebook
        run wastes time. Uses ``autocorrect=1`` so common misspellings still
        match the canonical artist.

        Args:
            spotify_artist_id: The Spotify artist ID, used as the cache key
                (so two Last.fm artists with the same name don't collide).
            artist_name: The artist's display name, used in the Last.fm
                query string.
            force_refresh: If True, skip the cache and refetch from Last.fm.

        Returns:
            Tuple of up to DEFAULT_TOP_N lowercased tags, descending-weight
            order. Empty tuple if Last.fm has no tags for this artist.
        """
        cache_key = f"lastfm_artist/{spotify_artist_id}"
        cached = None if force_refresh else self.cache.get(cache_key, ttl_days=self.CACHE_TTL_DAYS)
        if cached is not None:
            return tuple(cast(list[str], cached["tags"]))

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
        data = cast(dict[str, Any], json.loads(body))

        tags = self._extract_tags(data)
        self.cache.put(cache_key, {"tags": list(tags)})
        return tags

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
        raw = toptags.get("tag", [])
        if isinstance(raw, dict):
            raw = [raw]
        items = cast(list[dict[str, Any]], raw)
        names = [str(item.get("name", "")).strip().lower() for item in items]
        names = [n for n in names if n]
        return tuple(names[: self.DEFAULT_TOP_N])
```

Note: `time` is imported but not used yet — it will be in Task 4 (rate-limit retry). Keep it.

- [ ] **Step 4: Run tests to verify they pass**

```
.venv\Scripts\python.exe -m pytest tests/test_lastfm_client.py -v
```
Expected: all 6 tests pass.

- [ ] **Step 5: Lint and typecheck**

```
.venv\Scripts\python.exe -m ruff check src/spotify_project/lastfm_client.py tests/test_lastfm_client.py
.venv\Scripts\python.exe -m ruff format --check src/spotify_project/lastfm_client.py tests/test_lastfm_client.py
.venv\Scripts\python.exe -m pyright src/spotify_project/lastfm_client.py tests/test_lastfm_client.py
```
Expected: clean. If ruff complains about the unused `time` import in Step 3, add a `# noqa: F401  # used in fetch_artist_tags retry path` comment OR temporarily remove and re-add it in Task 4. Prefer removing it now and re-adding in Task 4 — cleaner diff.

- [ ] **Step 6: Commit**

```
git add src/spotify_project/lastfm_client.py tests/test_lastfm_client.py
git commit -m "add LastFmClient with cached fetch_artist_tags"
```

---

## Task 4: `LastFmClient` error handling (artist-not-found, rate limit)

**Files:**
- Modify: `src/spotify_project/lastfm_client.py` — handle error responses in `fetch_artist_tags`.
- Modify: `tests/test_lastfm_client.py` — add error-path tests.

- [ ] **Step 1: Write the failing error-path tests**

Append to `tests/test_lastfm_client.py`:
```python
def test_fetch_artist_tags_returns_empty_on_artist_not_found(
    cache: FileCache, caplog: pytest.LogCaptureFixture
) -> None:
    client = LastFmClient(api_key="test-key", cache=cache)
    # Last.fm returns HTTP 200 even on errors; the error is in the body.
    error_payload = {"error": 6, "message": "The artist you supplied could not be found"}
    with patch("spotify_project.lastfm_client.urlopen", return_value=_mock_urlopen_response(error_payload)):
        with caplog.at_level("WARNING", logger="spotify_project.lastfm_client"):
            tags = client.fetch_artist_tags("x", "ObscureArtist")
    assert tags == ()
    assert any("ObscureArtist" in rec.message for rec in caplog.records)


def test_fetch_artist_tags_caches_artist_not_found_result(cache: FileCache) -> None:
    # Negative results are cached too — no point refetching a known-missing artist.
    client = LastFmClient(api_key="test-key", cache=cache)
    error_payload = {"error": 6, "message": "not found"}
    with patch("spotify_project.lastfm_client.urlopen", return_value=_mock_urlopen_response(error_payload)) as mocked:
        client.fetch_artist_tags("x", "X")
        client.fetch_artist_tags("x", "X")
    assert mocked.call_count == 1


def test_fetch_artist_tags_retries_on_rate_limit_then_succeeds(cache: FileCache) -> None:
    client = LastFmClient(api_key="test-key", cache=cache)
    rate_limit_payload = {"error": 29, "message": "Rate limit exceeded"}
    success_payload = {"toptags": {"tag": [{"name": "rock", "count": 100}]}}
    side_effects = [
        _mock_urlopen_response(rate_limit_payload),
        _mock_urlopen_response(success_payload),
    ]
    with patch("spotify_project.lastfm_client.urlopen", side_effect=side_effects):
        # The first response triggers a single retry; the second succeeds.
        tags = client.fetch_artist_tags("x", "X")
    assert tags == ("rock",)


def test_fetch_artist_tags_raises_when_rate_limit_persists(cache: FileCache) -> None:
    client = LastFmClient(api_key="test-key", cache=cache)
    rate_limit_payload = {"error": 29, "message": "Rate limit exceeded"}
    side_effects = [
        _mock_urlopen_response(rate_limit_payload),
        _mock_urlopen_response(rate_limit_payload),
    ]
    with patch("spotify_project.lastfm_client.urlopen", side_effect=side_effects):
        with pytest.raises(RuntimeError, match="rate limit"):
            client.fetch_artist_tags("x", "X")


def test_fetch_artist_tags_raises_on_other_errors(cache: FileCache) -> None:
    client = LastFmClient(api_key="test-key", cache=cache)
    error_payload = {"error": 10, "message": "Invalid API key"}
    with patch("spotify_project.lastfm_client.urlopen", return_value=_mock_urlopen_response(error_payload)):
        with pytest.raises(RuntimeError, match="Invalid API key"):
            client.fetch_artist_tags("x", "X")
```

- [ ] **Step 2: Run tests to verify they fail**

```
.venv\Scripts\python.exe -m pytest tests/test_lastfm_client.py -v
```
Expected: the new tests fail; the original 6 still pass.

- [ ] **Step 3: Rework `fetch_artist_tags` to handle errors**

In `src/spotify_project/lastfm_client.py`, replace the body of `fetch_artist_tags` with:
```python
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
            if error_code == 29 and attempt == 0:
                logger.warning("Last.fm rate limit hit; sleeping %.1fs and retrying", self.RATE_LIMIT_DELAY_SECONDS * 5)
                time.sleep(self.RATE_LIMIT_DELAY_SECONDS * 5)
                continue
            message = data.get("message", "<no message>")
            raise RuntimeError(f"Last.fm error {error_code} for artist {artist_name!r}: {message}")
        # Unreachable: the loop above returns or raises on every path; this satisfies the type checker.
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
```

The `_extract_tags` method from Task 3 stays unchanged.

- [ ] **Step 4: Run all LastFmClient tests**

```
.venv\Scripts\python.exe -m pytest tests/test_lastfm_client.py -v
```
Expected: all tests pass (Task 3's 6 + Task 4's 5 = 11).

- [ ] **Step 5: Lint and typecheck**

```
.venv\Scripts\python.exe -m ruff check src/spotify_project/lastfm_client.py tests/test_lastfm_client.py
.venv\Scripts\python.exe -m ruff format --check src/spotify_project/lastfm_client.py tests/test_lastfm_client.py
.venv\Scripts\python.exe -m pyright src/spotify_project/lastfm_client.py tests/test_lastfm_client.py
```
Expected: clean.

- [ ] **Step 6: Commit**

```
git add src/spotify_project/lastfm_client.py tests/test_lastfm_client.py
git commit -m "add Last.fm error handling: not-found, rate-limit retry"
```

---

## Task 5: `LastFmClient.from_env` returning Optional

**Files:**
- Modify: `src/spotify_project/lastfm_client.py` — add `from_env` classmethod.
- Modify: `tests/test_lastfm_client.py` — add `from_env` tests.

- [ ] **Step 1: Write the failing `from_env` tests**

Append to `tests/test_lastfm_client.py`:
```python
def test_from_env_returns_client_when_key_set(
    cache: FileCache, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LASTFM_API_KEY", "real-key-xyz")
    client = LastFmClient.from_env(cache=cache)
    assert client is not None
    assert client.api_key == "real-key-xyz"
    assert client.cache is cache


def test_from_env_returns_none_when_key_missing(
    cache: FileCache, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.delenv("LASTFM_API_KEY", raising=False)
    with caplog.at_level("INFO", logger="spotify_project.lastfm_client"):
        client = LastFmClient.from_env(cache=cache)
    assert client is None
    assert any("LASTFM_API_KEY" in rec.message for rec in caplog.records)


def test_from_env_returns_none_when_key_blank(
    cache: FileCache, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LASTFM_API_KEY", "")
    client = LastFmClient.from_env(cache=cache)
    assert client is None
```

- [ ] **Step 2: Run tests to verify they fail**

```
.venv\Scripts\python.exe -m pytest tests/test_lastfm_client.py -v -k from_env
```
Expected: AttributeError — `from_env` doesn't exist.

- [ ] **Step 3: Add the `from_env` classmethod**

In `src/spotify_project/lastfm_client.py`, add the `os` import near the existing imports:
```python
import os
```

Then add this classmethod inside `LastFmClient` (place it right after `__init__`):
```python
    @classmethod
    def from_env(cls, cache: FileCache) -> LastFmClient | None:
        """Build a LastFmClient from the LASTFM_API_KEY env var.

        Reads the key from ``os.environ``. Returns None and emits a single
        INFO log line when the key is unset or empty — Last.fm enrichment is
        optional; the notebook degrades gracefully and TagAnalyzer/GenreAnalyzer
        get skipped instead of producing empty panels.

        Args:
            cache: FileCache for response persistence.

        Returns:
            A configured LastFmClient, or None when LASTFM_API_KEY is unset
            or blank.
        """
        key = os.environ.get("LASTFM_API_KEY", "").strip()
        if not key:
            logger.info("Last.fm enrichment disabled — set LASTFM_API_KEY to enable. Tag and Genre panels will be skipped.")
            return None
        return cls(api_key=key, cache=cache)
```

- [ ] **Step 4: Run tests to verify they pass**

```
.venv\Scripts\python.exe -m pytest tests/test_lastfm_client.py -v
```
Expected: all 14 tests pass (Task 3's 6 + Task 4's 5 + Task 5's 3).

- [ ] **Step 5: Lint and typecheck**

```
.venv\Scripts\python.exe -m ruff check src/spotify_project/lastfm_client.py tests/test_lastfm_client.py
.venv\Scripts\python.exe -m ruff format --check src/spotify_project/lastfm_client.py tests/test_lastfm_client.py
.venv\Scripts\python.exe -m pyright src/spotify_project/lastfm_client.py tests/test_lastfm_client.py
```
Expected: clean.

- [ ] **Step 6: Commit**

```
git add src/spotify_project/lastfm_client.py tests/test_lastfm_client.py
git commit -m "add LastFmClient.from_env returning None when key missing"
```

---

## Task 6: Wire `LastFmClient` into `SpotifyClient`

**Files:**
- Modify: `src/spotify_project/client.py` — add `genre_enricher` param to `__init__` and `from_env`; extend `_enrich_with_artists`.
- Modify: `tests/test_client.py` — add tests covering enricher-on and enricher-off paths.

- [ ] **Step 1: Inspect current test_client.py for the enrichment test pattern**

```
.venv\Scripts\python.exe -m pytest tests/test_client.py -v --collect-only
```
Note the existing test that exercises `_enrich_with_artists` (it should mock `sp.artist` or use a pre-populated cache).

- [ ] **Step 2: Write the failing enricher tests**

Append to `tests/test_client.py` (the file already has `from unittest.mock import MagicMock`; keep using the existing patterns there):
```python
def test_enrich_with_artists_uses_genre_enricher_when_set(tmp_path: Path) -> None:
    from spotify_project.cache import FileCache
    from spotify_project.client import SpotifyClient
    from spotify_project.models import Artist
    from unittest.mock import MagicMock

    cache = FileCache(root=tmp_path / "api")
    # Pre-populate Spotify artist cache so the Spotify side is read-only here.
    cache.put("artist/A1", {"id": "A1", "name": "Artist One"})

    sp = MagicMock()  # Spotipy client; should NOT be called for already-cached artists.
    enricher = MagicMock()
    enricher.fetch_artist_tags.return_value = ("rock", "indie")

    client = SpotifyClient(sp=sp, cache=cache, genre_enricher=enricher)
    track_items = [
        {
            "item": {
                "type": "track",
                "id": "T1",
                "name": "Track One",
                "artists": [{"id": "A1", "name": "Artist One"}],
                "album": {"name": "Album", "release_date": "2020-01-01"},
                "duration_ms": 200_000,
                "explicit": False,
            },
            "added_at": "2024-01-01T00:00:00Z",
            "is_local": False,
        }
    ]

    tracks = client._enrich_with_artists(track_items)

    assert len(tracks) == 1
    primary = tracks[0].primary_artist
    assert primary is not None
    assert primary.tags == ("rock", "indie")
    enricher.fetch_artist_tags.assert_called_once_with("A1", "Artist One")
    sp.artist.assert_not_called()


def test_enrich_with_artists_skips_lastfm_when_enricher_none(tmp_path: Path) -> None:
    from spotify_project.cache import FileCache
    from spotify_project.client import SpotifyClient
    from unittest.mock import MagicMock

    cache = FileCache(root=tmp_path / "api")
    cache.put("artist/A1", {"id": "A1", "name": "Artist One"})

    sp = MagicMock()
    client = SpotifyClient(sp=sp, cache=cache, genre_enricher=None)
    track_items = [
        {
            "item": {
                "type": "track",
                "id": "T1",
                "name": "Track One",
                "artists": [{"id": "A1", "name": "Artist One"}],
                "album": {"name": "Album", "release_date": "2020-01-01"},
                "duration_ms": 200_000,
                "explicit": False,
            },
            "added_at": "2024-01-01T00:00:00Z",
            "is_local": False,
        }
    ]

    tracks = client._enrich_with_artists(track_items)

    primary = tracks[0].primary_artist
    assert primary is not None
    assert primary.tags == ()


def test_spotify_client_init_defaults_genre_enricher_to_none(tmp_path: Path) -> None:
    from spotify_project.cache import FileCache
    from spotify_project.client import SpotifyClient
    from unittest.mock import MagicMock

    cache = FileCache(root=tmp_path / "api")
    sp = MagicMock()
    client = SpotifyClient(sp=sp, cache=cache)
    assert client.genre_enricher is None
```

Make sure `from pathlib import Path` is imported at the top of `test_client.py`; if not, add it.

- [ ] **Step 3: Run tests to verify they fail**

```
.venv\Scripts\python.exe -m pytest tests/test_client.py::test_enrich_with_artists_uses_genre_enricher_when_set tests/test_client.py::test_enrich_with_artists_skips_lastfm_when_enricher_none tests/test_client.py::test_spotify_client_init_defaults_genre_enricher_to_none -v
```
Expected: TypeError on the `genre_enricher=` kwarg (SpotifyClient doesn't accept it yet).

- [ ] **Step 4: Update `SpotifyClient.__init__`**

In `src/spotify_project/client.py`, modify the `__init__` signature and body (around line 57):
```python
    def __init__(
        self,
        sp: spotipy.Spotify,
        cache: FileCache,
        genre_enricher: "LastFmClient | None" = None,
    ) -> None:
        self.sp = sp
        self.cache = cache
        self.genre_enricher = genre_enricher
```

Add at the top of `client.py` near the other type-only imports (after the `from __future__ import annotations` line — already present):
```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .lastfm_client import LastFmClient
```

This avoids a hard import cycle while keeping the type annotation strict-mode-clean. The string forward reference in the signature uses it.

- [ ] **Step 5: Extend `_enrich_with_artists`**

In `_enrich_with_artists` (around line 236), after the existing line that builds `artist_by_id`:
```python
        artist_by_id: dict[str, Artist] = {a.id: a for a in self.fetch_artists(artist_ids, force_refresh=force_refresh)}
```

…insert the Last.fm enrichment block, then return as before. The full updated method body (replacing lines ~236-260):
```python
    def _enrich_with_artists(self, track_items: list[dict[str, Any]], *, force_refresh: bool = False) -> list[Track]:
        """Filter to audio tracks, resolve artist lookups, and return Track objects.

        Extracts the common enrichment pipeline shared by ``fetch_playlist()`` and
        ``fetch_liked_songs()``: filter items to audio tracks, collect unique
        artist IDs, batch-fetch via ``fetch_artists()``, then construct Track
        objects with full Artist references. If a ``genre_enricher`` was injected,
        artists are additionally enriched with Last.fm tags before Track
        construction — the Spotify-side ``artist_by_id`` dict is rebuilt in
        memory; the on-disk Spotify cache is never modified.

        Args:
            track_items: Raw playlist-item dicts using the ``item`` key schema.
            force_refresh: Passed through to ``fetch_artists()`` and to
                ``LastFmClient.fetch_artist_tags()``.

        Returns:
            List of fully-enriched Track objects (podcast episodes and
            local-file items dropped).
        """
        audio_tracks = [it for it in track_items if it.get("item") and it["item"].get("type") == "track"]
        dropped = len(track_items) - len(audio_tracks)
        if dropped > 0:
            logger.info("Dropped %d non-track items (podcasts, local files, etc.)", dropped)
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
            iter_artists: Iterable[Artist] = _tqdm_cls(  # pyright: ignore[reportUnknownVariableType]
                artist_by_id.values(),
                desc="Enriching with Last.fm tags",
                unit="artist",
            )
            for artist in iter_artists:
                tags = self.genre_enricher.fetch_artist_tags(artist.id, artist.name, force_refresh=force_refresh)
                enriched[artist.id] = replace(artist, tags=tags)
            artist_by_id = enriched

        return [Track.from_api(item, artist_by_id) for item in audio_tracks]
```

Add at the top of `client.py` (near the existing `from typing import Any, ClassVar, cast` import):
```python
from dataclasses import replace
```

- [ ] **Step 6: Update `from_env` to forward `genre_enricher`**

In `src/spotify_project/client.py`, modify `from_env` (around line 62-92) to accept and forward the param. Change the signature line and the final return:
```python
    @classmethod
    def from_env(
        cls,
        cache: FileCache,
        scopes: list[str] | None = None,
        *,
        genre_enricher: "LastFmClient | None" = None,
    ) -> SpotifyClient:
        # ... existing body unchanged until the final return ...
        return cls(sp=sp, cache=cache, genre_enricher=genre_enricher)
```

Update the docstring's `Args:` section to mention `genre_enricher`:
```
            genre_enricher: Optional Last.fm client for tag enrichment.
                When None (default), Artist.tags stays empty and TagAnalyzer
                / GenreAnalyzer panels are skipped downstream.
```

- [ ] **Step 7: Run all client tests**

```
.venv\Scripts\python.exe -m pytest tests/test_client.py -v
```
Expected: all pass. If existing tests break because `_enrich_with_artists` now also passes `force_refresh` through to the enricher (it does), they shouldn't — those tests don't set `genre_enricher`.

- [ ] **Step 8: Run the full test suite to catch any unintended ripple**

```
.venv\Scripts\python.exe -m pytest -v
```
Expected: all green. Likely failures are in test_analyzer.py / test_playlist_analyzer.py where existing tests use `Artist(genres=...)` constructor calls left over from Task 2 — fix those in place (same transformation as Task 2 Step 5).

- [ ] **Step 9: Lint and typecheck**

```
.venv\Scripts\python.exe -m ruff check src/spotify_project/client.py tests/test_client.py
.venv\Scripts\python.exe -m ruff format --check src/spotify_project/client.py tests/test_client.py
.venv\Scripts\python.exe -m pyright src/spotify_project/client.py tests/test_client.py
```
Expected: clean.

- [ ] **Step 10: Commit**

```
git add src/spotify_project/client.py tests/test_client.py
git commit -m "wire LastFmClient into SpotifyClient as optional genre_enricher"
```

---

## Task 7: `Analyzer.skip_message` + `run_all`/`plot_all` skip logic

**Files:**
- Modify: `src/spotify_project/analyzer.py` — add `Analyzer.skip_message` ClassVar; update `run_all` and `plot_all` to skip; add `skip_message` to existing `GenreAnalyzer`.
- Modify: `tests/test_analyzer.py` and/or `tests/test_playlist_analyzer.py` — add skip behavior tests.

`TagAnalyzer` itself is Task 8; this task wires the skip mechanism using the existing `GenreAnalyzer` as the demonstrator (it already exists and will become empty-by-default after Task 2's Artist change).

- [ ] **Step 1: Write the failing skip-behavior tests**

Add to `tests/test_playlist_analyzer.py` (or wherever `PlaylistAnalyzer` is tested):
```python
def test_run_all_skips_analyzer_with_zero_coverage_and_skip_message() -> None:
    import pandas as pd
    from spotify_project.analyzer import Analyzer, PlaylistAnalyzer
    from matplotlib.axes import Axes

    class FlaggedZeroCoverage(Analyzer):
        title = "Flagged"
        skip_message = "no data; set X to enable"

        def coverage(self, df: pd.DataFrame) -> tuple[int, int]:
            return (0, len(df))

        def analyze(self, df: pd.DataFrame) -> pd.DataFrame:
            raise AssertionError("analyze should not be called when skip applies")

        def plot(self, ax: Axes, summary: pd.DataFrame, *, color: object = None) -> None:
            raise AssertionError("plot should not be called when skip applies")

    df = pd.DataFrame({"x": [1, 2, 3]})
    pa = PlaylistAnalyzer(df=df, analyzers=[FlaggedZeroCoverage()])
    result = pa.run_all()
    assert "Flagged" not in result


def test_run_all_runs_analyzer_with_zero_coverage_when_no_skip_message() -> None:
    import pandas as pd
    from spotify_project.analyzer import Analyzer, PlaylistAnalyzer
    from matplotlib.axes import Axes

    class UnflaggedZeroCoverage(Analyzer):
        title = "Unflagged"
        # skip_message left as default (None)

        def coverage(self, df: pd.DataFrame) -> tuple[int, int]:
            return (0, len(df))

        def analyze(self, df: pd.DataFrame) -> pd.DataFrame:
            return pd.DataFrame({"k": [], "v": []})

        def plot(self, ax: Axes, summary: pd.DataFrame, *, color: object = None) -> None:
            pass

    df = pd.DataFrame({"x": [1, 2, 3]})
    pa = PlaylistAnalyzer(df=df, analyzers=[UnflaggedZeroCoverage()])
    result = pa.run_all()
    assert "Unflagged" in result  # still runs — opt-in skip only


def test_plot_all_skips_zero_coverage_analyzer() -> None:
    import pandas as pd
    from matplotlib.axes import Axes
    from matplotlib.figure import Figure
    from spotify_project.analyzer import Analyzer, PlaylistAnalyzer

    class FlaggedZeroCoverage(Analyzer):
        title = "Flagged"
        skip_message = "no data"

        def coverage(self, df: pd.DataFrame) -> tuple[int, int]:
            return (0, len(df))

        def analyze(self, df: pd.DataFrame) -> pd.DataFrame:
            raise AssertionError("analyze should not be called when skip applies")

        def plot(self, ax: Axes, summary: pd.DataFrame, *, color: object = None) -> None:
            raise AssertionError("plot should not be called when skip applies")

    class AlwaysRuns(Analyzer):
        title = "Always"

        def coverage(self, df: pd.DataFrame) -> tuple[int, int]:
            n = len(df)
            return (n, n)

        def analyze(self, df: pd.DataFrame) -> pd.DataFrame:
            return pd.DataFrame({"k": [1], "v": [1]})

        def plot(self, ax: Axes, summary: pd.DataFrame, *, color: object = None) -> None:
            ax.bar([0], [1])

    df = pd.DataFrame({"x": [1, 2, 3]})
    pa = PlaylistAnalyzer(df=df, analyzers=[FlaggedZeroCoverage(), AlwaysRuns()])
    fig = Figure()
    pa.plot_all(fig)  # should not raise
    # One subplot, not two:
    assert len(fig.axes) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

```
.venv\Scripts\python.exe -m pytest tests/test_playlist_analyzer.py::test_run_all_skips_analyzer_with_zero_coverage_and_skip_message tests/test_playlist_analyzer.py::test_run_all_runs_analyzer_with_zero_coverage_when_no_skip_message tests/test_playlist_analyzer.py::test_plot_all_skips_zero_coverage_analyzer -v
```
Expected: assertion failures or AttributeError on `skip_message`.

- [ ] **Step 3: Add `skip_message` to the base `Analyzer`**

In `src/spotify_project/analyzer.py`, modify the `Analyzer` class around line 60-77:
```python
class Analyzer(ABC):
    """Abstract analyzer over a track DataFrame.

    Concrete subclasses override ``analyze`` (returns a summary DataFrame) and
    ``plot`` (renders the result onto a Matplotlib Axes provided by the caller).
    Each subclass MUST also declare a non-empty class-level ``title``; this is
    enforced at class-definition time.

    Attributes:
        title: Short title; appears as the plot's title and is used as the
            key in ``PlaylistAnalyzer.run_all``'s result dict.
        default_color: Default bar/line color for plot().
        skip_message: If set, ``PlaylistAnalyzer.run_all`` and ``plot_all``
            skip this analyzer when its ``coverage()`` returns ``(0, n)``.
            Default None means "always run, even at zero coverage" (the
            analyzer's own ``plot`` renders an empty-state placeholder).
            Use skip_message for analyzers whose data source can be entirely
            absent (e.g. tags without a Last.fm key) — the user-visible
            message is logged when the skip triggers.
    """

    title: ClassVar[str]
    default_color: ClassVar[_Color] = "#1f77b4"
    skip_message: ClassVar[str | None] = None
```

- [ ] **Step 4: Update `PlaylistAnalyzer.run_all` and `plot_all`**

Replace `run_all` (around line 614):
```python
    def run_all(self) -> dict[str, pd.DataFrame]:
        """Run every registered Analyzer; returns ``{title: summary_df}``.

        Analyzers whose ``coverage(df)`` returns ``(0, n)`` AND that have set
        ``skip_message`` are skipped entirely (no entry in the result dict);
        a single INFO log line records the skip and the analyzer's hint.
        """
        out: dict[str, pd.DataFrame] = {}
        for a in self.analyzers:
            if a.skip_message is not None:
                n_data, _ = a.coverage(self.df)
                if n_data == 0:
                    logger.info("Skipping %s: %s", a.effective_title, a.skip_message)
                    continue
            out[a.effective_title] = a.analyze(self.df)
        return out
```

Replace `plot_all` (around line 618):
```python
    def plot_all(self, fig: Figure) -> None:
        """Lay out one subplot per non-skipped analyzer in a vertical stack on ``fig``.

        Analyzers whose ``coverage(df)`` returns ``(0, n)`` AND that have set
        ``skip_message`` are skipped — no subplot allocated, no log line
        (the log line is emitted by ``run_all``, which this method calls).

        Args:
            fig: Matplotlib Figure to subdivide with subplots.
        """
        summaries = self.run_all()
        active = [a for a in self.analyzers if a.effective_title in summaries]
        n = len(active)
        if n == 0:
            return
        axes = fig.subplots(n, 1)
        axes_list = [axes] if n == 1 else list(axes)
        palette = sns.color_palette("colorblind", n_colors=n)
        for ax, analyzer, color in zip(axes_list, active, palette, strict=True):
            analyzer.plot(ax, summaries[analyzer.effective_title], color=color)
        fig.tight_layout()
```

- [ ] **Step 5: Set `skip_message` on existing `GenreAnalyzer`**

In `src/spotify_project/analyzer.py`, find the `GenreAnalyzer` class (around line 131) and add directly under its `title = "Top Genres"` line:
```python
    skip_message = "no genres after whitelist filtering — set LASTFM_API_KEY to enable, or extend GENRE_WHITELIST in genre_taxonomy.py."
```

- [ ] **Step 6: Run the new tests**

```
.venv\Scripts\python.exe -m pytest tests/test_playlist_analyzer.py -v
```
Expected: the three new skip-behavior tests pass; existing playlist-analyzer tests still pass.

- [ ] **Step 7: Run the full suite to surface any GenreAnalyzer-default-skip ripple**

```
.venv\Scripts\python.exe -m pytest -v
```
Expected: all green. After Task 2's Artist change, any existing test that constructed a Playlist with no tag data and expected `GenreAnalyzer` to produce output will now find it skipped. Fix those tests by either: (a) constructing artists with `tags=("rock",)` so `genres == ("rock",)`, or (b) asserting the skip behavior instead of asserting on empty data.

- [ ] **Step 8: Lint and typecheck**

```
.venv\Scripts\python.exe -m ruff check src/spotify_project/analyzer.py tests/test_playlist_analyzer.py tests/test_analyzer.py
.venv\Scripts\python.exe -m ruff format --check src/spotify_project/analyzer.py tests/test_playlist_analyzer.py tests/test_analyzer.py
.venv\Scripts\python.exe -m pyright src/spotify_project/analyzer.py tests/test_playlist_analyzer.py tests/test_analyzer.py
```
Expected: clean.

- [ ] **Step 9: Commit**

```
git add src/spotify_project/analyzer.py tests/test_playlist_analyzer.py tests/test_analyzer.py
git commit -m "add Analyzer.skip_message + run_all/plot_all skip on zero coverage"
```

---

## Task 8: `TagAnalyzer` + `from_playlist` tags/genres columns

**Files:**
- Modify: `src/spotify_project/analyzer.py` — add `TagAnalyzer` class; extend `PlaylistAnalyzer.__init__` default analyzers list; extend `from_playlist` to materialize `tags` column.
- Modify: `tests/test_analyzer.py` — add `TagAnalyzer` tests.
- Modify: `tests/test_playlist_analyzer.py` — assert `tags` column in `from_playlist` output.

- [ ] **Step 1: Write the failing TagAnalyzer tests**

Append to `tests/test_analyzer.py`:
```python
def test_tag_analyzer_counts_tags_top_n() -> None:
    import pandas as pd
    from spotify_project.analyzer import TagAnalyzer

    df = pd.DataFrame({
        "tags": [
            ["rock", "indie", "british"],
            ["rock", "00s"],
            ["rock", "indie"],
            [],
        ],
        "duration_min": [3.5, 4.0, 3.0, 2.0],
    })
    result = TagAnalyzer(top_n=2).analyze(df)
    # Counts: rock=3, indie=2, british=1, 00s=1. Top-2: rock, indie.
    assert list(result["tag"]) == ["rock", "indie"]
    assert list(result["count"]) == [3, 2]


def test_tag_analyzer_coverage_counts_rows_with_any_tag() -> None:
    import pandas as pd
    from spotify_project.analyzer import TagAnalyzer

    df = pd.DataFrame({"tags": [["rock"], [], ["pop", "indie"], []]})
    n_data, n_total = TagAnalyzer().coverage(df)
    assert n_data == 2
    assert n_total == 4


def test_tag_analyzer_empty_df_returns_empty() -> None:
    import pandas as pd
    from spotify_project.analyzer import TagAnalyzer

    result = TagAnalyzer().analyze(pd.DataFrame())
    assert result.empty


def test_tag_analyzer_skips_with_zero_coverage_via_skip_message() -> None:
    from spotify_project.analyzer import TagAnalyzer
    assert TagAnalyzer.skip_message is not None
    assert "LASTFM_API_KEY" in TagAnalyzer.skip_message
```

- [ ] **Step 2: Write the failing from_playlist tags-column test**

Append to `tests/test_playlist_analyzer.py`:
```python
def test_from_playlist_materializes_tags_column() -> None:
    from spotify_project.analyzer import PlaylistAnalyzer
    from spotify_project.models import Artist, Playlist, Track

    artist = Artist(id="A1", name="Artist One", tags=("rock", "indie"))
    track = Track(
        id="T1",
        name="Track",
        artists=(artist,),
        album_name="Album",
        release_date="2020-01-01",
        duration_ms=200_000,
        explicit=False,
        added_at=None,
        is_local=False,
    )
    playlist = Playlist(
        id="P1", name="P", owner_display_name="", public=False,
        collaborative=False, description="", tracks=(track,),
    )
    pa = PlaylistAnalyzer.from_playlist(playlist)
    assert "tags" in pa.df.columns
    assert "genres" in pa.df.columns
    assert pa.df["tags"].iloc[0] == ["rock", "indie"]
    assert pa.df["genres"].iloc[0] == ["rock", "indie"]


def test_from_playlist_default_analyzers_include_tag_analyzer() -> None:
    from spotify_project.analyzer import PlaylistAnalyzer, TagAnalyzer
    pa = PlaylistAnalyzer.from_playlist(_empty_playlist())  # see helper below
    assert any(isinstance(a, TagAnalyzer) for a in pa.analyzers)


def _empty_playlist():
    from spotify_project.models import Playlist
    return Playlist(
        id="P", name="P", owner_display_name="", public=False,
        collaborative=False, description="", tracks=(),
    )
```

- [ ] **Step 3: Run tests to verify they fail**

```
.venv\Scripts\python.exe -m pytest tests/test_analyzer.py -v -k tag_analyzer
.venv\Scripts\python.exe -m pytest tests/test_playlist_analyzer.py -v -k from_playlist
```
Expected: ImportError on `TagAnalyzer` and KeyError on `tags` column.

- [ ] **Step 4: Add `TagAnalyzer` class**

In `src/spotify_project/analyzer.py`, add this private helper at module scope (near the existing `_get_coverage` / `_style_axes` helpers around line 26):
```python
def _top_n_from_list_column(df: pd.DataFrame, column: str, top_n: int, value_label: str) -> pd.DataFrame:
    """Frequency-count a DataFrame list-column and return the top N.

    Used by TagAnalyzer (column='tags') and GenreAnalyzer (column='genres')
    — both share the explode-and-group-by shape; only the column name and
    the output label differ.

    Args:
        df: Track-level DataFrame.
        column: Name of the list-valued column to count (e.g. 'tags' or 'genres').
        top_n: Number of rows to return.
        value_label: Output column name for the labels (e.g. 'tag' or 'genre').

    Returns:
        DataFrame with columns ``[value_label, 'count']``, descending count,
        limited to top_n rows. Empty DataFrame with the right columns when
        df is empty or the column is missing.
    """
    empty = pd.DataFrame({value_label: [], "count": []})
    if df.empty or column not in df.columns:
        return empty
    exploded = df.explode(column).dropna(subset=[column])
    if exploded.empty:
        return empty
    return (
        exploded.groupby(column, as_index=False)
        .size()
        .rename(columns={column: value_label, "size": "count"})
        .sort_values("count", ascending=False)
        .head(top_n)
        .reset_index(drop=True)
    )
```

Then add the `TagAnalyzer` class right above the existing `GenreAnalyzer` (so it precedes Genre in the file, matching the registration order):
```python
class TagAnalyzer(Analyzer):
    """Top Last.fm tags by track count.

    Tags are raw folksonomy: real genres alongside eras (``00s``), geography
    (``british``), behavior (``seen live``), sentiment (``favorite``). Useful
    as a complete view of how listeners describe these artists, and as a
    curation aid when refining the whitelist that drives GenreAnalyzer.

    Skipped by PlaylistAnalyzer.run_all when no track has any tag — typically
    because LASTFM_API_KEY is unset.

    Args:
        top_n: How many tags to return; default 15.
        title: Optional per-instance title override.
    """

    title = "Top Tags"
    skip_message = "no tag data — set LASTFM_API_KEY to enable."

    def __init__(self, top_n: int = 15, *, title: str | None = None) -> None:
        self.top_n = top_n
        self._instance_title = title

    def coverage(self, df: pd.DataFrame) -> tuple[int, int]:
        """Count rows whose ``tags`` list is non-empty."""
        if df.empty or "tags" not in df.columns:
            return (0, len(df))
        n_with = int(df["tags"].apply(lambda t: bool(t) if isinstance(t, list) else False).sum())  # pyright: ignore[reportUnknownArgumentType, reportUnknownLambdaType]
        return (n_with, len(df))

    def analyze(self, df: pd.DataFrame) -> pd.DataFrame:
        """Count tag frequency across all tracks and return the top N.

        Args:
            df: Track-level DataFrame with a ``tags`` column (list-valued).

        Returns:
            DataFrame with columns ``tag`` and ``count``, descending count,
            limited to ``top_n`` rows.
        """
        result = _top_n_from_list_column(df, "tags", self.top_n, "tag")
        return self._attach_coverage(result, df)

    def plot(self, ax: Axes, summary: pd.DataFrame, *, color: _Color | None = None) -> None:
        """Render a horizontal bar chart of tag counts.

        Args:
            ax: Matplotlib Axes to draw on.
            summary: Output of ``analyze``; columns ``tag`` and ``count``.
            color: Bar color; defaults to the class's ``default_color``.
        """
        c = color if color is not None else self.default_color
        if summary.empty:
            ax.text(0.5, 0.5, "No tag data", ha="center", va="center")
            _style_axes(ax, self.effective_title, summary)
            return
        ax.barh(summary["tag"], summary["count"], color=c)
        ax.invert_yaxis()
        ax.set_xlabel("Track count")
        _style_axes(ax, self.effective_title, summary)
```

- [ ] **Step 5: Refactor `GenreAnalyzer.analyze` to reuse the helper**

In `src/spotify_project/analyzer.py`, find `GenreAnalyzer.analyze` (around line 151) and replace its body with:
```python
    def analyze(self, df: pd.DataFrame) -> pd.DataFrame:
        """Count genre frequency across all tracks and return the top N.

        Args:
            df: Track-level DataFrame with a ``genres`` column (list-valued).

        Returns:
            DataFrame with columns ``genre`` and ``count``, descending count,
            limited to ``top_n`` rows.
        """
        result = _top_n_from_list_column(df, "genres", self.top_n, "genre")
        return self._attach_coverage(result, df)
```

(`GenreAnalyzer.coverage` and `GenreAnalyzer.plot` stay as they are.)

- [ ] **Step 6: Update `PlaylistAnalyzer.from_playlist` to materialize the `tags` column**

In `src/spotify_project/analyzer.py`, find the row-building block in `from_playlist` (around line 590-608). Add one new key to the dict appended to `rows`:
```python
                    "tags": list(primary.tags) if primary else [],
```

Place it immediately before the existing `"genres": ...` line so the columns are grouped.

- [ ] **Step 7: Register `TagAnalyzer` in the default analyzer list**

In `PlaylistAnalyzer.__init__` (around line 552-563), update the default analyzer list to include `TagAnalyzer()` immediately after `GenreAnalyzer()`:
```python
            analyzers
            if analyzers is not None
            else [
                GenreAnalyzer(),
                TagAnalyzer(),
                YearAnalyzer(),
                ArtistAnalyzer(),
                DurationAnalyzer(),
                TimelineAnalyzer(),
            ]
```

- [ ] **Step 8: Run the new tests**

```
.venv\Scripts\python.exe -m pytest tests/test_analyzer.py tests/test_playlist_analyzer.py -v
```
Expected: new tests pass; existing tests still green.

- [ ] **Step 9: Run the full suite**

```
.venv\Scripts\python.exe -m pytest -v
```
Expected: all green.

- [ ] **Step 10: Lint and typecheck**

```
.venv\Scripts\python.exe -m ruff check src tests
.venv\Scripts\python.exe -m ruff format --check src tests
.venv\Scripts\python.exe -m pyright src tests
```
Expected: clean.

- [ ] **Step 11: Commit**

```
git add src/spotify_project/analyzer.py tests/test_analyzer.py tests/test_playlist_analyzer.py
git commit -m "add TagAnalyzer; materialize tags column in from_playlist"
```

---

## Task 9: Notebook wiring

**Files:**
- Modify: `notebooks/01_explore_user_account.ipynb` — add LastFmClient import, build it via `from_env`, pass to `SpotifyClient.from_env`.

This task has no automated tests (notebooks aren't unit-tested); verification is by running the notebook end-to-end with and without `LASTFM_API_KEY`.

- [ ] **Step 1: Locate the client-construction cell**

Open `notebooks/01_explore_user_account.ipynb` and find the cell that builds `SpotifyClient.from_env`. It currently looks something like:
```python
cache = FileCache()
client = SpotifyClient.from_env(cache=cache)
```

- [ ] **Step 2: Insert LastFmClient wiring**

Replace that cell's contents with:
```python
from spotify_project.cache import FileCache
from spotify_project.client import SpotifyClient
from spotify_project.lastfm_client import LastFmClient

cache = FileCache()
lastfm = LastFmClient.from_env(cache=cache)  # None when LASTFM_API_KEY is unset
client = SpotifyClient.from_env(cache=cache, genre_enricher=lastfm)
```

Don't remove the existing import section above this if there's one — only the construction lines need to change. If the existing cell imports `dotenv` and calls `load_dotenv()`, keep that call before the `LastFmClient.from_env` line so `LASTFM_API_KEY` is loaded from `.env`.

- [ ] **Step 3: Restart the kernel and run the notebook end-to-end with the key set**

(Manual step — runs in Jupyter UI.) Verify:
- No exceptions.
- The "Enriching with Last.fm tags" progress bar appears on first run; subsequent runs hit the cache and finish in seconds.
- `plot_all()` renders six panels: Top Genres, Top Tags, Release Year, Top Artists, Track Duration, Timeline.
- The Top Tags panel includes folksonomy entries (e.g. `british`, `00s`, `seen live`).
- The Top Genres panel shows the whitelisted subset.

- [ ] **Step 4: Test the no-key path**

Without restarting the venv, in a notebook cell:
```python
import os, importlib
os.environ.pop("LASTFM_API_KEY", None)
# Reimport to bypass dotenv side effects from earlier cells.
import spotify_project.lastfm_client as lfm; importlib.reload(lfm)

cache = FileCache()
lastfm = lfm.LastFmClient.from_env(cache=cache)
print("lastfm is:", lastfm)
```
Expected: prints `lastfm is: None` and the log shows the "Last.fm enrichment disabled" INFO line.

Then run the analysis pipeline with `genre_enricher=lastfm` (i.e. None) and confirm:
- Four panels render (Year / Artist / Duration / Timeline) instead of six.
- The log shows two INFO lines: one for Top Tags, one for Top Genres.
- No exceptions.

- [ ] **Step 5: Commit the notebook**

(Notebook outputs are usually committed for this project — keep them if the user has been doing so; otherwise clear outputs before committing per local convention.) Check `git diff --stat notebooks/`:
```
git diff --stat notebooks/01_explore_user_account.ipynb
git add notebooks/01_explore_user_account.ipynb
git commit -m "wire Last.fm enrichment into the user-account notebook"
```

---

## Task 10: README + CLAUDE.md updates

**Files:**
- Modify: `README.md` — add "Restoring genres (and adding tags) via Last.fm" subsection under the existing "Spotify Web API limitations" section.
- Modify: `CLAUDE.md` — update gotcha #3 to reflect tags-on-Artist + derived-genres model.

- [ ] **Step 1: Add the README section**

Open `README.md`, locate the `## Spotify Web API limitations` section (or whatever the existing heading is named — Phase 1 README should have one). Add this subsection at the end of it:
```markdown
### Restoring genres (and adding tags) via Last.fm

Genres are re-sourced from Last.fm's `artist.getTopTags` endpoint, and raw
tags are surfaced as a separate analysis:

- ~95% per-artist coverage for typical Spotify libraries (mainstream + indie).
- One-time enrichment cost: ~7 minutes for ~2000 unique artists.
- Cached for 365 days under `.cache/api/lastfm_artist/<spotify_artist_id>.json`.
- `Top Tags` panel: raw Last.fm tags (eras, geography, moods, real genres).
- `Top Genres` panel: tags filtered through a curated whitelist in
  `src/spotify_project/genre_taxonomy.py`. Whitelist edits take effect
  instantly — no re-enrichment needed.

**To enable Last.fm locally:** register at
<https://www.last.fm/api/account/create> and set `LASTFM_API_KEY` in `.env`.
The project runs fine without a Last.fm key — the `Top Tags` and `Top Genres`
panels are skipped with an INFO log line.

**Caveat:** Last.fm's audience skews Western and indie, so the tag
distribution is biased that way. For mainstream pop and indie rock the data
is excellent; for K-pop, classical, and very-niche electronic the tag set
is sparser and less precise.
```

- [ ] **Step 2: Update CLAUDE.md gotcha #3**

Open `CLAUDE.md`, find the gotcha that currently reads:
```
3. **Artist `genres` and track/artist `popularity` are silently absent.** ... `popularity` is removed from the codebase per the no-dead-API-code policy; `genres` stays as a field on `Artist` and will be re-sourced from Last.fm (see [Last.fm enrichment spec](docs/superpowers/specs/2026-05-11-lastfm-genre-enrichment.md)).
```

Replace the trailing clause about `genres` with:
```
`popularity` is removed from the codebase per the no-dead-API-code policy. `Artist` stores raw Last.fm tags in a `tags: tuple[str, ...]` field; `.genres` is a derived `@property` that filters those tags through a curated whitelist in `src/spotify_project/genre_taxonomy.py`. With no Last.fm key, `tags` stays empty, `.genres` returns `()`, and the `Top Tags` / `Top Genres` analyzer panels are skipped with an INFO log line.
```

Also update the "Project structure (proposed)" block in `CLAUDE.md` to list the two new modules under `src/spotify_project/`:
```
│       ├── genre_taxonomy.py   # GENRE_WHITELIST + filter_to_genres
│       ├── lastfm_client.py    # LastFmClient — optional Last.fm enrichment
```

(Place them in alphabetical order with the existing entries.)

- [ ] **Step 3: Sanity-check the rendered README locally if possible**

(Optional — Windows: open in VS Code's markdown preview.) No automated check.

- [ ] **Step 4: Commit**

```
git add README.md CLAUDE.md
git commit -m "document Last.fm tag enrichment in README and CLAUDE.md"
```

---

## Task 11: Final verification

**Files:** none (verification only).

- [ ] **Step 1: Full test suite**

```
.venv\Scripts\python.exe -m pytest -v
```
Expected: all tests green.

- [ ] **Step 2: Lint + format on the whole project**

```
.venv\Scripts\python.exe -m ruff check src tests
.venv\Scripts\python.exe -m ruff format --check src tests
```
Expected: clean.

- [ ] **Step 3: Pyright strict on the whole project**

```
.venv\Scripts\python.exe -m pyright src tests
```
Expected: clean.

- [ ] **Step 4: Sanity command from spec §1.3**

Run with `LASTFM_API_KEY` set in the environment (or after `.\.venv\Scripts\Activate.ps1` if needed):
```
.venv\Scripts\python.exe -c "import os, urllib.request, json, urllib.parse; key = os.environ['LASTFM_API_KEY']; url = 'https://ws.audioscrobbler.com/2.0/?method=artist.getTopTags&artist=' + urllib.parse.quote('Daft Punk') + '&api_key=' + key + '&format=json'; r = urllib.request.urlopen(url, timeout=10); d = json.loads(r.read()); print([t['name'] for t in d['toptags']['tag'][:5]])"
```
Expected: prints a list of 5 Daft Punk tags (e.g. `['electronic', 'french', 'house', 'dance', 'electronica']`).

- [ ] **Step 5: Notebook end-to-end (manual, with key)**

Restart the kernel, run all cells. Verify per Task 9 Step 3.

- [ ] **Step 6: Notebook end-to-end (manual, without key)**

In PowerShell:
```
Remove-Item Env:\LASTFM_API_KEY -ErrorAction SilentlyContinue
```
Restart the kernel, run all cells. Verify per Task 9 Step 4.

- [ ] **Step 7: Tag-cleaning iteration (optional)**

Run a notebook cell that prints the top-30 tags appearing in `df["tags"]` but **not** in `df["genres"]`. Review with the user, add legitimate genres to `GENRE_WHITELIST`, re-render `plot_all()`. No re-enrichment needed.

- [ ] **Step 8: Final `git diff` review with the user**

```
git log --oneline main..HEAD
git diff main HEAD -- src tests
```
User reviews. If anything looks off, fix and amend.

---

## Self-review against the spec

(Plan author's own check, not a separate phase.)

- **§1 prerequisites** — covered: spec section is unchanged by the plan; `.env.example` already updated in the spec-revision commit.
- **§2 success criteria** — covered: Tasks 1-8 deliver all listed items; verification in Task 11.
- **§3.1 Artist data model** — Task 2.
- **§3.2 genre_taxonomy** — Task 1.
- **§3.3 LastFmClient** — Tasks 3-5.
- **§3.4 SpotifyClient integration** — Task 6.
- **§3.5 Two analyzers** — Task 8.
- **§3.6 Skip behavior** — Task 7.
- **§3.7 DataFrame columns** — Task 8 Step 6.
- **§3.8 Notebook wiring** — Task 9.
- **§4 Data flow** — implicit; emerges from the combined tasks.
- **§5 Tag-cleaning workflow** — Task 11 Step 7.
- **§6 Test coverage** — all listed test files have tasks (test_lastfm_client.py: Tasks 3-5; test_genre_taxonomy.py: Task 1; test_models.py: Task 2; test_analyzer.py: Tasks 7, 8; test_client.py: Task 6).
- **§7 Documentation updates** — Task 10.
- **§8 Out of scope** — not in the plan, as intended.
- **§9 Verification checklist** — Task 11.

No placeholders; all code blocks contain the actual code or commands the engineer needs to type. Method/class names match across tasks (`LastFmClient.from_env`, `Artist.tags`, `Artist.genres`, `TagAnalyzer`, `GenreAnalyzer`, `Analyzer.skip_message`, `genre_enricher` param). Task ordering respects dependencies (taxonomy → Artist → LastFmClient core/errors/from_env → SpotifyClient wiring → skip mechanism → TagAnalyzer + columns → notebook → docs → verify).
