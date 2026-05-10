# Code Review Findings — `ec46c73..HEAD` (24 commits)

**Source:** Three review agents (general code review, comment+docstring audit, silent-failure hunt) run on the diff after the Sonnet+Haiku handoffs and your manual touchups.

**Status:** S1 (OAuth token + PII leak in notebook) handled separately in-session. Everything else here for later review.

**How to use this file:** check off items as you fix them. If you disagree with a finding, strike it through and add a one-line note on why — that's a useful artifact when explaining "why we left this" later.

---

## 🔴 Critical — correctness bugs

### B1. `cache.py:33-51` — JSON corruption crashes the whole analysis

`json.loads(path.read_text(...))` is unguarded. A truncated/corrupted cache file (kill -9 mid-write, AV scan, OneDrive sync conflict on Windows) raises straight to the caller and aborts the analysis with a confusing `JSONDecodeError`.

**Fix:** wrap in `try/except (json.JSONDecodeError, OSError)`, log `logger.warning("Corrupted cache entry %s: %s; treating as miss", key, e)`, return `None`. This is exactly the "live unhappy path" your `feedback_no_untestable_code` memory endorses.

- [x] Done

### B2. `client.py:161-164` — `fetch_playlist` raises on legitimately empty playlists

```python
if not data.get("items"):
    raise ValueError(f"Playlist {playlist_id} [...] returned no track details.")
```

A playlist with **zero tracks** (a valid user state) hits this branch and raises. The check should be "key missing", not "key falsy". Also asymmetric: only `items` checked, but `fetch_user_playlists` accepts both `items` and `tracks` shapes.

**Fix:** raise only on `if "items" not in data and "tracks" not in data:`; an empty list of items should produce an empty `Playlist`.

- [x] Done

### B3. `models.py:117` — `datetime.fromisoformat` aborts the whole playlist on one bad row

A single malformed `added_at` raises `ValueError` and breaks the entire `Track.from_api` chain, taking the whole playlist with it. No log, no skip.

**Fix:** `try/except ValueError`, log `logger.warning("Unparseable added_at %r for track %s", added_at_raw, ...)`, set `added_at = None`.

- [x] Done

### B4. `analyzer.py:30` — type-narrowing was dropped from `_get_coverage`

The 84d0b5f cleanup replaced `cast(tuple[int, int] | None, summary.attrs.get("coverage"))` with:

```python
coverage: tuple[int, int] = summary.attrs.get("coverage", (0, 0))
return coverage
```

`summary.attrs` is `dict[Hashable, Any]` — the annotation is a lie at runtime. Combined with the simultaneous loosening of the match-case from `case (int(n_data), int(n_total))` to `case (n_data, n_total)` (analyzer.py:47), any non-tuple value silently slips through and crashes downstream.

**Fix:** restore the `cast(...)` on read OR re-add the `int(...)` runtime narrowing in the match cases. The prior pattern was strictly safer. Pick one:
- `coverage = cast(tuple[int, int] | None, summary.attrs.get("coverage"))` → callers handle None
- Keep current return but restore `case (int(n_data), int(n_total))` on every match site

- [ ] Done

### B5. `client.py:19` — `# type: ignore[assignment]` is mypy syntax in a pyright project

This comment does **nothing** in this repo (project uses pyright, per global rule). It's silently disabled noise.

**Fix:** Replace with `# pyright: ignore[reportAssignmentType]` or — better — fix the type properly: `_tqdm_cls: type[tqdm[str]] | None`.

- [x] Done

### B6. `client.py:109-114` — `fetch_current_user` silently coerces missing id/email to `""`

```python
id=data.get("id", "") or "",
display_name=data.get("display_name", "") or "",
```

A `User(id="", display_name="")` is structurally broken and breaks downstream with no clue why. Missing `id` from `current_user()` means an auth failure — fail loud.

**Fix:** `if not data.get("id"): raise RuntimeError(f"Spotify returned a user payload with no id; check token validity. Keys: {list(data.keys())}")`.

- [x] Done

---

## 🟡 Important — quality, drift, missing tests

### I1. `pyproject.toml:15, 25` — Python target is **3.14** (doesn't exist yet)

`target-version = "py314"` and `pythonVersion = "3.14"`. 3.14 ships Oct 2026. CLAUDE.md says "Python 3.11+". Pick a real version.

**Fix:** `py311` (project minimum) or `py312` if you want newer match-syntax. Silently changes ruff lint behavior right now.

- [ ] Done

### I2. `pyproject.toml:14` — line length is **188**, global rule is **88**

Your manual touchups (2c6abf3) collapsed wrapped lines into >88-char one-liners that pass only because of the loose setting. Right now `~/.claude/rules/python-style.md` and the project disagree.

**Fix:** decide one of:
- Tighten to 88 + run `ruff format`
- Document the 188 deviation in `CLAUDE.md` with a reason

- [ ] Done

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

### I7. No tests for `User`, `PlaylistSummary`, `fetch_current_user`, `fetch_user_playlists`

The only behavior change in 4599a4f ships untested. Easy edge case: Spotify returns `display_name: null` (not missing-key) for users who haven't set one — currently silently coerced to `""` (also see B6).

**Minimum:** one test per dataclass + parser. Mock the spotipy response.

- [ ] Done

### I8. `client.py:135` `track_count` parsing has a fragile `items or tracks` fallback

`int((p.get("items") or p.get("tracks") or {}).get("total", 0))` — the listing endpoint returns `tracks: {...}`, never `items`. The fallback works only because `p.get("items")` returns `None`.

**Fix:** tighten to a single explicit shape: `tracks_field = p.get("tracks") or {}`. If Spotify ever changes the shape, fail loud.

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
