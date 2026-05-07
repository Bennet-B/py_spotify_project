# Sonnet 4.6 handoff — refactors + story-doc

Hi! I'm working on a Spotify analytics project (Python 3.11, src/ layout). **Read `CLAUDE.md` first** — it explains the course rubric, the "no dead-API code" rule, the comment/docstring style preference (C#-XML-doc-style; Google/Sphinx mixed), and that Pydantic was rejected.

Six bundled tasks below, all touching `src/spotify_project/` and `README.md`. **One commit per task** (six commits total) for clean review. Conventional-commits style (see `git log` for examples).

---

## 1. README expansion (two parts)

**1a. Deprecation story.** The README already lists deprecated Spotify endpoints. Expand it into a chronological story:

- Bulk audio-features fetch was the natural design — gone Nov 2024 for new apps.
- This made **caching essential**, not nice-to-have.
- **Rate limits are now the binding constraint.** Artist enrichment is the big offender — N artists × 1 request each, throttled to 250ms client-side.
- Mention **when** things were removed (the user likes that it tells a story).

**1b. New "Phase 2 plans" section near the end of the README.** Cover:

- **Async client migration.** Current sync is intentional: spotipy is sync, and Spotify's per-app rate limit means parallelism is cosmetic. Async pays off only when one user shouldn't block another (i.e. web UI). The client / models / analyzers split keeps async a drop-in replacement.
- **Web UI framework deferred** — Streamlit vs FastAPI, decide after Phase 1.
- **Mutation scopes** (`playlist-modify-private`, `playlist-modify-public`) added in Phase 2.

---

## 2. Logging strategy + progress feedback

The `SpotifyClient` has a logger that's never called. `models.py` names its logger `_log` inconsistently with `client.py`. Fix both — pick one name (suggest `logger`) and apply everywhere.

Decide on a simple level policy and apply it:

- **INFO**: "fetching playlist X (N tracks)", "fetching N unique artists (~M seconds estimate)"
- **DEBUG**: cache hit/miss
- **WARNING**: rate-limit retries, partial coverage <70%

For the artist fetch (which can take minutes), add a **`tqdm` progress bar**. Make `tqdm` an optional dep — graceful fallback (a plain `INFO` log per N artists) if not installed. Add `tqdm` to `requirements.txt` as optional.

---

## 3. Extract shared artist-enrichment helper

The artist-enrichment code in `client.py` is duplicated between `playlist()` and the liked-songs fetch. Extract a private helper, e.g.:

```python
def _enrich_with_artists(self, track_dicts: list[dict[str, Any]]) -> list[dict[str, Any]]: ...
```

Don't change behavior. Both call sites should look the same after.

---

## 4. Reduce `dict[str, Any]` surface (within reason)

Goal: contain `Any` to the client's **internal** methods; **public** methods should return strongly-typed objects (`Playlist`, `list[Artist]`, etc.) — which they mostly already do.

Audit `analyzer.py` and `models.py` for `Any` usage. Where the field is actually known, replace with concrete types. Don't introduce TypedDicts unless they materially help — **Pydantic is rejected** per `CLAUDE.md`.

---

## 5. Cache location: anchor to project root

Currently `FileCache` resolves `.cache/` relative to **CWD**, so a notebook running from `notebooks/` makes a different cache than Streamlit running from the repo root. Fix:

```python
# in cache.py
_PROJECT_ROOT = Path(__file__).resolve().parents[2]  # src/spotify_project/cache.py → up 2 → repo root
DEFAULT_CACHE_DIR = _PROJECT_ROOT / ".cache"
```

Use that as the default when the ctor `cache_dir` arg is `None`. The existing `.cache/` folder must be reused (same path on disk) — **no migration, no copy needed**. Tests must still pass (they inject `tmp_path` via the ctor arg).

---

## 6. TimelineAnalyzer: drop year-only rows (don't fabricate January)

Currently year-only `release_date` values fall back to `YYYY-01-01`, which invents January precision and creates fake spikes. Change:

- Drop those rows from the timeline summary.
- Attach coverage via `_attach_coverage` like the other analyzers.
- Add a `logger.warning` when coverage drops below 70% so the user knows why the timeline looks sparse.

`YearAnalyzer` already covers the year-only case, so no information is lost overall.

---

## Constraints (apply to all tasks)

- Keep the existing per-line `# pyright: ignore[reportUnknownArgumentType, ...]` style for matplotlib stub gaps — **don't globally disable** report kinds in `pyproject.toml`.
- After changes, run `ruff check`, `ruff format`, `pyright`, and `pytest`. Report any remaining warnings/failures.
- Tests in `tests/` must still pass. If a test needs updating because a public name changed, update it.
- Strict type hints everywhere except notebooks (per `~/.claude/rules/python-style.md`).
- If anything is ambiguous or you find a problem with the plan, **ASK** before guessing.
