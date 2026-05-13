# Last.fm Tag Enrichment Spec

**Status:** Draft 2026-05-11. **Revised 2026-05-12** — major redesign: store raw Last.fm tags on `Artist` (not the whitelist-filtered subset), expose `genres` as a derived `@property`, add a `TagAnalyzer` alongside `GenreAnalyzer`, make Last.fm optional at runtime. Awaiting user approval after the revision.
**Predecessor:** [Deprecation Cleanup](2026-05-11-deprecation-cleanup.md) — must land first; this spec assumes `popularity` is already gone and `Artist.genres` is the empty-tuple field stripped by Spotify's deprecations.
**Goal:** Restore meaningful genre analysis and add tag analysis by sourcing per-artist tags from Last.fm, since Spotify's `genres` field on `GET /artists/{id}` is silently empty for apps registered after Nov 27 2024.

---

## 1. User prerequisites

### 1.1 Last.fm API account (recommended)

Last.fm enrichment is **optional at runtime**: if no key is configured the notebook runs unchanged, but the `Top Tags` and `Top Genres` panels are skipped (one log line each). To enable enrichment:

1. Open <https://www.last.fm/api/account/create>.
2. Log in with a regular Last.fm account (free; create one at <https://www.last.fm/join> if needed — no Spotify connection required).
3. Fill in the form:
   - **Application name:** `py_spotify_project` (or anything; only visible to you).
   - **Application description:** `Personal Spotify library analyzer — Last.fm enriches artist tags.`
   - **Callback URL:** leave blank.
   - **Application homepage:** leave blank or `https://github.com/<your-handle>/py_spotify_project`.
4. Submit. The page immediately shows the **API key** and a **Shared secret**. We only need the **API key** — `artist.getTopTags` is an unauthenticated read endpoint.
5. Free tier, no human review, no payment, generous rate limits (5 req/sec is fine).

### 1.2 Put the key into `.env`

Add to `.env` (gitignored):
```dotenv
LASTFM_API_KEY=<the-key-from-step-1.1>
```

`.env.example` already documents the variable.

### 1.3 Sanity check

From the project root (after activating venv):
```powershell
.venv\Scripts\python.exe -c "import os, urllib.request, json, urllib.parse; key = os.environ['LASTFM_API_KEY']; url = 'https://ws.audioscrobbler.com/2.0/?method=artist.getTopTags&artist=' + urllib.parse.quote('Daft Punk') + '&api_key=' + key + '&format=json'; r = urllib.request.urlopen(url, timeout=10); d = json.loads(r.read()); print([t['name'] for t in d['toptags']['tag'][:5]])"
```
Expected output (or similar): `['electronic', 'french', 'house', 'dance', 'electronica']`.

---

## 2. Goal & success criteria

By the end of this work, the notebook output gains two new panels (`Top Tags`, `Top Genres`) for users with a Last.fm key configured, and behaves unchanged for users without one. The implementation:

- Adds **one** new public API integration (Last.fm) — strengthens the rubric criterion "Internet data access — public API, programmatic".
- Adds **one** new concrete `Analyzer` subclass (`TagAnalyzer`) — strengthens the OOP criterion (`Analyzer` hierarchy grows from 5 → 6 concrete subclasses).
- Stores **raw** Last.fm tags on `Artist`; `Artist.genres` becomes a derived `@property` that filters via a curated whitelist. Whitelist edits take effect on next read — no re-fetch needed.
- Reuses the existing `FileCache` for Last.fm responses; one-time enrichment cost ~7 minutes for ~2000 artists, then cached for 365 days.
- **Never refetches Spotify data.** Existing `artist/<id>.json` cache entries are read-only; Last.fm tags are added in-memory after the Spotify side resolves.
- Stays within project style: strict types, docstrings on classes / non-trivial methods, no silent error swallowing, no dead-API code, no planning-phase references in code or config comments.

---

## 3. Architecture

### 3.1 `Artist` data model (`src/spotify_project/models.py`)

```python
@dataclass(slots=True, frozen=True)
class Artist:
    """A Spotify artist enriched with Last.fm tags.

    Attributes:
        id: Spotify artist ID.
        name: Display name.
        tags: Raw Last.fm tags (lowercased, descending weight). Empty when
            Last.fm enrichment is disabled or the artist is unknown to Last.fm.
    """

    id: str
    name: str
    tags: tuple[str, ...] = ()

    @property
    def genres(self) -> tuple[str, ...]:
        """Whitelist-filtered subset of tags, preserving descending-weight order.

        Recomputed on every access (cheap: a tuple comprehension over <=10 items).
        Whitelist edits are visible immediately without rebuilding Artist instances.
        """
        return tuple(filter_to_genres(self.tags))
```

Key points:
- `genres` is no longer a stored field — derived from `tags`.
- `Artist.from_api(spotify_data)` reads only `id` and `name`. The `data.get("genres", [])` line is removed (always empty for our app).
- Enrichment attaches tags via `dataclasses.replace(artist, tags=tuple(lowercased_tags))`.
- Default `tags=()` keeps existing test fixtures and any caller that constructs `Artist` directly without enrichment working unchanged.

### 3.2 New module: `src/spotify_project/genre_taxonomy.py`

A literal whitelist plus a thin filter function. Tags are lowercased upstream in `LastFmClient.fetch_artist_tags`, so the filter is a pure membership check — no normalization inside.

```python
GENRE_WHITELIST: frozenset[str] = frozenset({
    # ~100-200 entries; seeded with a defensible baseline of widely-recognized
    # music genres, then iteratively refined during the tag-cleaning session (§5).
    "rock", "pop", "indie", "indie pop", "indie rock", "alternative", "metal",
    "jazz", "blues", "soul", "funk", "r&b", "rap", "hip-hop", "hip hop",
    "electronic", "house", "techno", "trance", "ambient", "drum and bass",
    "classical", "soundtrack", "folk", "country", "reggae", "punk", "ska",
    "disco", "synthpop", "synthwave", "post-rock", "post-punk", "shoegaze",
    # ... filled in collaboratively during §5
})

def filter_to_genres(tags: tuple[str, ...]) -> list[str]:
    """Return the whitelisted subset of ``tags``, preserving input order.

    Args:
        tags: Lowercased tags in descending-weight order, as stored on Artist.

    Returns:
        A new list containing only the tags that appear in GENRE_WHITELIST.
    """
    return [t for t in tags if t in GENRE_WHITELIST]
```

`frozenset[str]` gives O(1) lookup, immutability, and accurate type info under pyright strict. Whitelist is **data, not behavior** — no unit-test surface beyond the filter itself.

### 3.3 New module: `src/spotify_project/lastfm_client.py`

```python
class LastFmClient:
    """Last.fm Web API client used to enrich Spotify artists with tags."""

    BASE_URL: ClassVar[str] = "https://ws.audioscrobbler.com/2.0/"
    RATE_LIMIT_DELAY_SECONDS: ClassVar[float] = 0.2   # ~5 req/sec
    CACHE_TTL_DAYS: ClassVar[float] = 365.0
    DEFAULT_TOP_N: ClassVar[int] = 10

    def __init__(self, api_key: str, cache: FileCache) -> None: ...

    @classmethod
    def from_env(cls, cache: FileCache) -> LastFmClient | None:
        """Build from LASTFM_API_KEY.

        Returns:
            A configured LastFmClient, or None when LASTFM_API_KEY is unset
            or empty. Logs one INFO line in the None case ("Last.fm enrichment
            disabled — set LASTFM_API_KEY to enable. Tag/Genre panels will
            be skipped."). Caller-side optionality: the notebook passes the
            result through to ``SpotifyClient(genre_enricher=...)``, which
            already accepts ``LastFmClient | None``.
        """

    def fetch_artist_tags(
        self,
        spotify_artist_id: str,
        artist_name: str,
        *,
        force_refresh: bool = False,
    ) -> tuple[str, ...]:
        """Return the top-N Last.fm tags for an artist, lowercased and in
        descending-weight order.

        Cached as ``lastfm_artist/<spotify_artist_id>.json`` (keyed by Spotify ID
        so two Last.fm artists with the same name don't collide). ``autocorrect=1``
        is sent on the request so misspellings still match the canonical artist.

        Lowercasing happens here (once) — downstream code (Artist, filter,
        analyzers) assumes tags are already lowercase.
        """
```

Implementation notes:
- stdlib `urllib.request` — no new dependency. Single GET per artist with three query params.
- `timeout=10` on every URL open.
- Last.fm returns HTTP 200 with `{"error": <code>, "message": "..."}` body on failures. Check the `error` key, not just HTTP status.
- "Artist not found" (code 6) → return `()`, log a warning, don't raise. A small number of misses are visible but not fatal.
- Rate-limit (code 29) → sleep then retry once; if it persists, raise so the enrichment loop fails fast. Consistent with "don't suppress errors silently".
- Other documented errors → raise. Surface clearly.

### 3.4 Integration: `SpotifyClient`

```python
class SpotifyClient:
    def __init__(
        self,
        sp: spotipy.Spotify,
        cache: FileCache,
        genre_enricher: LastFmClient | None = None,
    ) -> None:
        self.sp = sp
        self.cache = cache
        self.genre_enricher = genre_enricher

    def _enrich_with_artists(
        self,
        track_items: list[dict[str, Any]],
        *,
        force_refresh: bool = False,
    ) -> list[Track]:
        # ... existing code resolves artist_by_id from cached Spotify data ...

        if self.genre_enricher is not None:
            enriched: dict[str, Artist] = {}
            iter_artists: Iterable[Artist] = _tqdm_cls(
                artist_by_id.values(),
                desc="Enriching with Last.fm tags",
                unit="artist",
            )
            for artist in iter_artists:
                tags = self.genre_enricher.fetch_artist_tags(artist.id, artist.name)
                enriched[artist.id] = replace(artist, tags=tags)
            artist_by_id = enriched

        return [Track.from_api(item, artist_by_id) for item in audio_tracks]
```

- **Spotify cache is read-only here.** The Last.fm loop runs *after* the Spotify-side resolution completes (cache hit or otherwise) and only modifies the in-memory `artist_by_id` dict.
- `from_env(cache, scopes=None)` gains an optional `genre_enricher` param and forwards it to `__init__`. Notebook callers pass `genre_enricher=lastfm` where `lastfm: LastFmClient | None`.
- When `genre_enricher is None`, the loop is skipped → behavior identical to today.

### 3.5 Two analyzers (`src/spotify_project/analyzer.py`)

`TagAnalyzer` is new; `GenreAnalyzer` is modified to read the `genres` column (still populated from `Artist.genres`).

```python
class TagAnalyzer(Analyzer):
    """Top Last.fm tags by track count.

    Tags include all folksonomy: real genres alongside eras (``00s``), geography
    (``british``), behavior (``seen live``), sentiment (``favorite``). Useful as a
    raw view of the library and as a curation aid for the whitelist that drives
    GenreAnalyzer.
    """

    title = "Top Tags"

    def __init__(self, top_n: int = 15, *, title: str | None = None) -> None: ...

    def coverage(self, df: pd.DataFrame) -> tuple[int, int]:
        """Count rows whose ``tags`` list is non-empty."""

    def analyze(self, df: pd.DataFrame) -> pd.DataFrame:
        """Count tag frequency over df['tags'] and return the top N."""

    def plot(self, ax: Axes, summary: pd.DataFrame, *, color: _Color | None = None) -> None:
        """Render a horizontal bar chart of tag counts."""


class GenreAnalyzer(Analyzer):
    """Top whitelist-filtered genres by track count.

    Reads df['genres'] (whitelist-filtered subset of tags), same shape as
    TagAnalyzer but with the curated vocabulary applied upstream. Behaves
    identically to the original GenreAnalyzer; only the underlying column
    is now populated from Last.fm tags rather than Spotify's empty field.
    """

    title = "Top Genres"
    # analyze() / plot() / coverage() unchanged from current implementation
```

Both inherit from `Analyzer`, both override `analyze`/`plot`/`coverage` — real polymorphism, visible in `PlaylistAnalyzer.run_all()`. A small module-level helper `_top_n_from_list_column(df, column, top_n)` is shared by both `analyze` methods to avoid line-for-line duplication. The default analyzer registration in `PlaylistAnalyzer.__init__` adds `TagAnalyzer()` before `YearAnalyzer()`, giving six concrete subclasses total.

### 3.6 Skip behavior in `PlaylistAnalyzer`

The base `Analyzer` already has `coverage(df) -> (n_data, n_total)`. We add an optional class-level attribute:

```python
class Analyzer(ABC):
    skip_message: ClassVar[str | None] = None  # opt-in skip hint; None = always run

class TagAnalyzer(Analyzer):
    skip_message = "no tag data. Set LASTFM_API_KEY to enable."

class GenreAnalyzer(Analyzer):
    skip_message = "no genres after whitelist filtering. Set LASTFM_API_KEY or extend GENRE_WHITELIST."
```

`PlaylistAnalyzer.run_all()` and `plot_all()` check coverage before invoking `analyze`/`plot`:

```python
def run_all(self) -> dict[str, pd.DataFrame]:
    out: dict[str, pd.DataFrame] = {}
    for a in self.analyzers:
        n_data, _ = a.coverage(self.df)
        if n_data == 0 and a.skip_message is not None:
            logger.info("Skipping %s: %s", a.effective_title, a.skip_message)
            continue
        out[a.effective_title] = a.analyze(self.df)
    return out
```

`plot_all` mirrors the same skip and uses only the surviving analyzers when sizing the subplot grid. Without a Last.fm key, four panels render instead of six and the user sees two `INFO` lines.

Analyzers without `skip_message` (the default) always run, even at zero coverage — they fall back to their existing "no data" placeholder text in `plot`. This keeps existing analyzers' behavior unchanged.

### 3.7 DataFrame columns (`PlaylistAnalyzer.from_playlist`)

Two new flattened columns derived from `primary_artist`:

| Column | Source | Existing? |
|---|---|---|
| `tags` | `list(primary.tags)` if primary else `[]` | new |
| `genres` | `list(primary.genres)` if primary else `[]` | was already there, now actually populated |

### 3.8 Notebook wiring

```python
from spotify_project.cache import FileCache
from spotify_project.client import SpotifyClient
from spotify_project.lastfm_client import LastFmClient

cache = FileCache()
lastfm = LastFmClient.from_env(cache=cache)            # LastFmClient | None
client = SpotifyClient.from_env(cache=cache, genre_enricher=lastfm)
```

`lastfm` is `LastFmClient | None`; `genre_enricher=None` flows through cleanly. Three lines, identical regardless of whether the user has a Last.fm key.

---

## 4. Data flow

```
fetch_liked_songs()
  ├─ paginate Spotify /me/tracks         (cached: liked/me.json)
  ├─ _enrich_with_artists()
  │    ├─ collect unique artist IDs
  │    ├─ fetch_artists()                (cached: artist/<id>.json — Spotify side, read-only)
  │    └─ if genre_enricher:
  │         for each artist (tqdm):
  │           tags = lastfm.fetch_artist_tags(id, name)
  │                                      (cached: lastfm_artist/<spotify_id>.json)
  │           artist = replace(artist, tags=tags)
  └─ build Track objects from enriched artist_by_id

PlaylistAnalyzer.from_playlist(playlist)
  └─ flatten to rows with columns: ..., tags, genres
       (tags from primary.tags; genres from primary.genres @property)

PlaylistAnalyzer.run_all() / .plot_all()
  └─ for each analyzer:
       check coverage; skip + log if (n_data == 0 and skip_message)
```

"Spotify gives us id + name → Last.fm gives us raw tags → Artist stores tags, derives genres on read → Track holds Artist reference → DataFrame carries `tags` and `genres` columns → TagAnalyzer + GenreAnalyzer produce charts."

---

## 5. Tag-cleaning workflow (joint user + AI session)

Materially better than the original whitelist-at-fetch design: iteration is seconds, not minutes, because no re-enrichment is needed when the whitelist changes.

1. **Seed the whitelist** with the baseline (§3.2). Run the notebook once — enrichment is one-time (~7 min wall-clock for ~2000 artists), then cached for 365 days.
2. **Compare panels.** `Top Tags` shows the top-N raw tags; `Top Genres` shows the whitelisted subset. Anything frequent in Tags but missing from Genres is a curation candidate.
3. **Optional: dump unrecognized-but-frequent tags.** A short notebook cell prints the top-N tags that survived `fetch_artist_tags` but were filtered out by `filter_to_genres`. Sample:
   ```
   british          580
   00s              412
   seen live        388
   chill            301
   ```
4. **Review together.** Decide per tag: keep (real genre → add to `GENRE_WHITELIST`) or drop (era / country / behavior / sentiment).
5. **Re-render `plot_all()`.** Genre panel reflects the new vocabulary instantly. No re-enrichment. Tags panel is unchanged (raw data doesn't depend on the whitelist).
6. **Commit final whitelist.** Done.

Total curating effort: ~20-30 minutes across one or two iterations.

---

## 6. Test coverage

`tests/test_lastfm_client.py` (new):
- Mocked HTTP: 200 with typical `getTopTags` JSON body → expected `tuple[str, ...]` (lowercased, descending weight).
- Mocked HTTP: 200 with `{"error": 6, "message": "artist not found"}` → returns `()`, emits a single warning, no raise.
- Mocked HTTP: 200 with `{"error": 29}` (rate limit) → one retry, then raise on persistence.
- Cache round-trip: first call fetches, second call (within TTL) does not call `urlopen`.
- `from_env` with no `LASTFM_API_KEY` → returns `None`, logs one INFO line.

`tests/test_genre_taxonomy.py` (new):
- `filter_to_genres(("rock", "seen live", "indie", "british"))` → `["rock", "indie"]` (whitelist-filtered, order preserved).
- `filter_to_genres(())` → `[]`.

`tests/test_models.py` (extend):
- `Artist(id="x", name="y", tags=("rock", "seen live"))` → `.genres == ("rock",)`.
- `Artist(id="x", name="y")` (default `tags=()`) → `.genres == ()`.

`tests/test_analyzer.py` (extend):
- `TagAnalyzer.analyze` on a df with `tags` lists → correct top-N counts.
- `GenreAnalyzer.analyze` reads `genres` column → correct top-N counts (unchanged in shape from current test).
- `PlaylistAnalyzer.run_all()` with all-empty `tags` & `genres` → result dict excludes "Top Tags" and "Top Genres"; other analyzers still present; INFO lines logged.
- `plot_all` on the same df → renders 4 panels, not 6.

`tests/test_client.py` (extend):
- `_enrich_with_artists` with a mocked `genre_enricher` → resulting `Artist.tags` populated as expected; Spotify side hits cache only (no Spotify API call when artist is cached).
- Same with `genre_enricher=None` → tags stay empty, no Last.fm calls attempted.

Total: ~10 new test cases, well above the rubric floor.

---

## 7. Documentation updates

### `README.md`

Add to the existing `## Spotify Web API limitations` section:

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

### `CLAUDE.md`

The existing gotchas line `genres stays as a field on Artist and will be re-sourced from Last.fm` becomes stale once implementation lands. Update it then to: `Artist stores raw Last.fm tags; .genres is a derived property over a curated whitelist.` Per the project rule, this CLAUDE.md edit ships **with the implementation PR**, not with the spec.

---

## 8. Out of scope (deferred / not doing)

- **Per-track genre lookup** (Last.fm `track.getTopTags`). Coverage is much worse at the track level; artist-level is the right grain for "what's in my library" analyses. Documented as a future stretch.
- **MusicBrainz fallback.** Live probe on 2026-05-11 showed 2 of 5 calls timing out; throughput + reliability are not worth the marginal cleanup. Documented as not-doing.
- **ISRC-based MusicBrainz cross-reference for tracks.** Future-proofing — track payloads still contain ISRCs, so this path stays open if per-track genres become valuable later.
- **TheAudioDB / Discogs.** Smaller upside than Last.fm; not pursued.
- **Last.fm `playcount` / `listeners` as a popularity proxy.** Discussed and explicitly rejected — popularity not interesting enough to be worth restoring under a different name.
- **Concurrency in the enrichment loop.** A serial 0.2s loop completes 2000 artists in ~7 minutes; a threadpool would shave it to ~1 minute but adds complexity (rate-limit coordination, tqdm thread-safety). Not worth it.
- **Auto-disambiguating Last.fm name collisions.** A small `MANUAL_OVERRIDES: dict[spotify_artist_id, tuple[str, ...]]` map can handle edge cases organically; we'll add entries as we see them. Out of scope for the first implementation pass.
- **Parameterized single analyzer (one class, column-as-arg).** Considered and rejected in favor of two concrete subclasses, to keep the OOP rubric defense visible.

---

## 9. Verification checklist (run before declaring done)

- [ ] `ruff check src tests` clean.
- [ ] `ruff format --check src tests` clean.
- [ ] `pyright` strict-mode clean (no new per-file ignores beyond the existing ones).
- [ ] `pytest` passes; new tests cover `LastFmClient` (success / not-found / rate-limit / cache / no-key), `filter_to_genres`, `Artist.genres` property, two analyzers, and the skip behavior in `run_all` / `plot_all`.
- [ ] Sanity command from §1.3 still returns expected tags.
- [ ] Notebook re-executed end-to-end with Last.fm key set: `Top Tags` and `Top Genres` panels both render with ≥ 85% coverage; tags panel includes folksonomy, genres panel is clean.
- [ ] Notebook re-executed end-to-end with no Last.fm key (PowerShell: `Remove-Item Env:\LASTFM_API_KEY -ErrorAction SilentlyContinue` then restart the kernel; or temporarily blank it in `.env`): four panels render (Year / Artist / Duration / Timeline); INFO log lines visible for skipped Tag / Genre panels; no exceptions.
- [ ] Tag-cleaning iteration complete; the "unrecognized but frequent tags" cell shows mostly long-tail / one-off junk.
- [ ] README's `Restoring genres (and adding tags) via Last.fm` section present.
- [ ] CLAUDE.md gotchas updated to reflect the new `Artist.tags` + `genres` property model.
- [ ] `.env.example` documents `LASTFM_API_KEY` (already done).
- [ ] `git diff` reviewed by user.

---

## 10. Estimated effort

- New code (`LastFmClient`, `genre_taxonomy`, `Artist` change, `SpotifyClient` wiring, `TagAnalyzer`, skip plumbing): ~2.5 hours.
- Tests: ~45-60 min.
- One-time enrichment run + tag-cleaning iteration: ~45 min wall-clock (mostly waiting for Last.fm + curating).
- README + CLAUDE.md + spec sign-off: ~20 min.

**Total: ~4 hours, one focused session.**
