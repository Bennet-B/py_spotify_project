# Last.fm Genre Enrichment Spec

**Status:** Draft 2026-05-11. Awaiting user approval. Execution **blocked on user prerequisites** (§1). Should be started in a **new chat session** once prerequisites are complete, with this spec as the briefing document.
**Predecessor:** [Deprecation Cleanup](2026-05-11-deprecation-cleanup.md) — must land first; this spec assumes `popularity` is already gone and `Artist.genres` is the empty-tuple field stripped by Spotify's deprecations.
**Goal:** Restore the `GenreAnalyzer` to producing meaningful output by sourcing per-artist genre tags from Last.fm, since Spotify's `genres` field on `GET /artists/{id}` is silently empty for apps registered after Nov 27 2024.

---

## 1. User prerequisites (BLOCKING — do these before starting Phase 2)

### 1.1 Create a Last.fm API account

1. Open <https://www.last.fm/api/account/create>.
2. Log in with a regular Last.fm account (free; create one at <https://www.last.fm/join> if needed — no Spotify connection required).
3. Fill in the form:
   - **Application name:** `py_spotify_project` (or anything; only visible to you)
   - **Application description:** `Personal Spotify library analyzer — Last.fm enriches artist genre tags.`
   - **Callback URL:** leave blank.
   - **Application homepage:** leave blank or `https://github.com/<your-handle>/py_spotify_project`.
4. Submit. The page immediately shows the **API key** and a **Shared secret**. We only need the **API key** — `getTopTags` is an unauthenticated read endpoint, so the shared secret is not required.
5. Free tier, no human review, no payment, generous rate limits (5 req/sec is fine).

### 1.2 Put the key into `.env`

Add to `.env` (gitignored):
```dotenv
LASTFM_API_KEY=<the-key-from-step-1.1>
```

And add a documenting placeholder to `.env.example` (committed):
```dotenv
LASTFM_API_KEY=
```

### 1.3 Sanity check

From the project root (after activating venv):
```powershell
.venv\Scripts\python.exe -c "import os, urllib.request, json, urllib.parse; key = os.environ['LASTFM_API_KEY']; url = 'https://ws.audioscrobbler.com/2.0/?method=artist.getTopTags&artist=' + urllib.parse.quote('Daft Punk') + '&api_key=' + key + '&format=json'; r = urllib.request.urlopen(url, timeout=10); d = json.loads(r.read()); print([t['name'] for t in d['toptags']['tag'][:5]])"
```
Expected output (or similar): `['electronic', 'french', 'house', 'dance', 'electronica']`. If you see that, Phase 2 is unblocked.

---

## 2. Goal & success criteria

By the end of Phase 2, the notebook output for `Top Genres` shows a meaningful top-15 chart for the user's library (~90% coverage expected). The implementation:

- Adds **one** new public API integration (Last.fm) — **strengthens the rubric** (criterion: "Internet data access — public API, programmatic") rather than weakening it.
- Reuses the existing `FileCache` for Last.fm responses; one-time enrichment cost ~7 minutes for ~2000 artists, then cached for 365 days.
- Keeps `GenreAnalyzer` unchanged — it already reads `df["genres"]` lists, so the change is purely upstream.
- Stays within the project's style rules (strict types, docstrings on classes / non-trivial methods, no silent error swallowing, no dead-API code).

---

## 3. Architecture

### 3.1 New module: `src/spotify_project/lastfm_client.py`

A focused client that mirrors `SpotifyClient`'s shape (constructor takes a `FileCache`; `from_env` factory; per-artist cache key).

```python
class LastFmClient:
    """Last.fm Web API client used to enrich Spotify artists with genre tags."""

    BASE_URL: ClassVar[str] = "https://ws.audioscrobbler.com/2.0/"
    RATE_LIMIT_DELAY_SECONDS: ClassVar[float] = 0.2  # ≈ 5 req/sec
    CACHE_TTL_DAYS: ClassVar[float] = 365.0          # Last.fm tags drift slowly; long TTL is safe
    DEFAULT_TOP_N: ClassVar[int] = 10                # Pull top-N tags per artist; whitelist trims further downstream

    def __init__(self, api_key: str, cache: FileCache) -> None: ...

    @classmethod
    def from_env(cls, cache: FileCache) -> "LastFmClient": ...
        # Reads LASTFM_API_KEY; fails loud (RuntimeError) if missing — same pattern as SpotifyClient.from_env.

    def fetch_artist_tags(
        self,
        spotify_artist_id: str,
        artist_name: str,
        *,
        force_refresh: bool = False,
    ) -> list[str]:
        """Return the top-N raw Last.fm tags for an artist, in descending weight order.

        Cached as `lastfm_artist/<spotify_artist_id>.json` (keyed by Spotify ID so two
        Last.fm artists with the same name don't collide). `autocorrect=1` is sent on the
        request so misspellings still match the canonical artist."""
```

Implementation notes:
- Use stdlib `urllib.request` — no new dependency. Our usage is one GET per artist with three query params; `requests` would be overkill.
- Always include `timeout=10` on the URL open (per global style memory).
- Handle the documented error shapes: Last.fm returns HTTP 200 with `{"error": <code>, "message": "..."}` JSON body on failures. We must check for the `error` key, not just the HTTP status.
- On a "no such artist" error (code 6), return `[]` and **log a warning** so a small number of misses are visible; don't raise.
- On rate-limiting (code 29), backoff and retry once; if it persists, raise so the enrichment loop fails fast (consistent with "don't suppress errors silently").

### 3.2 New module: `src/spotify_project/genre_taxonomy.py`

A literal whitelist plus a filter function:

```python
GENRE_WHITELIST: frozenset[str] = frozenset({
    # ~100-200 entries; seeded with a defensible baseline of widely-recognized
    # music genres, then iteratively refined during the tag-cleaning session (§5).
    "rock", "pop", "indie", "indie pop", "indie rock", "alternative", "metal",
    "jazz", "blues", "soul", "funk", "r&b", "rap", "hip-hop", "hip hop",
    "electronic", "house", "techno", "trance", "ambient", "drum and bass",
    "classical", "soundtrack", "folk", "country", "reggae", "punk", "ska",
    "disco", "synthpop", "synthwave", "post-rock", "post-punk", "shoegaze",
    # … filled in collaboratively (§5)
})

def filter_to_genres(raw_tags: list[str]) -> list[str]:
    """Lowercase + whitelist-filter, preserving Last.fm's descending-weight order."""
    return [t for t in (tag.lower().strip() for tag in raw_tags) if t in GENRE_WHITELIST]
```

The whitelist is **data, not behavior** — short module, no logic to test beyond the filter function itself.

### 3.3 Integration point: `SpotifyClient._enrich_with_artists`

The cleanest injection is an **optional** `genre_enricher` on `SpotifyClient`:

```python
class SpotifyClient:
    def __init__(
        self,
        sp: spotipy.Spotify,
        cache: FileCache,
        genre_enricher: LastFmClient | None = None,
    ) -> None: ...
```

When `genre_enricher` is set, `_enrich_with_artists` runs Last.fm lookup + taxonomy filter against each artist *after* the Spotify artist fetch, and produces `Artist` instances whose `genres` tuple is populated.

Because `Artist` is `frozen=True`, this means constructing a new `Artist` per enrichment via `dataclasses.replace(artist, genres=tuple(filtered_tags))`. The `artist_by_id` dict is then rebuilt before `Track.from_api` runs, so resulting `Track.primary_artist.genres` is already populated by the time `PlaylistAnalyzer.from_playlist` flattens the rows.

Optionality matters: `SpotifyClient` stays usable without a Last.fm key (e.g., in CI tests). Pass `genre_enricher=None` and `Artist.genres` is empty — identical to today's behavior.

### 3.4 Notebook wiring

```python
from spotify_project.lastfm_client import LastFmClient

cache = FileCache()
lastfm = LastFmClient.from_env(cache=cache)
client = SpotifyClient.from_env(cache=cache, genre_enricher=lastfm)
```

That's the entire notebook delta. Everything downstream — `fetch_liked_songs`, `PlaylistAnalyzer.from_playlist`, `GenreAnalyzer` — sees the new genre data automatically.

---

## 4. Data flow

```
fetch_liked_songs()
  ├─ paginate Spotify /me/tracks         (cached: liked/me.json)
  ├─ _enrich_with_artists()
  │    ├─ collect unique artist IDs
  │    ├─ fetch_artists()                (cached: artist/<id>.json — Spotify shell, no genres)
  │    └─ if genre_enricher:             ← NEW
  │         for each artist:
  │           tags = lastfm.fetch_artist_tags(id, name)
  │                                      (cached: lastfm_artist/<spotify_id>.json)
  │           filtered = filter_to_genres(tags)
  │           artist = dataclasses.replace(artist, genres=tuple(filtered))
  └─ build Track objects from enriched artist_by_id
```

The chain is "Spotify gives us a name + ID → Last.fm gives us tags → taxonomy gives us a clean genre list → Artist stores them → Track holds a reference → DataFrame `genres` column carries them → `GenreAnalyzer` produces the chart."

---

## 5. Tag-cleaning workflow (joint user + AI session)

Run after `LastFmClient` is implemented, before declaring `GENRE_WHITELIST` final.

1. **Seed the whitelist** with the baseline (§3.2). Run the enrichment notebook once.
2. **Dump unrecognized tags.** A short cell in the notebook prints the top-N most frequent *unrecognized* tags (i.e. Last.fm tags that survived `fetch_artist_tags` but were dropped by `filter_to_genres`). Sample:
   ```
   british          580
   00s              412
   seen live        388
   chill            301
   ...
   ```
3. **Review together.** User + AI scan the list, decide for each:
   - keep (real genre, e.g. `jangle pop`) → add to `GENRE_WHITELIST`
   - drop (era / country / behavior / sentiment) → leave out
4. **Re-run notebook.** Coverage and chart improve. Repeat 2-3 once more if still noisy.
5. **Commit final whitelist.** Done.

Total expected curating effort: ~30 minutes across one or two iterations.

---

## 6. Test coverage

`tests/test_lastfm_client.py` (new):
- Mocked HTTP: a 200 response with a typical `getTopTags` JSON body returns the expected `list[str]` in descending order.
- Mocked HTTP: a 200 response with `{"error": 6, "message": "artist not found"}` returns `[]` and emits a single warning.
- Cache round-trip: first call fetches, second call (within TTL) does not call `urlopen`.

`tests/test_genre_taxonomy.py` (new):
- `filter_to_genres(["Rock", "seen live", "INDIE", "british"])` → `["rock", "indie"]` (case-folded, whitelist-filtered, order preserved).

`tests/test_client.py` (extend):
- An existing test exercises `_enrich_with_artists` with a mocked Spotify side. Add a variant that passes a mocked `genre_enricher` and asserts the resulting `Artist.genres` is populated as expected.

Test count stays well above the rubric floor.

---

## 7. README updates

Add to the existing `## Spotify Web API limitations` section (created in Phase 1):

```markdown
### Restoring genres via Last.fm

Genres are re-sourced from Last.fm's `artist.getTopTags` endpoint:

- ~95% per-artist coverage for typical Spotify libraries (mainstream + indie).
- One-time enrichment cost: ~7 minutes for ~2000 unique artists.
- Cached for 365 days under `.cache/api/lastfm_artist/<spotify_artist_id>.json`.
- Tags are filtered through a curated whitelist (`src/spotify_project/genre_taxonomy.py`)
  to drop non-genre folksonomy noise (`seen live`, `british`, `00s`, `favorite`, …).

**To enable Last.fm enrichment locally:** see `docs/superpowers/specs/2026-05-11-lastfm-genre-enrichment.md` §1 ("User prerequisites"). The project runs fine without a Last.fm key — you just get empty `GenreAnalyzer` output, as in Phase 1's interim state.

**Caveat:** Last.fm is a Western, indie-leaning audience, so the tag distribution is biased that way. For mainstream pop and indie rock the data is excellent; for K-pop, classical, and very-niche electronic the tag set is sparser and less precise.
```

---

## 8. Out of scope (deferred / not doing)

- **Per-track genre lookup** (Last.fm `track.getTopTags`). Coverage is much worse at the track level; artist-level is the right grain for "what's in my library" analyses. Documented as a future stretch.
- **MusicBrainz fallback.** Live probe on 2026-05-11 showed 2 of 5 calls timing out; throughput + reliability are not worth the marginal genre-vocabulary cleanup, especially given the whitelist already controls vocabulary. Documented as not-doing.
- **ISRC-based MusicBrainz cross-reference for tracks.** Future-proofing — track payloads still contain ISRCs, so this path stays open if per-track genres become valuable later.
- **TheAudioDB / Discogs.** Smaller upside than Last.fm; not pursued.
- **Last.fm `playcount`/`listeners` as a popularity proxy.** Discussed and explicitly rejected by user — popularity not interesting enough to be worth restoring under a different name.
- **Concurrency in the enrichment loop.** A serial 0.2s loop completes 2000 artists in ~7 minutes; threadpool would shave it to ~1 minute but adds complexity (rate-limit coordination, tqdm thread-safety). Not worth it.
- **Auto-disambiguating Last.fm name collisions.** Manual `MANUAL_OVERRIDES: dict[spotify_artist_id, list[str]]` map handles the ~10-30 edge cases organically; we'll add entries as we see them.

---

## 9. Verification checklist (run before declaring done)

- [ ] `ruff check src tests` clean.
- [ ] `ruff format --check src tests` clean.
- [ ] `pyright` strict-mode clean (no per-file ignores beyond the existing ones).
- [ ] `pytest` passes; new tests cover `LastFmClient` (success + not-found + cache) and `filter_to_genres`.
- [ ] Sanity command from §1.3 still returns expected tags.
- [ ] Notebook re-executed end-to-end. `Top Genres` panel now shows a real top-15 distribution with ≥ 85% coverage.
- [ ] Tag-cleaning iteration complete; the "unrecognized tags" notebook cell shows mostly long-tail / one-off junk and < 5% of tracks contributing to drop-only categories.
- [ ] README's "Restoring genres via Last.fm" section present.
- [ ] `.env.example` documents `LASTFM_API_KEY`.
- [ ] `git diff` reviewed by user.

---

## 10. Estimated effort

- New code (`LastFmClient`, `genre_taxonomy`, `SpotifyClient` wiring): ~2 hours.
- Tests: ~30-45 min.
- One-time enrichment run + tag-cleaning iteration: ~45 min wall-clock (mostly waiting for Last.fm fetch + curating).
- README + spec sign-off: ~15 min.

**Total: ~3.5 hours, all in one focused session.**
