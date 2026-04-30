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

## How to run *(placeholder — fills in as we build)*

1. Clone the repo
2. Create a Python 3.11+ virtual environment: `python -m venv .venv` then activate it
3. Install dependencies: `pip install -r requirements.txt`
4. Register a Spotify Developer App at <https://developer.spotify.com/dashboard>; set its redirect URI to `http://127.0.0.1:8888/callback`
5. Copy `.env.example` to `.env` and paste your `client_id` / `client_secret`
6. Open `notebooks/01_explore_user_account.ipynb` and run

## Modules *(placeholder)*

- `src/spotify_project/client.py` — auth and API access via `spotipy`
- `src/spotify_project/models.py` — `SpotifyResource` (ABC) and `Track` / `Playlist` / `Artist` subclasses
- `src/spotify_project/analyzer.py` — pandas-based analyses of a playlist or set of playlists
- `src/spotify_project/visualizer.py` — matplotlib / seaborn plots
- `tests/` — pytest unit tests
- `notebooks/` — exploratory notebook(s)

## Course grading map (20 pts)

| Criterion | Pts | Where in this repo |
| --- | --- | --- |
| OOP design (classes, inheritance) | 4 | `src/spotify_project/models.py`, `client.py`, `analyzer.py` |
| Internet data access (API + robustness) | 4 | `client.py` (spotipy session retries, 403/429 handling) |
| Pandas analysis + visualization | 4 | `analyzer.py`, `visualizer.py`, notebook |
| Code quality (≥ 3 unit tests, structure) | 4 | `tests/` |
| Presentation + ability to explain | 4 | (final lab session) |
