# Code Review Findings — `ec46c73..HEAD` (24 commits)

**Source:** Three review agents (general code review, comment+docstring audit, silent-failure hunt) run on the diff after the Sonnet+Haiku handoffs and your manual touchups.

**How to use this file:** check off items as you fix them. If you disagree with a finding, strike it through and add a one-line note on why — that's a useful artifact when explaining "why we left this" later.


## 🟡 Important — quality, drift, missing tests

### I3. README + docstring drift after the `fetch_*` rename

- `README.md:172` — *"expose the same `playlist()` / `liked_songs()` / `artists()` interface"* → must be `fetch_*`.
- `models.py:100` — *"populated by `SpotifyClient.playlist`"* → `SpotifyClient.fetch_playlist`.

- [ ] Done

### I4. `cache.py:20` class docstring still says `<repo-root>/.cache`

Actual default is `<repo-root>/.cache/api`. Trivial one-word fix.

- [ ] Done

### I5. README test count is wrong

`README.md:141` says "Expected: 42 tests pass." Actual: **44**.

**Fix:** either update the count or drop it entirely (recommendation: drop — counts rot every time you add a test). Replace with "All tests should pass."

- [ ] Done

### I6. README module list omits new dataclasses

`README.md:148` — `models.py — Track, Playlist, Artist`. Missing `User` and `PlaylistSummary` (added in 4599a4f).

- [ ] Done

### I9. "Sprint C" references rot

- `analyzer.py:36` — `"""Apply the Sprint C consistent style + coverage suffix to an Axes."""`
- Notebook cell 0 — `"Phase 1 demo (Sprint C, final)"`

Sprint ceremony shouldn't survive in code/docs.

**Fix:** drop "Sprint C" everywhere.

- [ ] Done

### I10. Silent skip without logging — three call sites

- `client.py:125` — `fetch_user_playlists` filters `None` slots silently. If a user has 5 deleted playlists, listing shows 5 fewer with no feedback.
- `client.py:247` — `_enrich_with_artists` silently filters non-track items (podcasts, local files).
- `client.py:214` — liked-songs filter silently skips null tracks.

**Fix:** at each site, count what was dropped and `logger.info("Dropped %d non-audio items", dropped)` when nonzero.

- [ ] Done

### I11. tqdm: in `requirements.txt` but documented as optional

`requirements.txt:10`: `tqdm>=4.66 # optional — graceful fallback...`. Currently the fallback path in `client.py:14-20` is untested dead code.

**Fix:** pick one:
- Move tqdm to a `[project.optional-dependencies]` extra and document install with extra
- Drop the fallback path; require tqdm

- [ ] Done

---

## 🔵 Suggestions — nice-to-haves

- [ ] **`models.py:113`** — warning says "track may lose primary_artist" but the artist is unconditionally skipped. Tighten to `logger.warning("artist %s missing from lookup; dropping from track %s", aid, track_id)`.

- [ ] **`models.py:108-115`** — when an artist isn't in the lookup, the track keeps going with empty artists. Consider an `ArtistAnalyzer.coverage()` override that counts rows with empty `primary_artist_id` so the partial-data warning fires.

- [ ] **`analyzer.py:113-127`** — `_attach_coverage` docstring should mention the `logger.warning` side effect explicitly. Add: `Side effects: emits logger.warning when n_data/n_total < _LOW_COVERAGE_THRESHOLD (0.7).`

- [ ] **`analyzer.py:347`** — comment about `explode` lock-step is half *what*, half *why*; drop the *what* line.

- [ ] **`cache.py:64-67`** — `clear()` has no `try/except` around `f.unlink()`; on Windows file lock it dies mid-loop with half the cache deleted. Add per-file try/except + warning, continue the loop.

- [ ] **`cache.py:8`** — `parents[2]` arithmetic comment is over-detailed; shrink to `# parents[2] = repo root`.

- [ ] **Pyright-disable rationale headers** in `client.py:1-6` and `analyzer.py:1-6` — three-line justifications can be one or two.

- [ ] **Notebook cell `e8db6079`** — trailing duplicate `# 3v8PWRLiPHGPY0oHgkoZvV` after the playlist-id assignment. Delete.

- [ ] **Notebook cell `adfe3d30`** — duplicates the section header in `7dde2d9e`. Merge.

- [ ] **Logging defense-in-depth (related to S1):** add a redaction filter that scrubs `Authorization: Bearer ...` and similar sensitive patterns from all log records, regardless of which logger emits them. Even at INFO this is good hygiene if you ever flip something to DEBUG temporarily.

---

## ✅ Verified working — what's good

- **`_get_coverage` centralization** (modulo B4) — clean refactor, removes scattered casts.
- **`_enrich_with_artists` extraction (ef83682)** — both call sites preserve behavior; clean DRY win.
- **TimelineAnalyzer simplification (5f1afb6)** — `release_date` fallback fully removed; no stale references; `source` column gone. Right call.
- **Low-coverage warning in `_attach_coverage`** — uniform across all subclasses; no duplicate in TimelineAnalyzer.
- **Cache anchor (4e1065e)** — `parents[2]` is correct; existing `.cache/api/` data preserved.
- **`__init_subclass__` title check + duplicate-title guard** — fail-loud at class construction.
- **Throttle test** — pins both call count + constant; will catch regressions in either direction.
- **Per-call TTL override on `FileCache.get`** — clean, tested.
- **README "deprecation story"** — accurate, well-structured, good context for graders.
- **No deprecated-API try/catch fallbacks anywhere** — your "no dead code" rule honored.
- **No obsolete `# pyright: ignore[...]`** found in the diff.
- **No TODO/FIXME debt** in the codebase.

---

## Splitting strategy for the next chat session

**Sonnet 4.6 chat** — code/correctness work:
- All B1–B6
- I1, I2, I7, I8
- Suggestions on `models.py`, `analyzer.py`, `cache.py`

**Haiku 4.5 chat** — text/doc work:
- I3, I4, I5, I6, I9, I10 (the doc-touch ones)
- I11 if treated as a requirements.txt + README edit
- Notebook cell cleanups

**Opus (this/next session)** — judgment calls:
- I2 line-length policy decision
- I11 tqdm extras vs hard-required decision
- The logging-redaction-filter design (I-suggestions)

---

## Action priority (suggested)

1. Fix Critical bugs (B1–B6) — real correctness issues.
2. I1 (`py314`), I2 (line-length), I7 (missing tests).
3. README/docstring drift sweep (I3–I6, I9).
4. Logging visibility (I10) + tqdm decision (I11).
5. Suggestions cleanup pass.
