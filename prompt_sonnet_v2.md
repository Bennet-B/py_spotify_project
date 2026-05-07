# Sonnet 4.6 — remediation pass

Read `CLAUDE.md` first. Five small but precise fixes against `main`. **One commit per task.** Conventional-commits style. Run `ruff check`, `ruff format`, `pyright`, `pytest` after each task.

---

## 1. Replace cast(...) call sites with a single typed accessor

Currently `analyzer.py` has multiple `cast(tuple[int, int], summary.attrs.get("coverage", ...))` and `cast(tuple[int, int] | None, summary.attrs.get("coverage"))` reads. The user dislikes this pattern repeated.

**Do:** Define ONE module-level helper:

```python
def _get_coverage(summary: pd.DataFrame) -> tuple[int, int] | None:
    """Read the (n_data, n_total) coverage tuple stamped by Analyzer._attach_coverage, if present."""
    return cast(tuple[int, int] | None, summary.attrs.get("coverage"))
```

Replace every `cast(tuple[int, int]...summary.attrs.get("coverage"...))` site with `_get_coverage(summary)`. Adjust the `match` statements: when `coverage is None`, treat as "no coverage info" (skip the suffix / band, same behavior as before). The cast must live in ONE place only.

---

## 2. Reduce `dict[str, Any]` at the client boundary

`fetch_current_user` returns `dict[str, Any]`. `fetch_user_playlists` returns `list[dict[str, Any]]`. Both leak Spotify's untyped shape to callers.

**Do:** Add two frozen dataclasses to `models.py`:

```python
@dataclass(frozen=True, slots=True)
class User:
    id: str
    display_name: str
    email: str | None  # may be missing depending on scopes

@dataclass(frozen=True, slots=True)
class PlaylistSummary:
    """Lightweight playlist listing — what fetch_user_playlists returns.

    Distinct from `Playlist` (which holds enriched tracks + artists).
    """
    id: str
    name: str
    owner_name: str
    track_count: int
    public: bool
```

Update `client.py`:
- `fetch_current_user(self) -> User` — parse at the boundary.
- `fetch_user_playlists(self) -> list[PlaylistSummary]` — parse at the boundary, still filtering out `None` slots.

The `dict[str, Any]` stays *inside* the methods (raw spotipy responses); only the return is typed. Update notebook + tests if any caller reads dict keys.

---

## 3. TimelineAnalyzer: REMOVE the release_date fallback entirely

Current behavior (after the previous Sonnet pass): TimelineAnalyzer falls back to `release_date` when `added_at` is missing, dropping year-only values. **The user wants no fallback at all.**

**Do:**
- TimelineAnalyzer uses **only `added_at`**.
- Drop rows where `added_at` is null or unparseable.
- Coverage = `(count of valid added_at, total rows)`.
- Drop the `source` column from the result DataFrame (only one source now).
- Update docstrings to remove all mention of `release_date` fallback.
- Update the `coverage()` override to count parseable `added_at` only.

If `added_at` is entirely missing (e.g. liked-songs has it; tests might not), return the empty result with `(0, n_total)` coverage.

---

## 4. Move coverage low-warning into the base — uniform across all analyzers

Currently `TimelineAnalyzer.analyze()` does its own `logger.warning` when coverage <70%. Other analyzers don't. The user wants this **consistent** across every analyzer.

**Do:** In `Analyzer._attach_coverage`:

```python
def _attach_coverage(self, summary: pd.DataFrame, df: pd.DataFrame) -> pd.DataFrame:
    n_data, n_total = self.coverage(df)
    if n_total > 0 and n_data / n_total < 0.7:
        logger.warning(
            "%s: low coverage %d/%d (%.0f%%)",
            self.effective_title, n_data, n_total, 100 * n_data / n_total,
        )
    summary.attrs["coverage"] = (n_data, n_total)
    return summary
```

Add `logger = logging.getLogger(__name__)` at module level if not already present (it is, per the previous pass).

**Then remove** the duplicate `logger.warning` from `TimelineAnalyzer.analyze()`.

The 70% threshold is shared — define it as a module-level constant `_LOW_COVERAGE_THRESHOLD = 0.7`.

---

## 5. Cache: preserve existing data, drop notebook hardcode

The previous pass set `DEFAULT_CACHE_DIR = _PROJECT_ROOT / ".cache"` but:
- The actual existing data is at `<repo_root>/.cache/api/<keys>` (the `/api` subfolder separates API cache from spotipy's `.cache/spotify_token`).
- The notebook still hardcodes `FileCache(root=Path(".cache") / "api")` — CWD-relative, defeats the whole purpose of anchoring.

**Do:**

1. In `cache.py`, change the default:
   ```python
   DEFAULT_CACHE_DIR = _PROJECT_ROOT / ".cache" / "api"
   ```
   This preserves the existing `.cache/api/` data unchanged.

2. In `notebooks/01_explore_playlist.ipynb`, change:
   ```python
   cache = FileCache(root=Path(".cache") / "api")
   ```
   to simply:
   ```python
   cache = FileCache()
   ```
   (Optionally drop the now-unused `from pathlib import Path` if no other notebook cell uses it.)

3. Update the notebook markdown that says *"The cache lives at `.cache/api/` (7-day TTL)"* to say something like *"The cache lives at the repo's `.cache/api/` folder regardless of where the notebook is launched from (7-day TTL)."*

**Verify:** after the change, instantiating `FileCache()` with no args must produce a `root` equal to `<repo_root>/.cache/api`. Tests still inject `tmp_path` so they're unaffected.

---

## Constraints

- Don't introduce TypedDicts. Don't bring back Pydantic.
- Per-line `# pyright: ignore[...]` comments stay; don't globally disable.
- After all 5 commits: `pytest`, `pyright`, `ruff check` must pass clean.
- If anything is ambiguous, ASK before guessing — the previous pass had two miscommunications (timeline fallback + cache notebook update) that you should not repeat.
