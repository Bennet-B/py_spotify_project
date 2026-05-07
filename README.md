# py_spotify_project

A Python toolkit for analyzing your own Spotify account: playlists, genres, listening history, track ages, and more — built as the **INFPROG2 FS26 semester project** (ZHAW).

The repo will grow in two phases:

1. **A Jupyter notebook** that authenticates you, pulls your playlists, and produces a stack of charts and stats about them.
2. **A small web UI** (Streamlit or FastAPI — TBD) that does the same interactively, plus playlist organization features: split, merge, dedupe, re-sort.

## A note about the Spotify Web API in 2026 — the sad part

In **late November 2024** Spotify deprecated several of the most fun parts of its public Web API for any developer app registered after that date:

- `audio-features` — danceability, energy, valence, tempo, key, acousticness, instrumentalness, loudness, etc.
- `audio-analysis` — bar / beat / segment-level structural data
- `recommendations` — "give me tracks like these"
- `related-artists`
- featured / category playlists
- genre seeds

Further endpoints were trimmed in early 2026.

Because **this app is brand-new**, none of those work for us — the API returns `403 Forbidden`. Apps that had extended quota *before* Nov 2024 are grandfathered in, but we're not. The classic "valence × energy mood map" plot you'll see in older Spotify-analytics tutorials is **not** something we can build today.

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

## Project status

- 2026-04-30: Project kickoff. Course brief reviewed, API state verified, plan agreed with user. Notebook scaffolding next.
- *(more dated entries land here as we build.)*

## How to run

### Prerequisites

- Python 3.11 or later (3.14 tested)
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
- `tests/` — pytest unit tests (42 as of Sprint C)
- `notebooks/01_explore_playlist.ipynb` — demo notebook

## Course grading map (20 pts)

| Criterion | Pts | Where in this repo |
| --- | --- | --- |
| OOP design (classes, inheritance) | 4 | `src/spotify_project/models.py`, `client.py`, `analyzer.py` |
| Internet data access (API + robustness) | 4 | `client.py` (spotipy session retries, 403/429 handling) |
| Pandas analysis + visualization | 4 | `analyzer.py` (plotting included), notebook |
| Code quality (≥ 3 unit tests, structure) | 4 | `tests/` |
| Presentation + ability to explain | 4 | (final lab session) |
