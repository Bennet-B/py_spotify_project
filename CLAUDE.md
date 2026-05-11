# py_spotify_project

A Spotify analytics + playlist tool, built as the **INFPROG2 FS26 semester project** at ZHAW (alternative to weekly Praktika P01–P04, worth 20% / 20 pts of the final grade).

## Goal

Phase 1 (current): A Jupyter notebook that authenticates as a Spotify user and analyzes their playlists — genres, release-year distribution, top artists, duration, "added at" timeline, cross-playlist comparison.

Phase 2 (later, maybe): A small web UI to do the same analyses interactively, plus mutations — create / split / merge / re-sort / dedupe / re-tag playlists. A "playlist organizer" tool.

## Course requirements (must be visible in the codebase)

| Criterion | Pts | How we satisfy it |
| --- | --- | --- |
| OOP design — 2–3 classes with meaningful inheritance | 4 | **Option B (chosen):** `Analyzer` (ABC) → 5 concrete subclasses with overridden `analyze()` + `plot()` methods (Strategy pattern). Plus `SpotifyClient`, `FileCache`, `PlaylistAnalyzer` orchestrator. Track/Playlist/Artist as plain `@dataclass(frozen=True, slots=True)`. Real polymorphism in `PlaylistAnalyzer.run_all()`. See [Phase 1 design spec](docs/superpowers/specs/2026-04-30-spotify-phase1-design.md). |
| Internet data access (public API, programmatic) | 4 | Spotify Web API via `spotipy` |
| Robustness & validation (try/except, retries, malformed data) | shares slot | spotipy session retries, graceful 403/429 handling, Pydantic at boundaries |
| Pandas analysis + ≥ 1 visualization | 4 | DataFrame of tracks; matplotlib plots (year histogram, genre bar, etc.) |
| Code quality — ≥ 3 meaningful unit tests | 4 | `pytest` in `tests/` |
| Presentation — both members can explain any line | 4 | Keep code small and explainable; avoid black-box AI dumps |

Deliverables: Git repo with `src/`, `notebooks/`, `tests/`, README. Final presentation 5–10 min in the last lab session.

## Tech stack

- Python 3.11+ (per global style: type hints everywhere, `from __future__ import annotations`)
- `.venv` per project (per global rule)
- `spotipy` — Spotify Web API client, handles OAuth
- `pandas` + `matplotlib` + `seaborn` — analysis + plots
- `python-dotenv` — load credentials from `.env`
- `pytest` — tests
- `jupyter` / `ipykernel` — for the notebook
- (Phase 2) `streamlit` or `fastapi` + minimal HTML — TBD

## Spotify API gotchas — IMPORTANT

The Spotify Web API was significantly cut down in late 2024 / early 2026. Read these before assuming any endpoint works:

1. **Audio Features endpoint is deprecated for new apps (Nov 2024).** The classic `valence / energy / danceability / tempo / acousticness / key` features are **not available** to apps registered after 2024-11-27 — they return 403. **Policy:** we do **not** implement deprecated endpoints in `src/`. No `get_audio_features()`, no try/catch fallback, no feature flag. The constraint is documented in README; the codebase contains only what we can run and test. (Driver: user feedback "no untestable / dead code", saved in memory.)
2. **Audio Analysis, Recommendations, Related Artists, Featured / Category Playlists, Genre Seeds** — also deprecated for new apps. Don't use.
3. **Artist `genres` and track/artist `popularity` are silently absent.** Even though the docs still list them, response payloads for our app (registered after 2024-11-27) omit both fields entirely. Discovered empirically 2026-05-07 by inspecting cached responses; consistent with developer reports throughout 2025. `popularity` is removed from the codebase per the no-dead-API-code policy; `genres` stays as a field on `Artist` and will be re-sourced from Last.fm (see [Last.fm enrichment spec](docs/superpowers/specs/2026-05-11-lastfm-genre-enrichment.md)).
4. **Track-level genre never existed.** When genres flow again (via Last.fm), they're still per-artist; track-level genre is synthesized from the primary artist.
5. **Pagination is required.** Most list endpoints cap at 50–100 items. Use spotipy's `sp.next(results)` loop.
6. **Rate limiting:** 429 with `Retry-After` header. spotipy's session handles backoff but be defensive.
7. **`/v1/...` endpoints are being migrated.** Prefer the spotipy method (e.g. `sp.playlist_items`) over hand-rolled URLs — the library tracks these.

## Authentication

- Register a Spotify Developer App at <https://developer.spotify.com/dashboard>. We need `client_id`, `client_secret`, and a registered `redirect_uri` (default plan: `http://127.0.0.1:8888/callback`).
- **Secrets approach (UserSecrets-equivalent for Python):** spotipy auto-reads `SPOTIPY_CLIENT_ID`, `SPOTIPY_CLIENT_SECRET`, `SPOTIPY_REDIRECT_URI` from the process environment. We populate them in priority order:
  1. real OS env vars (Windows: `setx SPOTIPY_CLIENT_ID "..."` — closest to .NET UserSecrets, never lives in project tree), if set
  2. otherwise, a `.env` file in the repo root loaded via `python-dotenv` (file is gitignored)
- A `.env.example` (no secrets) is committed to document the keys.
- We did **not** pick `keyring` (OS credential store) — overkill for a single-user course project; revisit if it ever ships beyond the team.
- spotipy's `SpotifyOAuth` does the Auth-Code flow: opens a browser, user grants scopes, code is exchanged, token cached in `.cache` (also gitignored).
- Scopes needed for Phase 1 (read-only): `user-read-private`, `user-read-email`, `playlist-read-private`, `playlist-read-collaborative`, `user-library-read`, `user-top-read`.
- Scopes added in Phase 2 (mutation): `playlist-modify-private`, `playlist-modify-public`.

## Project structure (proposed)

```
py_spotify_project/
├── .env                       # gitignored
├── .env.example
├── .gitignore                 # .env, .cache, .venv/, __pycache__/, *.ipynb_checkpoints
├── README.md
├── requirements.txt
├── pyproject.toml             # ruff + pyright config
├── docs/
│   └── superpowers/
│       └── specs/
│           └── 2026-04-30-spotify-phase1-design.md
├── src/
│   └── spotify_project/
│       ├── __init__.py
│       ├── cache.py           # FileCache — file-based API response cache (7-day TTL)
│       ├── client.py          # SpotifyClient — auth, fetch, retry, pagination
│       ├── models.py          # @dataclass Track, Playlist, Artist (no inheritance)
│       └── analyzer.py        # Analyzer (ABC) + 6 subclasses + PlaylistAnalyzer orchestrator
├── notebooks/
│   └── 01_explore_user_account.ipynb
└── tests/
    ├── test_models.py
    ├── test_analyzer.py
    └── test_client.py         # mocked
```

## Style anchors

- Global Python style rules apply — see `~/.claude/rules/python-style.md`.
- Strict type hints everywhere except notebooks (per global rule).
- Plain `@dataclass(slots=True, frozen=True)` for data carriers; validate invariants in `__post_init__` only where bugs can plausibly occur. Pydantic considered and rejected (data source is consistent and trusted, no untrusted input).
- `with` for files. `pathlib.Path`, never string concat. Always `encoding="utf-8"`. Always `timeout=` on requests.
- **Comment / docstring style** (user preference): write a docstring on every class and every non-trivial public method, in the style of C# XML doc comments — short summary, parameters, return value, exceptions raised. Use Google-style or Sphinx-style docstrings consistently. Inline `#` comments only where the *why* is non-obvious. Self-explanatory names + good docstrings beat noisy inline comments.

## Deferred decisions

- **Phase 2 web UI framework:** Streamlit (very fast, pure Python, ~50 lines for a working UI) vs FastAPI + small HTML/JS frontend (more work, more "real-world" stack). User is open to trying both. Decide when Phase 1 is done.

## Reference materials in this repo

- `docs/superpowers/specs/2026-04-30-spotify-phase1-design.md` — **authoritative Phase 1 design spec** (start here)
- `INFPROG2 FS26 Semester Project Guide.txt` — official course brief (root)
- `week_10_infodump/PROG2_SUMMARY.md` — condensed course summary; especially §5 (OOP), §7 (HTTP), §8 (validation), §9 (pandas), §15 (semester-project rubric)
- `week_10_infodump/_extracted/` — full lecture notebooks and lab solutions (gitignored)

## Current status

- 2026-04-30: Project initialized; Phase 1 design completed via superpowers brainstorming. Pivoted from Option A (SpotifyResource hierarchy) to Option B (Analyzer hierarchy) — better-defended OOP, real polymorphism. Dropped pydantic; added FileCache. Spec at `docs/superpowers/specs/2026-04-30-spotify-phase1-design.md`. Implementation begins after user approval.
