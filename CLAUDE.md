# py_spotify_project

A Spotify analytics + playlist tool. Originally built as the **INFPROG2 FS26 semester project** at ZHAW (submitted — frozen at tag `v1.0-prog2`); now continuing as a personal tool.

## Goal

Phase 1 (done, course scope): A Jupyter notebook that authenticates as a Spotify user and analyzes their playlists — genres, release-year distribution, top artists, duration, "added at" timeline, cross-playlist comparison.

Phase 1.5 (current): richer notebook analytics — temporal analysis (library growth, artist discovery waves, seasonal trends), distribution views (KDE, ECDF, violin/box), release-year vs added-year, network visualizations (artist co-occurrence, genre similarity), first interactive Plotly charts.

Phase 2 (next, planned jointly): A small web UI to do the same analyses interactively, plus mutations — create / split / merge / re-sort / dedupe / re-tag playlists. A "playlist organizer" tool: split a source playlist / liked songs into genre- or vibe-matching buckets.

## Course requirements (satisfied — kept because they explain the code's shape)

| Criterion | Pts | How we satisfy it |
| --- | --- | --- |
| OOP design — 2–3 classes with meaningful inheritance | 4 | **Option B (chosen):** `Analyzer` (ABC) → 6 concrete subclasses with overridden `analyze()` + `plot()` methods (Strategy pattern): Genre, Tag, Year, Artist, Duration, Timeline. Plus `SpotifyClient`, `FileCache`, `LastFmClient`, `PlaylistAnalyzer` orchestrator. `Track`, `Playlist`, `Artist`, `User`, `PlaylistSummary` as plain `@dataclass(frozen=True, slots=True)`. Real polymorphism in `PlaylistAnalyzer.run_all()`. See [Phase 1 design spec](docs/superpowers/specs/2026-04-30-spotify-phase1-design.md). |
| Internet data access (public API, programmatic) | 4 | Spotify Web API via `spotipy` |
| Robustness & validation (try/except, retries, malformed data) | shares slot | spotipy session retries, graceful 403/429 handling, `LastFmClient` retry + not-found graceful degrade, `FileCache` corrupt-entry recovery, `Track.__post_init__` invariant guard |
| Pandas analysis + ≥ 1 visualization | 4 | DataFrame of tracks; matplotlib plots (year histogram, genre bar, etc.) |
| Code quality — ≥ 3 meaningful unit tests | 4 | `pytest` in `tests/` |
| Presentation — both members can explain any line | 4 | Keep code small and explainable; avoid black-box AI dumps |

Deliverables: Git repo with `src/`, `notebooks/`, `tests/`, README. Final presentation 5–10 min in the last lab session. The exact submitted state is tag `v1.0-prog2`.

## Tech stack

- Python 3.14+ (`requires-python` matches what ruff/pyright/the venv actually enforce; per global style: type hints everywhere, `from __future__ import annotations`)
- `.venv` per project (per global rule)
- `spotipy` — Spotify Web API client, handles OAuth
- `pandas` + `matplotlib` + `seaborn` — analysis + plots
- `python-dotenv` — load credentials from `.env`
- `tqdm` — progress bar during Last.fm artist enrichment (~7 min for a fresh ~2 000-artist library)
- `pyarrow` — pandas Arrow-backed dtype support (transitive but pinned)
- `pytest` — tests
- `jupyter` / `ipykernel` — for the notebook
- (Phase 2) `streamlit` or `fastapi` + minimal HTML — TBD

## Commands

Run from the repo root using the venv's interpreter (Windows / Linux paths differ):

```bash
.venv/Scripts/python.exe -m pytest -q          # tests (Windows)
.venv/bin/python -m pytest -q                  # tests (macOS / Linux)
ruff check                                      # lint
ruff format                                     # format
pyright                                         # type check (strict)
jupyter notebook notebooks/01_explore_playlist.ipynb
```

## Spotify API gotchas — IMPORTANT

The Spotify Web API was significantly cut down in late 2024 / early 2026. Read these before assuming any endpoint works:

1. **Audio Features endpoint is deprecated for new apps (Nov 2024).** The classic `valence / energy / danceability / tempo / acousticness / key` features are **not available** to apps registered after 2024-11-27 — they return 403. **Policy:** we do **not** implement deprecated endpoints in `src/`. No `get_audio_features()`, no try/catch fallback, no feature flag. The constraint is documented in README; the codebase contains only what we can run and test. (Driver: user feedback "no untestable / dead code", saved in memory.)
2. **Audio Analysis, Recommendations, Related Artists, Featured / Category Playlists, Genre Seeds** — also deprecated for new apps. Don't use.
3. **Artist `genres` and track/artist `popularity` are silently absent.** Even though the docs still list them, response payloads for our app (registered after 2024-11-27) omit both fields entirely. Discovered empirically 2026-05-07 by inspecting cached responses; consistent with developer reports throughout 2025. `popularity` is removed from the codebase per the no-dead-API-code policy. `Artist` stores raw Last.fm tags in a `tags: tuple[str, ...]` field; `.genres` is a derived `@property` that filters those tags through a curated whitelist in `src/spotify_project/genre_taxonomy.py`. With no Last.fm key, `tags` stays empty, `.genres` returns `()`, and the `Top Tags` / `Top Genres` analyzer panels are skipped with an INFO log line. (See [Last.fm enrichment spec](docs/superpowers/specs/2026-05-11-lastfm-genre-enrichment.md).)
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

## Project structure

```
py_spotify_project/
├── .env                       # gitignored
├── .env.example
├── .gitignore                 # .env, .cache*, .venv/, docs/, __pycache__/, *.ipynb_checkpoints
├── README.md
├── CLAUDE.md
├── requirements.txt
├── pyproject.toml             # ruff + pyright + pytest config
├── docs/                      # gitignored — local working notes, not shipped
│   ├── INFPROG2 FS26 Semester Project Guide.txt
│   ├── chat_histories/        # archived Claude session transcripts
│   ├── week_10_infodump/      # course materials / lecture extracts
│   └── superpowers/
│       ├── specs/             # active design specs (Phase 1 design, Last.fm enrichment)
│       └── archive/           # superseded sprint plans + specs (historical)
├── src/
│   └── spotify_project/
│       ├── __init__.py
│       ├── analyzer.py        # Analyzer (ABC) + 6 subclasses + PlaylistAnalyzer orchestrator
│       ├── cache.py           # FileCache — file-based JSON cache with TTL
│       ├── client.py          # SpotifyClient — auth, fetch, retry, pagination
│       ├── genre_taxonomy.py  # GENRE_WHITELIST + filter_to_genres
│       ├── lastfm_client.py   # LastFmClient — optional Last.fm tag enrichment
│       ├── logging_setup.py   # RedactAuthFilter + TqdmLoggingHandler
│       └── models.py          # @dataclass Track, Playlist, Artist, User, PlaylistSummary
├── notebooks/
│   └── 01_explore_playlist.ipynb
└── tests/
    ├── test_analyzer.py
    ├── test_cache.py
    ├── test_client.py            # mocked spotipy
    ├── test_genre_taxonomy.py
    ├── test_lastfm_client.py
    ├── test_logging_setup.py
    ├── test_models.py
    └── test_playlist_analyzer.py
```

## Style anchors

- Global Python style rules apply — see `~/.claude/rules/python-style.md`.
- Strict type hints everywhere except notebooks (per global rule).
- Plain `@dataclass(slots=True, frozen=True)` for data carriers; validate invariants in `__post_init__` only where bugs can plausibly occur. Pydantic considered and rejected (data source is consistent and trusted, no untrusted input).
- `with` for files. `pathlib.Path`, never string concat. Always `encoding="utf-8"`. Always `timeout=` on requests.
- **Comment / docstring style** (user preference): write a docstring on every class and every non-trivial public method, in the style of C# XML doc comments — short summary, parameters, return value, exceptions raised. Use Google-style or Sphinx-style docstrings consistently. Inline `#` comments only where the *why* is non-obvious. Self-explanatory names + good docstrings beat noisy inline comments.

## Deferred decisions

- **Phase 2 web UI — framework AND scope:** to be decided **jointly with the user** in a dedicated planning session (Claude presents options, user decides). Candidates: Streamlit (very fast, pure Python) vs FastAPI + small HTML/JS frontend (more work, more "real-world" stack). Scope questions: which analyses go interactive, how far the playlist organizer goes (given no audio features, "vibe" must derive from Last.fm tags + release year + artist data), and the dry-run/review UX before any playlist mutation.

## Reference materials in this repo

The entire `docs/` directory is **gitignored** — these are local working notes that aren't shipped. A fresh clone won't have them.

- `docs/superpowers/specs/2026-04-30-spotify-phase1-design.md` — Phase 1 design spec (implemented, historical)
- `docs/superpowers/specs/2026-05-11-lastfm-genre-enrichment.md` — Last.fm enrichment spec (implemented, historical)
- `docs/superpowers/archive/` — superseded sprint plans and specs from the course phase
- `docs/chat_histories/` — archived Claude session transcripts from each sprint
- `docs/INFPROG2 FS26 Semester Project Guide.txt` — official course brief
- `docs/week_10_infodump/PROG2_SUMMARY.md` — condensed course summary; especially §5 (OOP), §7 (HTTP), §8 (validation), §9 (pandas), §15 (semester-project rubric)
- `docs/week_10_infodump/_extracted/` — full lecture notebooks and lab solutions

## Current status

- 2026-04-30: Project initialized; Phase 1 design completed via superpowers brainstorming. Pivoted from Option A (SpotifyResource hierarchy) to Option B (Analyzer hierarchy) — better-defended OOP, real polymorphism. Dropped pydantic; added FileCache. Spec at `docs/superpowers/specs/2026-04-30-spotify-phase1-design.md`. Implementation begins after user approval.
- 2026-05-12: Last.fm tag enrichment implemented on `feature/lastfm-tag-enrichment` branch. `Artist` redesigned (raw `tags` + derived `genres` property); `LastFmClient` added (FileCache-backed, 365-day TTL); `SpotifyClient` gained optional `genre_enricher`; `TagAnalyzer` added; `PlaylistAnalyzer.run_all/plot_all` skip Tag/Genre panels when LASTFM_API_KEY is unset. See implementation plan (archived at `docs/superpowers/archive/plans/2026-05-12-lastfm-tag-enrichment.md`).
- 2026-05-13: Last.fm enrichment merged to `main` via PR #1. Test suite restructured around per-module files (`test_playlist_analyzer.py` split out from `test_analyzer.py`; added `test_logging_setup.py`, `test_genre_taxonomy.py`, `test_cache.py`, `test_lastfm_client.py`). `.gitignore` cleaned up — `docs/` is now explicitly local-only. Phase 1 implementation effectively complete; remaining work is documentation polish, README slim-down, and final presentation prep.
- 2026-07-02: Course submitted and graded-state frozen at tag `v1.0-prog2`. Project continues as a personal tool. Post-course cleanup pass (`chore/post-course-cleanup`): full codebase review, superseded planning docs moved to `docs/superpowers/archive/`, CLAUDE.md re-scoped. Next: notebook visualization upgrade (Phase 1.5), then a joint planning session for the Phase 2 web UI (framework + scope decided together with the user).
