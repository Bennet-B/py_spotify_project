# py_spotify_project

A Python toolkit for analyzing your own Spotify account: playlists, genres, listening history, track ages, and more — built as the **INFPROG2 FS26 semester project** (ZHAW).

The repo will grow in two phases:

1. **A Jupyter notebook** that authenticates you, pulls your playlists, and produces a stack of charts and stats about them.
2. **A small web UI** (Streamlit or FastAPI — TBD) that does the same interactively, plus playlist organization features: split, merge, dedupe, re-sort.

## A note about the Spotify Web API in 2026 — what happened and why it shaped this codebase

This is a quick history of constraints, not just a list of missing features. Each cutback changed how the code had to be written.

### The timeline

**November 2024** — Spotify removed the richest analysis endpoints for any developer app registered from that point on:

- `audio-features` — danceability, energy, valence, tempo, key, acousticness, instrumentalness, loudness, etc.
- `audio-analysis` — bar / beat / segment-level structural data
- `recommendations` — "give me tracks like these"
- `related-artists`
- featured / category playlists, genre seeds

Apps grandfathered before that date kept access, but we're a new app, so these return `403 Forbidden`.

**February 2026** — Spotify removed the batch-artists endpoint (`GET /artists?ids=...`) for new apps. What had been a single round-trip for a whole playlist's worth of artists became **one HTTP call per artist**. A 3 000-track library can reference 2 000+ unique artists; at one request per artist the naive approach would be extremely slow.

### How the cutbacks shaped the design

**Caching became load-bearing, not nice-to-have.**
Before the Feb 2026 change, artist data was cheap — one call, all artists. Now every uncached artist costs a real API round-trip. `FileCache` stores each artist for 365 days so the per-artist cost is paid once and amortized over an entire year of notebook runs.

**Rate limits are now the binding constraint.**
With one request per artist, the client must throttle. Artist fetches are spaced 250 ms apart (~4 req/s) to stay well inside Spotify's rolling-window rate limit. The progress bar (via `tqdm` if installed) and INFO log lines exist specifically because fetching a fresh playlist with 500+ unique artists takes over two minutes — without feedback the notebook would look frozen.

**Genre data moved up one level.**
Spotify has never exposed genre at the track level. Genres live on the *artist* object. To report a track's genre we look up its primary artist and pull genres from there. This is the only source available.

### What this means for the codebase

We do not implement endpoints we cannot exercise. There is no `get_audio_features()` method, no `recommendations()` method, no `related_artists()` method anywhere in `src/spotify_project/`. We did not add try/catch wrappers, feature flags, or "if available" branches for these features either. **Untested code is technical debt the moment it lands**, so we keep the codebase clean and document the constraint here once. If Spotify ever restores access (or we get a grandfathered app), adding the code is a small follow-up; until then it would be code we cannot test, run, or defend.

### What we can still do (and it's plenty)

The endpoints we *do* still have access to give us:

- User profile: display name, follower count, country
- All your playlists (private + collaborative + saved)
- Every track of every playlist with: name, artists, album, release date, duration, popularity score (0–100), explicit flag, **timestamp when you added it**
- Per-artist data including **genres** (which is where genre lives in Spotify's model — there is no track-level genre)
- Saved tracks, top artists, top tracks, recently played

That gives us:

- **Release-year & decade distribution** — how old is your music?
- **Top genres** (aggregated from artist genres) and top artists
- **Popularity distribution** — are you a mainstream or deep-cuts listener?
- **Total duration** of each playlist; explicit ratio
- **"Added at" timeline** — how a playlist evolved over time
- **Cross-playlist comparison** — pick three and see who has the oldest songs, the most variety, the longest runtime

So no mood-map, but a perfectly rich semester-project worth of analysis.

## How to run

### Prerequisites

- Python 3.11 or later
- A Spotify Developer App — register one at <https://developer.spotify.com/dashboard>

### Setup

1. Clone the repo and enter the directory:
   ```
   git clone <repo-url> py_spotify_project
   cd py_spotify_project
   ```

2. Create and activate a virtual environment:
   ```
   # Windows
   python -m venv .venv
   .venv\Scripts\activate

   # macOS / Linux
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

4. Register a Spotify app (if you don't have one):
   - Go to <https://developer.spotify.com/dashboard> → "Create app"
   - Set the redirect URI to `http://127.0.0.1:8888/callback`
   - Copy your `client_id` and `client_secret`

5. Configure credentials:
   ```
   cp .env.example .env
   ```
   Then edit `.env` and fill in:
   - `SPOTIPY_CLIENT_ID` — from the dashboard
   - `SPOTIPY_CLIENT_SECRET` — from the dashboard
   - `SPOTIPY_REDIRECT_URI` — e.g. `http://127.0.0.1:8888/callback`

### Run the notebook

```
jupyter notebook notebooks/01_explore_playlist.ipynb
```

- The first run opens a browser for OAuth; grant the scopes.
- Subsequent runs use the cached token at `.cache/spotify_token` and don't prompt.
- To analyze a different playlist, replace the `PLAYLIST_ID` in the fetch cell with one of your own playlist IDs (visible in the playlist-list cell's output).
- To analyze your "Liked Songs" instead, set `PLAYLIST_ID = "__liked__"`.

### Run the test suite

```
.venv/Scripts/python.exe -m pytest -q          # Windows
.venv/bin/python -m pytest -q                  # macOS / Linux
```

Expected: 42 tests pass.

## Modules

- `src/spotify_project/cache.py` — `FileCache`, a simple file-based JSON cache with TTL
- `src/spotify_project/client.py` — `SpotifyClient`, OAuth + API access via `spotipy` (playlists, liked songs, artists)
- `src/spotify_project/models.py` — `Track`, `Playlist`, `Artist` (frozen dataclasses)
- `src/spotify_project/analyzer.py` — `Analyzer` ABC + six concrete analyzers (Genre, Year, Artist, Popularity, Duration, Timeline) + `PlaylistAnalyzer` orchestrator. Includes plotting.
- `tests/` — pytest unit tests (42)
- `notebooks/01_explore_playlist.ipynb` — demo notebook

## Course grading map (20 pts)

| Criterion | Pts | Where in this repo |
| --- | --- | --- |
| OOP design (classes, inheritance) | 4 | `src/spotify_project/models.py`, `client.py`, `analyzer.py` |
| Internet data access (API + robustness) | 4 | `client.py` (spotipy session retries, 403/429 handling) |
| Pandas analysis + visualization | 4 | `analyzer.py` (plotting included), notebook |
| Code quality (≥ 3 unit tests, structure) | 4 | `tests/` |
| Presentation + ability to explain | 4 | (final lab session) |

## Phase 2 plans

Phase 1 is a Jupyter notebook. Phase 2 is a small web UI with playlist-mutation features. A few decisions deferred from Phase 1 are recorded here so they land in the right place in the codebase when the time comes.

### Async client migration

The current `SpotifyClient` is synchronous. This is intentional for Phase 1: `spotipy` is a sync library, and Spotify's per-app rate limit means firing requests in parallel doesn't actually speed anything up — the API throttles us at the app level regardless of how many concurrent connections we open. Parallelism would be cosmetic at best.

The calculation changes in a web UI: with multiple users hitting the server simultaneously, one user's slow artist fetch should not block another user's request. That's the point at which `async` pays off.

The architecture is already laid out to make migration straightforward. `SpotifyClient` is cleanly separated from `models.py` (which is pure Python dataclasses) and `analyzer.py` (which is pure pandas). An async `AsyncSpotifyClient` can be a drop-in replacement that exposes the same `playlist()` / `liked_songs()` / `artists()` interface — nothing in the analyzer layer would need to change.

### Web UI framework

Two realistic options, each with a different tradeoff:

- **Streamlit** — pure Python, around 50 lines for a working interactive UI. Best if rapid iteration and demo speed matter more than architectural purity.
- **FastAPI + minimal HTML/JS** — more setup, but a more realistic production stack. Better if we want to show "real" web-dev skills in the presentation.

Decision deferred until Phase 1 is complete and delivered.

### Mutation scopes

Phase 1 uses read-only OAuth scopes. Phase 2 playlist-mutation features (create, split, merge, dedupe, re-sort) require two additional scopes:

- `playlist-modify-private`
- `playlist-modify-public`

These are already documented in `CLAUDE.md` and will be added to `SpotifyClient.DEFAULT_SCOPES` when the first mutation feature lands.
