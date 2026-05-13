# py_spotify_project

A Python toolkit for analyzing your own Spotify account — playlists, genres, listening history, release-year distribution and "added at" timelines.

## About

A learning project, written to exercise a specific set of Python topics end-to-end:

- **OOP** — abstract base class + concrete subclasses (Strategy pattern), frozen dataclasses, real polymorphism
- **HTTP / REST** — a real third-party API, OAuth2 authorization-code flow, pagination, retries, rate limits
- **Caching** — file-based JSON cache with TTL so the API isn't hammered on every notebook run
- **Data** — `pandas` for analysis, `matplotlib` + `seaborn` for charts
- **Robustness** — input validation, defensive parsing, graceful degradation when an optional service is missing
- **Tooling** — `pytest` (with mocks for the HTTP layer), `pyright` strict, `ruff` for lint + format

## The Spotify Web API in 2026 — what shaped this codebase

Spotify cut significant functionality from the Web API across 2024–2026. The constraints below explain several design choices in `src/`.

### What's gone

**Nov 27, 2024 — deprecated for new apps** ([announcement](https://developer.spotify.com/blog/2024-11-27-changes-to-the-web-api)). Apps registered after this date receive `403 Forbidden` from:

- `audio-features` (danceability, energy, valence, tempo, key, acousticness…)
- `audio-analysis` (bar / beat / segment data)
- `recommendations`, `related-artists`
- featured / category playlists, genre seeds
- 30-second preview URLs in multi-get responses

**Through 2025 — silent field strip** (no migration notice; observed empirically and confirmed by inspecting our cached responses on 2026-05-07):

- `genres` on the artist object — now returned empty
- `popularity` on tracks and artists — now absent from the payload

**Feb 2026** — the batch-artists endpoint (`GET /artists?ids=…`) was removed for new apps. Fetching one playlist's worth of artists became one HTTP call per artist.

### How that shaped the code

- **Caching is load-bearing.** Each artist costs a real round-trip, so `FileCache` keeps artist responses for 365 days. Cached entries cover an entire year of notebook runs from a single fetch.
- **Rate limits dictate pacing.** The client paces artist fetches at ~4 req/s and prints progress via `tqdm`; a fresh ~2 000-artist library takes ~7 minutes and must be run over several sessions to allow the cache to fill.
- **Genres come from Last.fm.** Since Spotify's `artist.genres` field is empty, we enrich via Last.fm's `artist.getTopTags`. Raw tags surface in a `Top Tags` panel; a curated whitelist (`genre_taxonomy.py`) filters them into a `Top Genres` panel. The project runs without a Last.fm key — those two panels are simply skipped with an INFO log line.
- **No dead code for deprecated endpoints.** `get_audio_features`, `recommendations`, `related_artists`, and similar are not in `src/` at all. We don't ship code we can't test.

### What's still here

User profile; all playlists (private + collaborative + saved); every track with name / artists / album / release date / duration / explicit flag / added-at timestamp; per-artist metadata; saved tracks; top artists; top tracks; recently played.

That gives us: release-year & decade distribution, top artists (count and minutes), top genres + tags, total duration & explicit ratio, "added at" timeline, and cross-playlist comparison.

## How to run

### Prerequisites

- Python 3.11+
- A Spotify developer app — register at <https://developer.spotify.com/dashboard>
- *(Optional - but highly recommended)* a Last.fm API key for genre / tag enrichment — register at <https://www.last.fm/api/account/create>

### Setup

```bash
# clone + venv
git clone <repo-url> py_spotify_project
cd py_spotify_project
python -m venv .venv

# activate (Windows)
.venv\Scripts\activate
# activate (macOS / Linux)
source .venv/bin/activate

# install deps
pip install -r requirements.txt

# credentials
cp .env.example .env
```

Then edit `.env` and fill in:

- `SPOTIPY_CLIENT_ID` / `SPOTIPY_CLIENT_SECRET` — from the developer dashboard
- `SPOTIPY_REDIRECT_URI` — must match the URI registered on the dashboard (e.g. `http://127.0.0.1:8888/callback`)
- `LASTFM_API_KEY` — optional; enables the `Top Tags` and `Top Genres` panels

### Run the notebook

```bash
jupyter notebook notebooks/01_explore_playlist.ipynb
```

- First run opens a browser for OAuth; subsequent runs read the cached token from `.cache/spotify_token`.
- To analyze a different playlist, replace `PLAYLIST_ID` in the fetch cell. Use `"__liked__"` for your Liked Songs.

### Quality checks

```bash
ruff check                                     # lint
ruff format                                    # format (Black-compatible)
pyright                                        # type check (strict mode)
.venv/Scripts/python.exe -m pytest -q          # tests (Windows)
.venv/bin/python -m pytest -q                  # tests (macOS / Linux)
```

See `pyproject.toml` for tooling configuration.

## Modules

- `src/spotify_project/cache.py` — `FileCache` (file-based JSON cache with TTL)
- `src/spotify_project/client.py` — `SpotifyClient` (OAuth, paged fetch, retries, optional genre enricher)
- `src/spotify_project/lastfm_client.py` — `LastFmClient` (optional Last.fm `artist.getTopTags` enrichment)
- `src/spotify_project/models.py` — `Track`, `Playlist`, `Artist`, `User`, `PlaylistSummary` (frozen dataclasses)
- `src/spotify_project/analyzer.py` — `Analyzer` ABC + six concrete analyzers (Genre, Tag, Year, Artist, Duration, Timeline) + `PlaylistAnalyzer` orchestrator
- `src/spotify_project/genre_taxonomy.py` — `GENRE_WHITELIST` + `filter_to_genres`
- `src/spotify_project/logging_setup.py` — auth-header redaction filter + `tqdm`-compatible log handler
- `notebooks/01_explore_playlist.ipynb` — demo notebook
- `tests/` — pytest unit tests (one per module)
