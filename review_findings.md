# Code Review Findings — `ec46c73..HEAD` (24 commits)

**Source:** Three review agents (general code review, comment+docstring audit, silent-failure hunt) run on the diff after the Sonnet+Haiku handoffs and your manual touchups.

**How to use this file:** check off items as you fix them. If you disagree with a finding, strike it through and add a one-line note on why — that's a useful artifact when explaining "why we left this" later.


## 🔵 Suggestions — nice-to-haves

- [ ] **`models.py:113`** — warning says "track may lose primary_artist" but the artist is unconditionally skipped. Tighten to `logger.warning("artist %s missing from lookup; dropping from track %s", aid, track_id)`.

- [ ] **`models.py:108-115`** — when an artist isn't in the lookup, the track keeps going with empty artists. Consider an `ArtistAnalyzer.coverage()` override that counts rows with empty `primary_artist_id` so the partial-data warning fires.

- [ ] **`analyzer.py:113-127`** — `_attach_coverage` docstring should mention the `logger.warning` side effect explicitly. Add: `Side effects: emits logger.warning when n_data/n_total < _LOW_COVERAGE_THRESHOLD (0.7).`

- [ ] **`analyzer.py:347`** — comment about `explode` lock-step is half *what*, half *why*; drop the *what* line.

- [ ] **`cache.py:64-67`** — `clear()` has no `try/except` around `f.unlink()`; on Windows file lock it dies mid-loop with half the cache deleted. Add per-file try/except + warning, continue the loop.

- [ ] **`cache.py:8`** — `parents[2]` arithmetic comment is over-detailed; shrink to `# parents[2] = repo root`.

- [ ] **Pyright-disable rationale headers** in `client.py:1-6` and `analyzer.py:1-6` — three-line justifications can be one or two.

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