# Phase 1 Sprint C Design Spec — py_spotify_project

**Status:** Approved 2026-05-06.
**Predecessor:** [Sprint B plan](../plans/2026-05-05-spotify-phase1-sprint-b.md) — completed at commit `92c15cd`.
**Goal:** The final big sprint of Phase 1. Adds the Liked Songs feature, applies a coordinated visual polish across all six analyzer plots, ships coverage annotations so missing data is visible at-a-glance, cleans up known limitations carried from Sprint B, and finishes the deliverables (notebook narrative, README "how to run") for the oral exam.

Phase 2 (web UI / mutation features) is **out of scope**.

---

## 1. Liked Songs feature (highest priority)

**Why:** the user's primary playlist of interest has 3000+ tracks and is their Spotify-saved-tracks collection — not a regular playlist. Spotify exposes saved tracks via a different endpoint (`current_user_saved_tracks`), and the existing pipeline can't reach them.

### 1.1 Design choice: pseudo-playlist

Liked Songs is modeled as a synthesized `Playlist` with `id="__liked__"`, name `"Liked Songs"`, and the authenticated user's display name as owner. This keeps `PlaylistAnalyzer.from_playlist`, every analyzer, and the entire DataFrame schema unchanged. The "lie" at the type level is purely nominal — the `__liked__` id makes the synthesis self-documenting; nothing else in the codebase has to know.

### 1.2 New `SpotifyClient.liked_songs` method

```python
def liked_songs(self, *, force_refresh: bool = False) -> Playlist
```

Behavior:
- Cache key `liked/me` in the existing `FileCache`. On hit, return the cached pseudo-playlist data; on miss, paginate via `sp.current_user_saved_tracks(limit=50)` until exhausted, then cache. The 7-day TTL applies; `force_refresh=True` repays the API cost.
- Each saved-tracks page item has shape `{"track": {...}, "added_at": "..."}` — same shape `Track.from_api` already consumes.
- Same two-phase pattern as `playlist()`: paginate track items, deduplicate artist IDs across all pages, batch-enrich via `self.artists()`, then construct `Track` objects.
- Returns a `Playlist` with `id="__liked__"`, `name="Liked Songs"`, `owner_display_name=current_user["display_name"]`, `public=False`, `collaborative=False`, `description=""`, `tracks=...`.

### 1.3 Notebook integration

A one-line toggle in the existing fetch cell:

```python
PLAYLIST_ID = "3v8PWRLiPHGPY0oHgkoZvV"  # or "__liked__" for your saved tracks
playlist = client.liked_songs() if PLAYLIST_ID == "__liked__" else client.playlist(PLAYLIST_ID)
print(f"{playlist.name}: {len(playlist.tracks)} tracks")
```

### 1.4 Test coverage

One new test in `tests/test_client.py`:
- Mock `sp.current_user_saved_tracks` returning 3 pages (50 + 50 + 30 items). Mock `sp.artist` for the unique artists.
- Assert resulting `Playlist.id == "__liked__"`, `name == "Liked Songs"`, `len(tracks) == 130`, `tracks[0].primary_artist` is enriched.

---

## 2. Visual polish

### 2.1 Palette philosophy: per-analyzer colors

`seaborn.color_palette("colorblind", n_colors=6)` provides six visually distinct, accessible colors. Each analyzer gets one slot at orchestration time. Coverage annotations / mean / runtime lines use `"#444"` (neutral dark grey) regardless of panel color so they read consistently across all six plots.

### 2.2 Color wiring through the Analyzer ABC

The `Analyzer.plot()` signature gains an optional `color` keyword arg:

```python
def plot(self, ax: Axes, summary: pd.DataFrame, *, color: str | None = None) -> None
```

Each subclass:
- Uses `color` if passed, else falls back to a class-level `default_color: ClassVar[str]` (kept so a standalone `analyzer.plot(ax, summary)` outside the orchestrator still produces a sensible chart).

`PlaylistAnalyzer.plot_all` builds the palette once and zips it through:

```python
palette = sns.color_palette("colorblind", n_colors=len(self.analyzers))
for ax, analyzer, color in zip(axes_list, self.analyzers, palette, strict=True):
    analyzer.plot(ax, summaries[analyzer.effective_title], color=color)
```

### 2.3 Style tweaks (one helper, applied uniformly)

A module-level helper called from inside every `plot()` after data is rendered:

```python
def _style_axes(ax: Axes, title: str) -> None:
    ax.set_title(title, fontsize=12, fontweight="bold")
    ax.tick_params(colors="#666", labelsize=9)
    # x/y labels stay where each plot sets them, but apply small/grey:
    if ax.get_xlabel():
        ax.set_xlabel(ax.get_xlabel(), fontsize=10, color="#666")
    if ax.get_ylabel():
        ax.set_ylabel(ax.get_ylabel(), fontsize=10, color="#666")
```

Each `plot()` calls `_style_axes(ax, title_with_coverage_suffix)` after drawing data and before returning.

### 2.4 Coverage annotations (C.1 + C.2)

New method on `Analyzer`:

```python
def coverage(self, df: pd.DataFrame) -> tuple[int, int]:
    """Return (n_with_usable_data, n_total). Default: full coverage."""
    return (len(df), len(df))
```

Per-subclass overrides where coverage < 100% is plausible:
- `GenreAnalyzer.coverage`: `n = sum(1 for row_genres in df["genres"] if len(row_genres) > 0)`.
- `YearAnalyzer.coverage`: `n = df["release_date"].notna().sum()` filtered to parseable years.
- `TimelineAnalyzer.coverage`: `n = (df["added_at"].notna() | df.get("release_date", pd.Series([], dtype=object)).notna()).sum()`.
- Others (`Artist`, `Popularity`, `Duration`) inherit the default.

**Title suffix** computed by every analyzer's `plot()`:
```python
n_data, n_total = self.coverage(self_df_or_passed_df)  # see §2.5
suffix = "" if n_total == 0 or n_data == n_total else f" ({n_data}/{n_total} tracks, {n_data/n_total:.0%} coverage)"
```

But `plot()` doesn't have the original `df` — it only has the summary. So:

### 2.5 How coverage flows from analyze to plot

The `coverage` value is computed during `analyze()` (which has the full df) and stored on the summary's `pd.DataFrame.attrs["coverage"]: tuple[int, int]`. `plot()` reads `summary.attrs.get("coverage", (0, 0))`. This is the same pandas-supported metadata mechanism the Sprint B plan considered for `DurationAnalyzer` runtime stats but didn't end up using.

The `Analyzer` ABC gets a small concrete helper:

```python
def _attach_coverage(self, summary: pd.DataFrame, df: pd.DataFrame) -> pd.DataFrame:
    summary.attrs["coverage"] = self.coverage(df)
    return summary
```

Each subclass's `analyze()` calls `return self._attach_coverage(summary, df)` as its last step.

### 2.6 GenreAnalyzer-specific bottom band (C.2)

When `GenreAnalyzer.plot()` is called and coverage < 100%, draw a thin horizontal grey band beneath the bars indicating the missing fraction. Implementation:

```python
n_data, n_total = summary.attrs.get("coverage", (n_total, n_total))
if n_total > 0 and n_data < n_total:
    missing_frac = 1 - n_data / n_total
    # Grey band along the bottom 5% of the axes; missing fraction shaded darker.
    ax.axhspan(-0.5, -0.1, xmin=0, xmax=missing_frac, facecolor="#999", alpha=0.6, transform=ax.get_yaxis_transform())
```

(Exact axes-fraction values to be tuned during implementation; the spec just commits to "thin grey band beneath bars showing missing fraction".)

---

## 3. Cleanups carried from Sprint B

### 3.1 Drop `TimelineAnalyzer._last_source` instance state (C-emerged-1)

Replace the per-instance `_last_source` field with a `source` column on the summary DataFrame. Every row's `source` is the same string (`"added_at"` or `"release_date"`); `plot()` reads `summary["source"].iloc[0]`. This eliminates the temporal coupling that required `analyze()` to be called before `plot()`.

Final summary schema for `TimelineAnalyzer`: `[period, count, source]`.

### 3.2 Per-instance title override (C-emerged-2)

`Analyzer.__init__` (or each subclass's `__init__`) gains an optional `title: str | None = None` parameter. The base class exposes:

```python
@property
def effective_title(self) -> str:
    return self._instance_title if self._instance_title is not None else type(self).title
```

`__init_subclass__` continues to require a class-level `title` (default for the class). `PlaylistAnalyzer`'s duplicate-title guard already uses `a.title`; switch it to `a.effective_title`. `run_all` keys on `effective_title`. `plot_all` keys on `effective_title`.

This makes `PlaylistAnalyzer(analyzers=[YearAnalyzer(bucket_size=5, title="Years (5y)"), YearAnalyzer(bucket_size=10, title="Years (10y)")])` legal and well-defined.

### 3.3 Drop `all_artists` from the schema (B-followup-3)

The pipe-joined `all_artists` string is redundant with `artist_names: list[str]`. Drop it from the row dict in `PlaylistAnalyzer.from_playlist`. The notebook's display already prints `df.head()` which shows whatever columns exist; the pipe-string was never displayed by name. Update the parquet round-trip test fixture accordingly.

### 3.4 Update default analyzer list (B-followup-2)

`PlaylistAnalyzer.__init__` default analyzer list grows from 2 to 6:

```python
analyzers if analyzers is not None else [
    GenreAnalyzer(),
    YearAnalyzer(),
    ArtistAnalyzer(),
    PopularityAnalyzer(),
    DurationAnalyzer(),
    TimelineAnalyzer(),
]
```

The existing test `test_plot_all_with_no_analyzers_does_not_crash` passes `analyzers=[]` explicitly and is unaffected.

### 3.5 Add the missing `ArtistAnalyzer.analyze` ValueError test (B-followup-1)

Test that `ArtistAnalyzer().analyze(df)` raises `ValueError` when a row has `len(artist_ids) != len(artist_names)`. Already documented in the docstring; just no test exercised it yet.

---

## 4. Notebook narrative + README

### 4.1 Notebook markdown narrative (C.3)

Insert short (1–2 sentence) markdown cells before each code cell. Tone: factual, oral-exam friendly. Specifically:

- Before cell 1 (setup): one sentence on what's being imported and why `load_dotenv` matters.
- Before cell 9 (analyses): one sentence per analyzer, explaining what it shows and why it's interesting.
- Before cell 11 (plots): one sentence on the layout (six stacked subplots, colorblind palette).
- Before the parquet cell: one sentence on what the export contains and when it's useful.

The goal is that the grader can read the markdown alone and understand the demo's narrative.

### 4.2 README "How to run" section (C.4)

Fill the `## How to run` section in `README.md` with the actual concrete commands now that they're known:
1. Prerequisites (Python 3.11+, ~30s of read time).
2. `python -m venv .venv` and `.venv/Scripts/activate` (Windows) / `source .venv/bin/activate` (Unix).
3. `pip install -r requirements.txt`.
4. Spotify Developer App registration (link to dashboard, scopes needed).
5. Copy `.env.example` to `.env`, fill credentials.
6. Open `notebooks/01_explore_playlist.ipynb`, run all cells.

~30 lines total.

---

## 5. Test coverage target

Sprint B ended at 32 tests. Sprint C adds ~8:
- Liked Songs pagination (1).
- Per-analyzer `coverage()` override tests (3 — Genre, Year, Timeline).
- ArtistAnalyzer ValueError on mismatched lists (1).
- Title-instance-override (1).
- TimelineAnalyzer source column on summary (1, repurposing the existing fallback test).
- Sweep gaps surfaced during implementation (~1–2).

End-of-sprint target: **~40 tests passing.**

---

## 6. Task ordering (locked)

1. Visual: `Analyzer.plot()` color signature change + `_style_axes` helper + palette wiring in `plot_all`.
2. Visual: `Analyzer.coverage()` + per-class overrides + `_attach_coverage` + title suffix in every `plot()`.
3. Visual: `GenreAnalyzer` bottom band for missing-fraction.
4. Liked Songs: `SpotifyClient.liked_songs()` + test.
5. Cleanup: drop `TimelineAnalyzer._last_source`, replace with `source` column on summary.
6. Cleanup: title-instance-override (Analyzer + PlaylistAnalyzer guard switch + test).
7. Cleanup: drop `all_artists` from schema.
8. Cleanup: update `PlaylistAnalyzer` default analyzer list.
9. Cleanup: add `ArtistAnalyzer` ValueError test.
10. Notebook: narrative cells + Liked Songs toggle line + execute end-to-end against real Spotify.
11. README: fill `## How to run` section.

Ordering chosen so the visual-polish refactor (which touches every analyzer) lands first while the analyzers are still simple — adding new analyzers later (none planned, but if Sprint D ever happens) inherits the shape. Liked Songs lands after the visual changes so the new feature ships with the new style.

---

## 7. Out of scope

- **Phase 2:** web UI (Streamlit / FastAPI), mutation features (create/split/merge/dedupe playlists), any feature requiring `playlist-modify-*` scopes.
- **Bigger refactors:** splitting `analyzer.py` into per-class files (still small enough at the end of Sprint B; revisit only if Phase 2 starts).
- **Performance:** the file cache TTL stays at 7 days; we don't add invalidation hooks, partial-refresh logic, or pagination resume.
- **Audio features / recommendations / related-artists / etc.** — already documented as deprecated/dead in `CLAUDE.md`.

---

## 8. Out of plan

Anything not listed in §1–§6. Specifically:
- No new analyzer subclasses.
- No new caching layer.
- No new environment variables, config files, or CLI entry points.
- No changes to `models.py`, `cache.py`, or anything in `tests/test_models.py` / `tests/test_cache.py`.
