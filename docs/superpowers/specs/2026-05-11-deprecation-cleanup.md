# Deprecation Cleanup Spec — Drop `popularity`, Document API Limitations

**Status:** Draft 2026-05-11. Awaiting user approval before execution.
**Trigger:** Notebook output on 2026-05-07 cache showed `Top Genres: low coverage 0/3647 (0%)` and `PopularityAnalyzer` placing all 3647 tracks in the `[0, 10)` bin. Inspection of the raw cached API responses confirmed both `genres` (on artists) and `popularity` (on artists and tracks) are absent from Spotify's API response payloads for this app.
**Predecessor:** [Sprint C](2026-05-06-spotify-phase1-sprint-c.md) — completed; repo declared "good state" by user before this issue surfaced.
**Successor:** [Last.fm Genre Enrichment](2026-05-11-lastfm-genre-enrichment.md) — restores genres via a second API. Out of scope for this spec.

---

## 1. Goal

Remove every dead reference to track/artist `popularity` from the codebase, since Spotify no longer returns that field for apps registered after Nov 27 2024. Document the deprecation prominently in the README so a reader (oral examiner, future maintainer) immediately understands why two course-relevant features look thin.

`genres` is **not** dropped here — it will be re-sourced from Last.fm in Phase 2. In the meantime, the `genres` field on `Artist` stays as a `tuple[str, ...]` but will always be empty until Phase 2 lands. `GenreAnalyzer` stays in the codebase and shows its "No genre data" placeholder.

---

## 2. Code changes

### 2.1 Drop `popularity` from `Track`

`src/spotify_project/models.py`:
- Remove `popularity: int` field from the `@dataclass`.
- Remove the `__post_init__` validation of `popularity`.
- Remove `popularity` from `Track.from_api`. (The key isn't in the API response anymore, so we'd never read it anyway.)
- Update the class docstring.

### 2.2 Drop `popularity` from `Artist`

`src/spotify_project/models.py`:
- Remove `popularity: int` field.
- Remove the `__post_init__` validation of `popularity`.
- Remove `popularity` from `Artist.from_api`.
- Update the class docstring.

### 2.3 Remove `PopularityAnalyzer`

`src/spotify_project/analyzer.py`:
- Delete the `PopularityAnalyzer` class entirely (~50 lines).
- Remove it from the default `analyzers` list in `PlaylistAnalyzer.__init__`.
- Remove `popularity` from the row dict built in `PlaylistAnalyzer.from_playlist`.

### 2.4 Update notebook

`notebooks/01_explore_playlist.ipynb`:
- Remove `PopularityAnalyzer` from both the import line and the `analyzers: list[Analyzer]` list in the build-analyzer cell.
- Re-execute the notebook end-to-end (per "Verify notebook output yourself" memory) to confirm five panels render, no exceptions, no orphan references.

### 2.5 Tests

`tests/`:
- Drop all `popularity` references from `test_models.py` constructors / assertions.
- Drop `PopularityAnalyzer` tests from `test_analyzer.py`.
- Sanity-check that the remaining test count is still ≥ 3 meaningful tests (the rubric floor).

### 2.6 CLAUDE.md

`CLAUDE.md`:
- Add a 1-line note in the **Spotify API gotchas** section: artist `genres` and artist/track `popularity` are silently absent from responses for apps registered after Nov 27 2024; do not depend on them.
- Remove any other references to `popularity` that no longer apply.

---

## 3. README changes

A new top-level section titled **`## Spotify Web API limitations`** sits between the project description and the "Tech stack" section. Suggested content (final wording can be lightly polished during execution):

```markdown
## Spotify Web API limitations

Spotify significantly restricted its Web API on **November 27, 2024**.
Apps registered on or after that date — like this one — no longer have access
to the following endpoints:

- Related Artists
- Recommendations
- Audio Features (track tempo, energy, danceability, valence, …)
- Audio Analysis
- Get Featured Playlists / Get Category's Playlists
- 30-second preview URLs in multi-get responses
- Algorithmic & Spotify-owned editorial playlists

Source: [Spotify for Developers — Introducing some changes to our Web API
(2024-11-27)](https://developer.spotify.com/blog/2024-11-27-changes-to-the-web-api).

In addition to the officially-announced deprecations, two **fields** that the
documentation still lists are now silently absent from the responses we
receive for this app:

- `genres` on the artist object (`GET /artists/{id}`) — returned as missing/empty.
- `popularity` on both the track and artist objects — never present.

This was discovered empirically on 2026-05-07 by inspecting raw API
responses; it is consistent with what other developers have reported on the
Spotify community forums throughout 2025.

### What this means for this project

- **`popularity` analysis is removed.** We had a `PopularityAnalyzer` that
  binned the 0-100 score into a histogram; with the field gone, every track
  reads as `0` and the chart degenerates to a single bar. Per the project's
  "no dead-API code" policy, the analyzer and the field are deleted, not
  faked with a placeholder.
- **Genre analysis is currently empty**, but is being restored in a follow-up
  via the Last.fm API. See `docs/superpowers/specs/2026-05-11-lastfm-genre-enrichment.md`.
```

---

## 4. Verification checklist (run before declaring done)

- [ ] `ruff check src tests` clean.
- [ ] `ruff format --check src tests` clean.
- [ ] `pyright` strict-mode clean.
- [ ] `pytest` passes; test count ≥ 3 meaningful tests.
- [ ] Notebook re-executed end-to-end without exceptions. The five remaining analyzer panels render. `Top Genres` panel still shows the existing "No genre data" placeholder + grey coverage band (unchanged behavior).
- [ ] `grep -rn -i popularity src/ tests/ notebooks/ CLAUDE.md README.md` returns **no** results.
- [ ] README has the new "Spotify Web API limitations" section with the Nov 27 2024 link.
- [ ] `git diff` reviewed by user (per "plan together before coding" memory).

---

## 5. Out of scope (deferred to Phase 2 or beyond)

- Re-sourcing genres from any other API (Last.fm, MusicBrainz, TheAudioDB). That's the entire Phase 2 spec.
- Adding loud warnings in `from_api` when API fields are unexpectedly absent. (Marginal value — we've already verified the absence is universal, not intermittent.)
- Removing `GenreAnalyzer`. It stays; Phase 2 will re-feed it real data.
- Per-track genre enrichment, MusicBrainz fallback, ISRC-based lookups. Documented in Phase 2 as future work.

---

## 6. Estimated effort

~30-45 minutes of edits + verification. No new dependencies. No new files.
