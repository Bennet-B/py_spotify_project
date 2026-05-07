# Phase 1 Sprint C Implementation Plan — py_spotify_project

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the final big sprint of Phase 1 — Liked Songs as a pseudo-playlist (`id="__liked__"`), a coordinated visual polish across all six analyzers (per-analyzer colorblind palette, bold titles, dim axis labels, coverage annotations in titles plus a missing-fraction band on `GenreAnalyzer`), Sprint B carry-over cleanups (`TimelineAnalyzer._last_source` → summary column, per-instance title override, drop redundant `all_artists` schema column, default-analyzer-list bump, missing `ArtistAnalyzer` ValueError test), oral-exam-friendly notebook narrative, and a finished README "How to run" section.

**Architecture:** Spec at [docs/superpowers/specs/2026-05-06-spotify-phase1-sprint-c.md](../specs/2026-05-06-spotify-phase1-sprint-c.md). Almost all work lives in `src/spotify_project/analyzer.py` and `tests/test_analyzer.py`; `client.py` gets one new method (Liked Songs); `notebooks/01_explore_playlist.ipynb` and `README.md` get final-pass updates. The visual changes thread through every analyzer's `plot()` (new optional `color` keyword arg + a shared `_style_axes` helper) but the analyze→plot data shape is unchanged except for `TimelineAnalyzer` (gains a `source` column) and the addition of `summary.attrs["coverage"]`.

**Tech Stack:** Same as Sprints A/B — Python 3.14, spotipy 2.26, pandas 2.3, matplotlib 3.10, **seaborn 0.13** (now used for palette generation, not just theming), pytest 8.4, ruff (format + lint), pyright strict. All in `.venv`.

---

## Pre-flight

Five seconds of check; mistakes prevented.

- [ ] **Step 0.1: Confirm working tree is clean enough**

  Run:
  ```
  git status
  ```
  Expected: clean, or only the kernel-metadata diff on the notebook (harmless). If anything else is modified (besides the standalone `test_output.txt` / `test_pyright.txt` scratch files which are gitignored), surface it before continuing.

- [ ] **Step 0.2: Confirm baseline tests pass**

  Run:
  ```
  .venv/Scripts/python.exe -m pytest -q
  ```
  Expected: `32 passed`. (Sprint B end-state.)

- [ ] **Step 0.3: Confirm pyright + ruff clean**

  Run:
  ```
  .venv/Scripts/python.exe -m pyright src tests
  .venv/Scripts/python.exe -m ruff check src tests
  .venv/Scripts/python.exe -m ruff format --check src tests
  ```
  Expected: `0 errors`, `All checks passed!`, `11 files already formatted`.

- [ ] **Step 0.4: Confirm seaborn is installed**

  We've been using seaborn for theming since Sprint A; we'll now also use it for `color_palette("colorblind", n_colors=6)`. Run:
  ```
  .venv/Scripts/python.exe -c "import seaborn; print(seaborn.__version__)"
  ```
  Expected: `0.13.x`. No version bump needed.

---

## File structure (locked)

| File | Tasks | Responsibility |
|---|---|---|
| `src/spotify_project/analyzer.py` | T1, T2, T3, T5, T6, T7, T8 | All analyzer-side changes (color signature, coverage method, schema cleanup, title override, default list, Timeline source column, GenreAnalyzer band) |
| `src/spotify_project/client.py` | T4 | New `SpotifyClient.liked_songs()` method |
| `tests/test_analyzer.py` | T1–T3, T5–T9 | New / updated analyzer tests |
| `tests/test_client.py` | T4 | Liked Songs pagination test |
| `tests/test_playlist_analyzer.py` | T7 | Update parquet fixture (drop `all_artists`) |
| `notebooks/01_explore_playlist.ipynb` | T10 | Narrative cells + Liked Songs toggle line + execute end-to-end |
| `README.md` | T11 | "How to run" section |

No new files. No deletions of source or test files. `analyzer.py` grows from ~620 to ~720 lines; still cohesive.

---

## Sprint C — tasks

### Task 1: Visual — `Analyzer.plot()` color signature + `_style_axes` helper + palette wiring

**Why first:** Mechanical change touching every analyzer's `plot()` and `PlaylistAnalyzer.plot_all`. Lands the wiring before Task 2 (coverage suffix) consumes it.

**Files:**
- Modify: `src/spotify_project/analyzer.py` (Analyzer ABC + 6 concrete subclasses + PlaylistAnalyzer.plot_all + module-level `_style_axes` helper)
- Modify: `tests/test_analyzer.py` (one new test for the color-passthrough)

- [ ] **Step 1.1: Write the failing test for color passthrough**

  Append to `tests/test_analyzer.py`:

  ```python
  def test_analyzer_plot_accepts_color_kwarg() -> None:
      """Each Analyzer subclass's plot() accepts a color= kwarg without raising.

      Pins the contract that PlaylistAnalyzer.plot_all relies on for palette
      threading. Doesn't assert color was actually used (matplotlib internals);
      just that the kwarg is supported.
      """
      from matplotlib.figure import Figure

      from spotify_project.analyzer import (
          ArtistAnalyzer,
          DurationAnalyzer,
          GenreAnalyzer,
          PopularityAnalyzer,
          TimelineAnalyzer,
          YearAnalyzer,
      )

      fig = Figure()
      ax = fig.subplots()
      df = _frame(
          [
              {
                  "track_id": "t1",
                  "genres": ["rock"],
                  "release_date": "2020-01-01",
                  "primary_artist_id": "a1",
                  "primary_artist_name": "Alice",
                  "artist_ids": ["a1"],
                  "artist_names": ["Alice"],
                  "duration_min": 3.0,
                  "popularity": 50,
                  "added_at": pd.Timestamp("2024-01-01", tz="UTC"),
              }
          ]
      )
      for cls in (
          GenreAnalyzer,
          YearAnalyzer,
          ArtistAnalyzer,
          PopularityAnalyzer,
          DurationAnalyzer,
          TimelineAnalyzer,
      ):
          analyzer = cls()
          summary = analyzer.analyze(df)
          analyzer.plot(ax, summary, color="#ff0000")
          ax.clear()
  ```

- [ ] **Step 1.2: Run the test — expect failure**

  Run:
  ```
  .venv/Scripts/python.exe -m pytest tests/test_analyzer.py::test_analyzer_plot_accepts_color_kwarg -v
  ```
  Expected: `TypeError: ... plot() got an unexpected keyword argument 'color'` (any analyzer's plot signature will fail).

- [ ] **Step 1.3: Add `default_color` to the Analyzer ABC and the `_style_axes` helper**

  In `src/spotify_project/analyzer.py`, locate the `Analyzer` ABC class. Add `default_color: ClassVar[str] = "#1f77b4"` immediately under `title: ClassVar[str]`. Then immediately above the `Analyzer` class, add this module-level helper:

  ```python
  def _style_axes(ax: Axes, base_title: str, summary: pd.DataFrame) -> None:
      """Apply the Sprint C consistent style + coverage suffix to an Axes.

      Reads ``summary.attrs["coverage"]`` (a ``(n_data, n_total)`` tuple
      attached by ``Analyzer._attach_coverage``); when present and < 100%,
      appends a coverage suffix to the title.

      Args:
          ax: The Matplotlib Axes to style.
          base_title: The analyzer's effective title, before coverage suffix.
          summary: The analyze() output. Used to read ``attrs["coverage"]``.
      """
      coverage = summary.attrs.get("coverage")
      suffix = ""
      if isinstance(coverage, tuple) and len(coverage) == 2:
          n_data, n_total = coverage
          if n_total > 0 and n_data < n_total:
              pct = n_data / n_total
              suffix = f" ({n_data}/{n_total} tracks, {pct:.0%} coverage)"
      ax.set_title(base_title + suffix, fontsize=12, fontweight="bold")
      ax.tick_params(colors="#666", labelsize=9)
      xlabel = ax.get_xlabel()
      ylabel = ax.get_ylabel()
      if xlabel:
          ax.set_xlabel(xlabel, fontsize=10, color="#666")
      if ylabel:
          ax.set_ylabel(ylabel, fontsize=10, color="#666")
  ```

  Note: `_style_axes` is called by every `plot()` after data is drawn (or after the empty-state placeholder). It tolerates a missing `attrs["coverage"]` (returns no suffix).

- [ ] **Step 1.4: Update `GenreAnalyzer.plot` signature and body**

  Replace `GenreAnalyzer.plot` with:

  ```python
      def plot(self, ax: Axes, summary: pd.DataFrame, *, color: str | None = None) -> None:
          """Render a horizontal bar chart of genre counts.

          Args:
              ax: Matplotlib Axes to draw on.
              summary: Output of ``analyze``; columns ``genre`` and ``count``.
              color: Bar color; defaults to the class's ``default_color``.
          """
          c = color if color is not None else self.default_color
          if summary.empty:
              ax.text(0.5, 0.5, "No genre data", ha="center", va="center")
              _style_axes(ax, self.effective_title, summary)
              return
          ax.barh(summary["genre"], summary["count"], color=c)
          ax.invert_yaxis()
          ax.set_xlabel("Track count")
          _style_axes(ax, self.effective_title, summary)
  ```

  (Don't worry about `effective_title` not being defined yet — Task 6 adds it. For now, replace `self.effective_title` with `self.title` everywhere in this and subsequent task code; Task 6's first step will swap them all to `effective_title` in one pass. Mark this as a known forward-reference.)

  **Read this carefully:** the plan presents the *final* plot bodies with `self.effective_title` to keep the code blocks coherent. Until Task 6 lands, every `self.effective_title` you copy must be temporarily written as `self.title`. Task 6 explicitly does the find-and-replace.

  Concretely, for Task 1 ONLY, copy the body above but with `self.title` everywhere. Same applies to all six analyzers in Tasks 1–3.

- [ ] **Step 1.5: Update `YearAnalyzer.plot` signature and body**

  ```python
      def plot(self, ax: Axes, summary: pd.DataFrame, *, color: str | None = None) -> None:
          """Render a vertical bar chart of track counts per year-bucket.

          Bar width is proportional to ``bucket_size`` so adjacent buckets
          touch (decade plot looks like a histogram, not isolated columns).

          Args:
              ax: Matplotlib Axes to draw on.
              summary: Output of ``analyze``; columns ``year`` and ``count``.
              color: Bar color; defaults to the class's ``default_color``.
          """
          c = color if color is not None else self.default_color
          if summary.empty:
              ax.text(0.5, 0.5, "No year data", ha="center", va="center")
              _style_axes(ax, self.title, summary)
              return
          ax.bar(
              summary["year"],
              summary["count"],
              width=self.bucket_size * 0.9,
              align="edge" if self.bucket_size > 1 else "center",
              color=c,
          )
          xlabel = (
              "Year"
              if self.bucket_size == 1
              else f"Year ({self.bucket_size}-year buckets)"
          )
          ax.set_xlabel(xlabel)
          ax.set_ylabel("Track count")
          _style_axes(ax, self.title, summary)
  ```

  (Replace the whole existing `plot` method.)

- [ ] **Step 1.6: Update `ArtistAnalyzer.plot` signature and body**

  ```python
      def plot(self, ax: Axes, summary: pd.DataFrame, *, color: str | None = None) -> None:
          """Render a horizontal bar chart of artists by track count.

          Args:
              ax: Matplotlib Axes to draw on.
              summary: Output of ``analyze``; must include ``artist_name``
                  and ``track_count`` columns.
              color: Bar color; defaults to the class's ``default_color``.
          """
          c = color if color is not None else self.default_color
          if summary.empty:
              ax.text(0.5, 0.5, "No artist data", ha="center", va="center")
              _style_axes(ax, self.title, summary)
              return
          ax.barh(summary["artist_name"], summary["track_count"], color=c)
          ax.invert_yaxis()
          ax.set_xlabel("Track count")
          _style_axes(ax, self.title, summary)
  ```

- [ ] **Step 1.7: Update `PopularityAnalyzer.plot` signature and body**

  ```python
      def plot(self, ax: Axes, summary: pd.DataFrame, *, color: str | None = None) -> None:
          """Render a histogram of popularity counts plus a vertical mean line.

          The mean is computed from the bin midpoints weighted by counts —
          accurate enough for visual annotation, even if the underlying data
          spread within bins is lost.

          Args:
              ax: Matplotlib Axes to draw on.
              summary: Output of ``analyze``.
              color: Bar color; defaults to the class's ``default_color``.
          """
          c = color if color is not None else self.default_color
          if summary.empty:
              ax.text(0.5, 0.5, "No popularity data", ha="center", va="center")
              _style_axes(ax, self.title, summary)
              return
          widths = summary["bin_high"] - summary["bin_low"]
          ax.bar(summary["bin_low"], summary["count"], width=widths, align="edge", color=c)
          midpoints = (summary["bin_low"] + summary["bin_high"]) / 2
          weighted_mean = (midpoints * summary["count"]).sum() / summary["count"].sum()
          ax.axvline(weighted_mean, linestyle="--", linewidth=1, color="#444")
          ax.set_xlabel("Popularity (0-100)")
          ax.set_ylabel("Track count")
          ax.set_xlim(0, 100)
          _style_axes(ax, f"{self.title} (mean ≈ {weighted_mean:.1f})", summary)
  ```

- [ ] **Step 1.8: Update `DurationAnalyzer.plot` signature and body**

  ```python
      def plot(self, ax: Axes, summary: pd.DataFrame, *, color: str | None = None) -> None:
          """Render a duration histogram with total-runtime annotation in the title.

          Args:
              ax: Matplotlib Axes to draw on.
              summary: Output of ``analyze``.
              color: Bar color; defaults to the class's ``default_color``.
          """
          c = color if color is not None else self.default_color
          if summary.empty:
              ax.text(0.5, 0.5, "No duration data", ha="center", va="center")
              _style_axes(ax, self.title, summary)
              return
          widths = summary["bin_high"] - summary["bin_low"]
          ax.bar(summary["bin_low"], summary["count"], width=widths, align="edge", color=c)
          total_min = round(summary["minutes_in_bin"].sum())
          hours = total_min // 60
          minutes = total_min % 60
          ax.set_xlabel("Duration (minutes)")
          ax.set_ylabel("Track count")
          _style_axes(ax, f"{self.title} (total runtime: {hours}h {minutes}m)", summary)
  ```

- [ ] **Step 1.9: Update `TimelineAnalyzer.plot` signature and body**

  Existing TimelineAnalyzer reads `self._last_source`. We keep that for now (Task 5 swaps it for the summary column). Just thread through `color` and `_style_axes`:

  ```python
      def plot(self, ax: Axes, summary: pd.DataFrame, *, color: str | None = None) -> None:
          """Render an area-style line chart of track additions over time.

          Args:
              ax: Matplotlib Axes to draw on.
              summary: Output of ``analyze``; columns ``period`` and ``count``.
              color: Line/fill color; defaults to the class's ``default_color``.
          """
          c = color if color is not None else self.default_color
          if summary.empty:
              ax.text(0.5, 0.5, "No timeline data", ha="center", va="center")
              _style_axes(ax, self.title, summary)
              return
          x: pd.Series[Any] = summary["period"].apply(lambda p: p.start_time)  # pyright: ignore[reportUnknownVariableType,reportUnknownArgumentType,reportUnknownLambdaType,reportUnknownMemberType]
          ax.fill_between(x, summary["count"], step="mid", alpha=0.4, color=c)
          ax.plot(x, summary["count"], marker="o", color=c)
          ax.set_xlabel("Time")
          ax.set_ylabel("Tracks added")
          source_label = (
              "added_at" if self._last_source == "added_at" else "release_date (fallback)"
          )
          _style_axes(ax, f"{self.title} (source: {source_label})", summary)
  ```

- [ ] **Step 1.10: Update `PlaylistAnalyzer.plot_all` to thread the palette**

  Locate `PlaylistAnalyzer.plot_all` and replace its body (the part after the early-return for `n == 0`):

  ```python
      def plot_all(self, fig: Figure) -> None:
          """Lay out one subplot per analyzer in a vertical stack on ``fig``.

          Each panel uses one color from seaborn's ``"colorblind"`` palette,
          assigned in registration order.

          Args:
              fig: Matplotlib Figure to subdivide with subplots.
          """
          n = len(self.analyzers)
          if n == 0:
              return
          summaries = self.run_all()
          axes = fig.subplots(n, 1)
          axes_list = [axes] if n == 1 else list(axes)
          palette = sns.color_palette("colorblind", n_colors=n)
          for ax, analyzer, color in zip(axes_list, self.analyzers, palette, strict=True):
              analyzer.plot(ax, summaries[analyzer.title], color=color)
          fig.tight_layout()
  ```

  Add `import seaborn as sns` near the existing top-level imports if not already present.

  Note `summaries[analyzer.title]` — Task 6 will update both this and `run_all` to use `effective_title`.

- [ ] **Step 1.11: Run the new test — expect pass**

  Run:
  ```
  .venv/Scripts/python.exe -m pytest tests/test_analyzer.py::test_analyzer_plot_accepts_color_kwarg -v
  ```
  Expected: `1 passed`.

- [ ] **Step 1.12: Run the full suite — confirm no regression**

  Run:
  ```
  .venv/Scripts/python.exe -m pytest -q
  ```
  Expected: `33 passed` (32 existing + 1 new).

- [ ] **Step 1.13: Format, lint, type-check**

  Run:
  ```
  .venv/Scripts/python.exe -m ruff format src tests
  .venv/Scripts/python.exe -m ruff check src tests
  .venv/Scripts/python.exe -m pyright src tests
  ```
  Expected: clean.

- [ ] **Step 1.14: Commit**

  ```
  git add src/spotify_project/analyzer.py tests/test_analyzer.py
  git commit -m "feat(analyzer): per-analyzer color kwarg, palette wiring, _style_axes helper"
  ```

> **CHECKPOINT 1 — STOP HERE.** Confirm the full test suite still passes and that ruff + pyright are clean. The next task adds the `coverage()` method on top of this scaffolding.

---

### Task 2: Visual — `Analyzer.coverage()` + per-class overrides + `_attach_coverage` + tests

**Files:**
- Modify: `src/spotify_project/analyzer.py` (Analyzer ABC + GenreAnalyzer + YearAnalyzer + TimelineAnalyzer + analyze() returns)
- Modify: `tests/test_analyzer.py` (3 new tests)

- [ ] **Step 2.1: Write the failing test for GenreAnalyzer coverage**

  Append to `tests/test_analyzer.py`:

  ```python
  def test_genre_analyzer_reports_partial_coverage_via_attrs() -> None:
      """GenreAnalyzer.analyze attaches (n_with_genres, n_total) to summary.attrs.

      Tracks with empty genres list count toward n_total but not n_with_genres.
      """
      df = _frame(
          [
              {"track_id": "1", "genres": ["rock", "indie"]},
              {"track_id": "2", "genres": ["pop"]},
              {"track_id": "3", "genres": []},
              {"track_id": "4", "genres": []},
          ]
      )
      summary = GenreAnalyzer().analyze(df)
      assert summary.attrs["coverage"] == (2, 4)
  ```

- [ ] **Step 2.2: Write the failing test for YearAnalyzer coverage**

  Append:

  ```python
  def test_year_analyzer_reports_coverage_via_attrs() -> None:
      """YearAnalyzer.analyze counts rows with parseable release_date."""
      df = _frame(
          [
              {"track_id": "1", "release_date": "2020-01-01"},
              {"track_id": "2", "release_date": "1979"},
              {"track_id": "3", "release_date": None},
              {"track_id": "4", "release_date": "not-a-date"},
          ]
      )
      summary = YearAnalyzer().analyze(df)
      # Rows 1, 2 parse cleanly. Row 3 is None. Row 4's first 4 chars "not-"
      # fail pd.to_numeric → NaN → dropped. So 2 of 4 cleanly contribute years.
      assert summary.attrs["coverage"] == (2, 4)
  ```

- [ ] **Step 2.3: Write the failing test for TimelineAnalyzer coverage**

  Append:

  ```python
  def test_timeline_analyzer_reports_coverage_via_attrs() -> None:
      """TimelineAnalyzer.analyze counts rows with usable date data.

      A row contributes to coverage if EITHER added_at OR release_date is
      parseable.
      """
      from datetime import UTC, datetime

      df = _frame(
          [
              {
                  "track_id": "1",
                  "added_at": datetime(2024, 1, 1, tzinfo=UTC),
                  "release_date": "2020-01-01",
              },
              {"track_id": "2", "added_at": None, "release_date": "2020-05-01"},
              {"track_id": "3", "added_at": None, "release_date": None},
              {
                  "track_id": "4",
                  "added_at": datetime(2024, 2, 1, tzinfo=UTC),
                  "release_date": None,
              },
          ]
      )
      summary = TimelineAnalyzer().analyze(df)
      # Rows 1, 2, 4 contribute (have at least one usable date). Row 3 doesn't.
      assert summary.attrs["coverage"] == (3, 4)
  ```

- [ ] **Step 2.4: Run the new tests — expect failure**

  Run:
  ```
  .venv/Scripts/python.exe -m pytest tests/test_analyzer.py -k "coverage_via_attrs" -v
  ```
  Expected: 3 failures with `KeyError: 'coverage'` or `assert {} == ...`.

- [ ] **Step 2.5: Add `coverage` + `_attach_coverage` to the `Analyzer` ABC**

  In `src/spotify_project/analyzer.py`, inside the `Analyzer` ABC (after the existing abstract `plot` method), add:

  ```python
      def coverage(self, df: pd.DataFrame) -> tuple[int, int]:
          """Return ``(n_with_usable_data, n_total)`` for this analyzer.

          Default returns full coverage. Override in subclasses where data
          can plausibly be missing (e.g. ``release_date`` for some albums,
          ``genres`` for some artists).

          Args:
              df: The track-level DataFrame.

          Returns:
              ``(n_with_usable_data, n_total)``.
          """
          n = len(df)
          return (n, n)

      def _attach_coverage(self, summary: pd.DataFrame, df: pd.DataFrame) -> pd.DataFrame:
          """Stamp coverage onto ``summary.attrs["coverage"]`` and return.

          Helper called by every concrete ``analyze()`` as its last step.

          Args:
              summary: The DataFrame that ``analyze`` is about to return.
              df: The track-level DataFrame the analyzer worked from.

          Returns:
              ``summary``, with ``attrs["coverage"]`` set.
          """
          summary.attrs["coverage"] = self.coverage(df)
          return summary
  ```

- [ ] **Step 2.6: Override `coverage` in `GenreAnalyzer`**

  Inside `GenreAnalyzer`, after `__init__`, add:

  ```python
      def coverage(self, df: pd.DataFrame) -> tuple[int, int]:
          """Count rows whose ``genres`` list is non-empty."""
          if df.empty or "genres" not in df.columns:
              return (0, len(df))
          n_with = int((df["genres"].apply(len) > 0).sum())
          return (n_with, len(df))
  ```

- [ ] **Step 2.7: Override `coverage` in `YearAnalyzer`**

  Inside `YearAnalyzer`, after `__init__`, add:

  ```python
      def coverage(self, df: pd.DataFrame) -> tuple[int, int]:
          """Count rows with a parseable 4-digit release year."""
          if df.empty or "release_date" not in df.columns:
              return (0, len(df))
          parsed = pd.to_numeric(df["release_date"].str.slice(0, 4), errors="coerce")
          n_with = int(parsed.notna().sum())
          return (n_with, len(df))
  ```

- [ ] **Step 2.8: Override `coverage` in `TimelineAnalyzer`**

  Inside `TimelineAnalyzer`, after `__init__`, add:

  ```python
      def coverage(self, df: pd.DataFrame) -> tuple[int, int]:
          """Count rows with EITHER added_at OR release_date parseable."""
          if df.empty:
              return (0, 0)
          added_at_ok = pd.to_datetime(df.get("added_at"), errors="coerce", utc=True).notna()
          release_date_ok = (
              pd.to_datetime(df["release_date"].astype(str), errors="coerce", utc=True).notna()
              if "release_date" in df.columns
              else pd.Series(False, index=df.index)
          )
          n_with = int((added_at_ok | release_date_ok).sum())
          return (n_with, len(df))
  ```

- [ ] **Step 2.9: Update each analyzer's `analyze()` to call `_attach_coverage`**

  In each of the six analyzer subclasses (Genre, Year, Artist, Popularity, Duration, Timeline), find the final `return` statement of `analyze()` and wrap the returned DataFrame:

  - GenreAnalyzer: change every `return ...` (including the early empty-df returns) to `return self._attach_coverage(<existing return value>, df)`.
  - Same pattern for the other five analyzers.

  Concrete example for `GenreAnalyzer.analyze` (replace all three return statements):

  ```python
      def analyze(self, df: pd.DataFrame) -> pd.DataFrame:
          # ... existing docstring ...
          if df.empty:
              return self._attach_coverage(pd.DataFrame({"genre": [], "count": []}), df)
          exploded = df.explode("genres").dropna(subset=["genres"])
          if exploded.empty:
              return self._attach_coverage(pd.DataFrame({"genre": [], "count": []}), df)
          result = (
              exploded.groupby("genres", as_index=False)
              .size()
              .rename(columns={"genres": "genre", "size": "count"})
              .sort_values("count", ascending=False)
              .head(self.top_n)
              .reset_index(drop=True)
          )
          return self._attach_coverage(result, df)
  ```

  Apply the analogous pattern to YearAnalyzer, ArtistAnalyzer, PopularityAnalyzer, DurationAnalyzer, TimelineAnalyzer. For TimelineAnalyzer specifically, the `_attach_coverage` call wraps the final reset_index result and the empty returns (this is independent of Task 5's source-column work — both can land cleanly).

- [ ] **Step 2.10: Run the coverage tests — expect pass**

  Run:
  ```
  .venv/Scripts/python.exe -m pytest tests/test_analyzer.py -k "coverage_via_attrs" -v
  ```
  Expected: `3 passed`.

- [ ] **Step 2.11: Run the full suite — expect no regression**

  Run:
  ```
  .venv/Scripts/python.exe -m pytest -q
  ```
  Expected: `36 passed` (33 from Task 1 + 3 new).

- [ ] **Step 2.12: Format, lint, type-check**

  Run:
  ```
  .venv/Scripts/python.exe -m ruff format src tests
  .venv/Scripts/python.exe -m ruff check src tests
  .venv/Scripts/python.exe -m pyright src tests
  ```
  Expected: clean.

- [ ] **Step 2.13: Commit**

  ```
  git add src/spotify_project/analyzer.py tests/test_analyzer.py
  git commit -m "feat(analyzer): coverage() method + per-class overrides + summary.attrs wiring"
  ```

> **CHECKPOINT 2 — STOP HERE.** Coverage now flows from analyze to the title via `_style_axes`. Verify by reading `_style_axes` and confirming the suffix logic is wired correctly.

---

### Task 3: Visual — `GenreAnalyzer` bottom band for missing-fraction

**Files:**
- Modify: `src/spotify_project/analyzer.py` (`GenreAnalyzer.plot` only)
- Modify: `tests/test_analyzer.py` (one new test)

- [ ] **Step 3.1: Write the failing test**

  Append to `tests/test_analyzer.py`:

  ```python
  def test_genre_analyzer_plot_draws_band_when_coverage_below_100() -> None:
      """GenreAnalyzer.plot adds an axhspan-style patch when coverage < 100%.

      Coarse check: count the number of patches added to the Axes after
      drawing. With full coverage, only the bar patches are present. With
      partial coverage, an additional patch (the missing-fraction band)
      appears.
      """
      from matplotlib.figure import Figure

      df_full = _frame(
          [
              {"track_id": "1", "genres": ["rock"]},
              {"track_id": "2", "genres": ["pop"]},
          ]
      )
      df_partial = _frame(
          [
              {"track_id": "1", "genres": ["rock"]},
              {"track_id": "2", "genres": []},
          ]
      )

      def _patch_count(d: pd.DataFrame) -> int:
          fig = Figure()
          ax = fig.subplots()
          analyzer = GenreAnalyzer()
          summary = analyzer.analyze(d)
          analyzer.plot(ax, summary)
          return len(ax.patches)

      patches_full = _patch_count(df_full)
      patches_partial = _patch_count(df_partial)
      assert patches_partial > patches_full
  ```

- [ ] **Step 3.2: Run the test — expect failure**

  Run:
  ```
  .venv/Scripts/python.exe -m pytest tests/test_analyzer.py::test_genre_analyzer_plot_draws_band_when_coverage_below_100 -v
  ```
  Expected: failure (patch counts equal, since the band isn't drawn yet).

- [ ] **Step 3.3: Add the band-drawing logic to `GenreAnalyzer.plot`**

  Replace the `GenreAnalyzer.plot` method body (the data path — keep the empty-state and `_style_axes` calls):

  ```python
      def plot(self, ax: Axes, summary: pd.DataFrame, *, color: str | None = None) -> None:
          """Render a horizontal bar chart of genre counts, plus a
          missing-fraction band beneath the bars when coverage is partial.

          Args:
              ax: Matplotlib Axes to draw on.
              summary: Output of ``analyze``; columns ``genre`` and ``count``.
              color: Bar color; defaults to the class's ``default_color``.
          """
          c = color if color is not None else self.default_color
          if summary.empty:
              ax.text(0.5, 0.5, "No genre data", ha="center", va="center")
              _style_axes(ax, self.title, summary)
              return
          ax.barh(summary["genre"], summary["count"], color=c)
          ax.invert_yaxis()
          ax.set_xlabel("Track count")
          coverage = summary.attrs.get("coverage")
          if isinstance(coverage, tuple) and len(coverage) == 2:
              n_data, n_total = coverage
              if n_total > 0 and n_data < n_total:
                  missing_frac = 1 - n_data / n_total
                  # Draw a thin grey band along the bottom 4% of the axes,
                  # shading the missing fraction. Uses axes-fraction
                  # transform so it sits independent of the bar y-coords.
                  ax.axhspan(
                      ymin=-0.05,
                      ymax=-0.01,
                      xmin=0.0,
                      xmax=missing_frac,
                      facecolor="#999",
                      alpha=0.6,
                      transform=ax.get_yaxis_transform(),
                      clip_on=False,
                  )
          _style_axes(ax, self.title, summary)
  ```

- [ ] **Step 3.4: Run the test — expect pass**

  Run:
  ```
  .venv/Scripts/python.exe -m pytest tests/test_analyzer.py::test_genre_analyzer_plot_draws_band_when_coverage_below_100 -v
  ```
  Expected: `1 passed`.

- [ ] **Step 3.5: Run the full suite**

  Run:
  ```
  .venv/Scripts/python.exe -m pytest -q
  ```
  Expected: `37 passed`.

- [ ] **Step 3.6: Format, lint, type-check**

  Run:
  ```
  .venv/Scripts/python.exe -m ruff format src tests
  .venv/Scripts/python.exe -m ruff check src tests
  .venv/Scripts/python.exe -m pyright src tests
  ```
  Expected: clean.

- [ ] **Step 3.7: Commit**

  ```
  git add src/spotify_project/analyzer.py tests/test_analyzer.py
  git commit -m "feat(analyzer): GenreAnalyzer bottom band for missing-genre fraction"
  ```

---

### Task 4: Liked Songs — `SpotifyClient.liked_songs()` (test-first)

**Files:**
- Modify: `src/spotify_project/client.py`
- Modify: `tests/test_client.py`

**Implementation note:** `current_user_saved_tracks()` returns items with `{"track": {...}, "added_at": ...}` (legacy key). `Track.from_api` reads `item["item"]` (Feb 2026 rename). So `liked_songs()` rewrites each saved-track item to `{"item": <track_data>, "added_at": ..., "is_local": False}` during page collection.

- [ ] **Step 4.1: Write the failing pagination test**

  Append to `tests/test_client.py`:

  ```python
  def _saved_track_item(idx: int, artist_id: str = "a1") -> dict[str, Any]:
      """Build a spotipy current_user_saved_tracks item — uses legacy 'track' key."""
      return {
          "track": {
              "id": f"st{idx}",
              "name": f"Saved Track {idx}",
              "type": "track",
              "artists": [{"id": artist_id, "name": "Artist 1"}],
              "album": {"name": "Album", "release_date": "2020-01-01"},
              "duration_ms": 200_000,
              "popularity": 50,
              "explicit": False,
          },
          "added_at": "2024-06-01T00:00:00Z",
      }


  def test_liked_songs_paginates_and_synthesizes_pseudo_playlist(tmp_path: Path) -> None:
      """SpotifyClient.liked_songs paginates saved tracks and returns a pseudo-Playlist.

      The synthetic Playlist has id="__liked__", name="Liked Songs", owner from
      the authenticated user's display_name, and concatenated tracks from all
      pages. Each Track ends up enriched with full Artist data.
      """
      cache = FileCache(root=tmp_path)
      fake_sp = MagicMock()

      fake_sp.current_user.return_value = {"id": "me", "display_name": "Bennet"}
      fake_sp.current_user_saved_tracks.return_value = {
          "items": [_saved_track_item(i) for i in range(50)],
          "next": "next_url_1",
      }
      fake_sp.next.side_effect = [
          {
              "items": [_saved_track_item(i) for i in range(50, 100)],
              "next": "next_url_2",
          },
          {
              "items": [_saved_track_item(i) for i in range(100, 130)],
              "next": None,
          },
      ]
      fake_sp.artist.return_value = {
          "id": "a1",
          "name": "Artist 1",
          "genres": ["rock", "indie"],
          "popularity": 70,
      }

      client = SpotifyClient(sp=fake_sp, cache=cache)
      playlist = client.liked_songs()

      assert playlist.id == "__liked__"
      assert playlist.name == "Liked Songs"
      assert playlist.owner_display_name == "Bennet"
      assert len(playlist.tracks) == 130
      first = playlist.tracks[0].primary_artist
      assert first is not None
      assert first.name == "Artist 1"
      assert "rock" in first.genres
  ```

  Make sure `Path`, `MagicMock`, `FileCache`, and `SpotifyClient` are already imported (they are, from the existing `test_playlist_paginates_and_enriches_artists` test). Also verify `Any` is imported from `typing`; if not, add `from typing import Any` to the top.

- [ ] **Step 4.2: Run the test — expect AttributeError**

  Run:
  ```
  .venv/Scripts/python.exe -m pytest tests/test_client.py::test_liked_songs_paginates_and_synthesizes_pseudo_playlist -v
  ```
  Expected: `AttributeError: 'SpotifyClient' object has no attribute 'liked_songs'`.

- [ ] **Step 4.3: Implement `liked_songs`**

  In `src/spotify_project/client.py`, add this method to `SpotifyClient`, immediately after the existing `playlist` method:

  ```python
      def liked_songs(self, *, force_refresh: bool = False) -> Playlist:
          """Fetch the authenticated user's saved tracks as a pseudo-Playlist.

          Spotify's "Liked Songs" is not a real playlist — it has no id, no
          owner, no description. We model it as a synthesized ``Playlist``
          with ``id="__liked__"`` so the rest of the pipeline (Track parsing,
          PlaylistAnalyzer, every analyzer) consumes it unchanged.

          Two-phase like ``playlist()``: paginate ``current_user_saved_tracks``
          (50/page), then batch-fetch unique artists.

          Args:
              force_refresh: Skip the cache and refetch from the API. The
                  cached blob can be several MB for 3000+ saved tracks; the
                  default 7-day ``FileCache`` TTL applies.

          Returns:
              A pseudo-Playlist with id ``"__liked__"`` and name ``"Liked Songs"``.
          """
          cache_key = "liked/me"
          cached = None if force_refresh else self.cache.get(cache_key)
          data: dict[str, Any]
          if cached is None:
              first = cast(
                  dict[str, Any], self.sp.current_user_saved_tracks(limit=50)
              )
              # Convert legacy {"track": ...} → {"item": ...} so the rest of
              # the pipeline (which reads item["item"]) can consume unchanged.
              raw_items: list[dict[str, Any]] = list(first["items"])
              page: dict[str, Any] = first
              while page.get("next"):
                  page = cast(dict[str, Any], self.sp.next(page))
                  raw_items.extend(page["items"])
              items: list[dict[str, Any]] = [
                  {
                      "item": it["track"],
                      "added_at": it.get("added_at"),
                      "is_local": False,
                  }
                  for it in raw_items
                  if it.get("track")
              ]
              me = cast(dict[str, Any], self.sp.current_user())
              data = {
                  "id": "__liked__",
                  "name": "Liked Songs",
                  "owner": {"display_name": me.get("display_name", "")},
                  "public": False,
                  "collaborative": False,
                  "description": "",
                  "items": {"items": items},
              }
              self.cache.put(cache_key, data)
          else:
              data = cached
              items = data["items"]["items"]

          track_items = [
              it
              for it in items
              if it.get("item") and it["item"].get("type") == "track"
          ]

          artist_ids: set[str] = set()
          for item in track_items:
              for a in item["item"].get("artists", []):
                  if a.get("id"):
                      artist_ids.add(a["id"])

          artist_by_id: dict[str, Artist] = {
              a.id: a for a in self.artists(artist_ids, force_refresh=force_refresh)
          }

          tracks = [Track.from_api(item, artist_by_id) for item in track_items]
          return Playlist.from_api(data, tracks)
  ```

- [ ] **Step 4.4: Run the test — expect pass**

  Run:
  ```
  .venv/Scripts/python.exe -m pytest tests/test_client.py::test_liked_songs_paginates_and_synthesizes_pseudo_playlist -v
  ```
  Expected: `1 passed`.

- [ ] **Step 4.5: Run the full suite**

  Run:
  ```
  .venv/Scripts/python.exe -m pytest -q
  ```
  Expected: `38 passed`.

- [ ] **Step 4.6: Format, lint, type-check**

  Run:
  ```
  .venv/Scripts/python.exe -m ruff format src tests
  .venv/Scripts/python.exe -m ruff check src tests
  .venv/Scripts/python.exe -m pyright src tests
  ```
  Expected: clean.

- [ ] **Step 4.7: Commit**

  ```
  git add src/spotify_project/client.py tests/test_client.py
  git commit -m "feat(client): liked_songs() — saved tracks as a pseudo-Playlist (id=__liked__)"
  ```

> **CHECKPOINT 3 — STOP HERE.** Liked Songs ships. The notebook update in Task 10 will toggle between playlist and liked songs.

---

### Task 5: Cleanup — replace `TimelineAnalyzer._last_source` with summary `source` column

**Files:**
- Modify: `src/spotify_project/analyzer.py` (TimelineAnalyzer)
- Modify: `tests/test_analyzer.py` (update existing tests, add one)

- [ ] **Step 5.1: Add a test asserting the summary has a `source` column**

  Append to `tests/test_analyzer.py`:

  ```python
  def test_timeline_analyzer_summary_includes_source_column() -> None:
      """TimelineAnalyzer.analyze stamps the source ('added_at' or 'release_date')
      onto every row of the summary, eliminating the need for instance state."""
      from datetime import UTC, datetime

      df_added_at = _frame(
          [{"track_id": "1", "added_at": datetime(2024, 1, 1, tzinfo=UTC)}]
      )
      summary_added = TimelineAnalyzer().analyze(df_added_at)
      assert "source" in summary_added.columns
      assert (summary_added["source"] == "added_at").all()

      df_release = _frame(
          [{"track_id": "1", "added_at": None, "release_date": "2020-05-01"}]
      )
      summary_release = TimelineAnalyzer().analyze(df_release)
      assert (summary_release["source"] == "release_date").all()
  ```

- [ ] **Step 5.2: Run — expect failure**

  Run:
  ```
  .venv/Scripts/python.exe -m pytest tests/test_analyzer.py::test_timeline_analyzer_summary_includes_source_column -v
  ```
  Expected: `KeyError: 'source'` (or similar — column doesn't exist yet).

- [ ] **Step 5.3: Update `TimelineAnalyzer` to drop `_last_source` and add `source` column**

  Replace the entire `TimelineAnalyzer` class body. The new shape:

  ```python
  class TimelineAnalyzer(Analyzer):
      """Track-addition timeline, grouped by period.

      Falls back to ``release_date`` when ``added_at`` is entirely missing —
      typical for Spotify-curated playlists, whose API responses set
      ``added_at: null`` on every item.

      Args:
          freq: pandas Period frequency string. Default ``"M"`` (month).
              ``"Y"`` for yearly, ``"W"`` for weekly. Validated by pandas.
      """

      title = "Track Timeline"

      def __init__(self, freq: str = "M") -> None:
          self.freq = freq

      def coverage(self, df: pd.DataFrame) -> tuple[int, int]:
          """Count rows with EITHER added_at OR release_date parseable."""
          if df.empty:
              return (0, 0)
          added_at_ok = pd.to_datetime(df.get("added_at"), errors="coerce", utc=True).notna()
          release_date_ok = (
              pd.to_datetime(df["release_date"].astype(str), errors="coerce", utc=True).notna()
              if "release_date" in df.columns
              else pd.Series(False, index=df.index)
          )
          n_with = int((added_at_ok | release_date_ok).sum())
          return (n_with, len(df))

      def analyze(self, df: pd.DataFrame) -> pd.DataFrame:
          """Group track additions (or release dates) into time-period buckets.

          Args:
              df: Track-level DataFrame; must contain ``added_at`` and
                  optionally ``release_date``.

          Returns:
              DataFrame with columns ``period`` (pandas Period), ``count``,
              and ``source`` (``"added_at"`` or ``"release_date"``, repeated
              on every row), sorted ascending by period.
          """
          empty = pd.DataFrame({"period": [], "count": [], "source": []})
          if df.empty:
              return self._attach_coverage(empty, df)

          source_col = "added_at"
          raw: pd.Series[Any] = (
              df["added_at"]
              if "added_at" in df.columns
              else pd.Series([], dtype=object)
          )
          values: pd.Series[Any] = pd.to_datetime(raw, errors="coerce", utc=True)
          if values.isna().all() and "release_date" in df.columns:
              source_col = "release_date"
              values = pd.to_datetime(
                  df["release_date"].astype(str), errors="coerce", utc=True
              )

          values = values.dropna()
          if values.empty:
              return self._attach_coverage(empty, df)

          periods: pd.Series[Any] = values.dt.tz_localize(None).dt.to_period(self.freq)
          result: pd.DataFrame = (
              periods.value_counts()
              .sort_index()
              .rename_axis("period")
              .reset_index(name="count")
          )
          result["source"] = source_col
          return self._attach_coverage(result, df)

      def plot(self, ax: Axes, summary: pd.DataFrame, *, color: str | None = None) -> None:
          """Render an area-style line chart of track additions over time.

          Args:
              ax: Matplotlib Axes to draw on.
              summary: Output of ``analyze``; columns ``period``, ``count``, ``source``.
              color: Line/fill color; defaults to the class's ``default_color``.
          """
          c = color if color is not None else self.default_color
          if summary.empty:
              ax.text(0.5, 0.5, "No timeline data", ha="center", va="center")
              _style_axes(ax, self.title, summary)
              return
          x: pd.Series[Any] = summary["period"].apply(lambda p: p.start_time)  # pyright: ignore[reportUnknownVariableType,reportUnknownArgumentType,reportUnknownLambdaType,reportUnknownMemberType]
          ax.fill_between(x, summary["count"], step="mid", alpha=0.4, color=c)
          ax.plot(x, summary["count"], marker="o", color=c)
          ax.set_xlabel("Time")
          ax.set_ylabel("Tracks added")
          source_col = str(summary["source"].iloc[0])
          source_label = (
              "added_at" if source_col == "added_at" else "release_date (fallback)"
          )
          _style_axes(ax, f"{self.title} (source: {source_label})", summary)
  ```

- [ ] **Step 5.4: Run the new test — expect pass**

  Run:
  ```
  .venv/Scripts/python.exe -m pytest tests/test_analyzer.py::test_timeline_analyzer_summary_includes_source_column -v
  ```
  Expected: `1 passed`.

- [ ] **Step 5.5: Run all timeline tests — confirm no regression**

  Run:
  ```
  .venv/Scripts/python.exe -m pytest tests/test_analyzer.py -k timeline -v
  ```
  Expected: 4 passed (3 existing + 1 new). The 3 existing should still pass — they don't read `_last_source` directly, only assert the period/count contract.

- [ ] **Step 5.6: Run the full suite**

  Run:
  ```
  .venv/Scripts/python.exe -m pytest -q
  ```
  Expected: `39 passed`.

- [ ] **Step 5.7: Format, lint, type-check**

  Run:
  ```
  .venv/Scripts/python.exe -m ruff format src tests
  .venv/Scripts/python.exe -m ruff check src tests
  .venv/Scripts/python.exe -m pyright src tests
  ```
  Expected: clean.

- [ ] **Step 5.8: Commit**

  ```
  git add src/spotify_project/analyzer.py tests/test_analyzer.py
  git commit -m "refactor(analyzer): TimelineAnalyzer summary gains source column, drop instance state"
  ```

---

### Task 6: Cleanup — per-instance title override

**Files:**
- Modify: `src/spotify_project/analyzer.py` (Analyzer ABC + 6 subclasses' `__init__` + PlaylistAnalyzer)
- Modify: `tests/test_analyzer.py` (one new test)

- [ ] **Step 6.1: Write the failing test**

  Append:

  ```python
  def test_playlist_analyzer_accepts_two_year_analyzers_with_distinct_titles() -> None:
      """Per-instance title override lets two same-class instances coexist.

      Without the override, registering two YearAnalyzer instances would
      collide on the class-level title. With the override, a custom title=
      kwarg gives each its own slot.
      """
      pa = PlaylistAnalyzer(
          df=pd.DataFrame(),
          analyzers=[
              YearAnalyzer(bucket_size=5, title="Years (5y)"),
              YearAnalyzer(bucket_size=10, title="Years (10y)"),
          ],
      )
      titles = [a.effective_title for a in pa.analyzers]
      assert titles == ["Years (5y)", "Years (10y)"]
  ```

- [ ] **Step 6.2: Run — expect failure**

  Run:
  ```
  .venv/Scripts/python.exe -m pytest tests/test_analyzer.py::test_playlist_analyzer_accepts_two_year_analyzers_with_distinct_titles -v
  ```
  Expected: `TypeError: YearAnalyzer.__init__() got an unexpected keyword argument 'title'`.

- [ ] **Step 6.3: Add `effective_title` property to the Analyzer ABC**

  In `src/spotify_project/analyzer.py`, inside `Analyzer`, after `__init_subclass__`, add:

  ```python
      @property
      def effective_title(self) -> str:
          """Return the per-instance title if set, else the class-level ``title``.

          Per-instance titles are set by passing ``title=`` to a concrete
          analyzer's constructor. They let multiple instances of the same
          subclass coexist in one ``PlaylistAnalyzer`` without colliding on
          the dict key in ``run_all``.
          """
          instance_title = getattr(self, "_instance_title", None)
          return instance_title if instance_title is not None else type(self).title
  ```

  (`getattr` with default makes it safe even for analyzers whose `__init__` doesn't accept `title=`.)

- [ ] **Step 6.4: Add `title` kwarg to each analyzer subclass's `__init__`**

  For each of the six analyzers (Genre, Year, Artist, Popularity, Duration, Timeline), update its `__init__` to accept and store `title`. Examples:

  **GenreAnalyzer:**
  ```python
      def __init__(self, top_n: int = 15, *, title: str | None = None) -> None:
          self.top_n = top_n
          self._instance_title = title
  ```

  **YearAnalyzer:**
  ```python
      def __init__(self, bucket_size: int = 1, *, title: str | None = None) -> None:
          if bucket_size < 1:
              raise ValueError(
                  f"bucket_size must be a positive integer, got {bucket_size}"
              )
          self.bucket_size = bucket_size
          self._instance_title = title
  ```

  **ArtistAnalyzer:**
  ```python
      def __init__(
          self,
          top_n: int = 15,
          primary_only: bool = False,
          *,
          title: str | None = None,
      ) -> None:
          self.top_n = top_n
          self.primary_only = primary_only
          self._instance_title = title
  ```

  **PopularityAnalyzer:**
  ```python
      def __init__(self, bins: int = 10, *, title: str | None = None) -> None:
          if bins < 1:
              raise ValueError(f"bins must be a positive integer, got {bins}")
          self.bins = bins
          self._instance_title = title
  ```

  **DurationAnalyzer:**
  ```python
      def __init__(self, bins: int = 20, *, title: str | None = None) -> None:
          if bins < 1:
              raise ValueError(f"bins must be a positive integer, got {bins}")
          self.bins = bins
          self._instance_title = title
  ```

  **TimelineAnalyzer:**
  ```python
      def __init__(self, freq: str = "M", *, title: str | None = None) -> None:
          self.freq = freq
          self._instance_title = title
  ```

- [ ] **Step 6.5: Switch `run_all` and the duplicate-title guard from `title` to `effective_title`**

  In `PlaylistAnalyzer.__init__`, replace:
  ```python
          titles = [a.title for a in self.analyzers]
  ```
  with:
  ```python
          titles = [a.effective_title for a in self.analyzers]
  ```

  In `PlaylistAnalyzer.run_all`, replace:
  ```python
          return {a.title: a.analyze(self.df) for a in self.analyzers}
  ```
  with:
  ```python
          return {a.effective_title: a.analyze(self.df) for a in self.analyzers}
  ```

  In `PlaylistAnalyzer.plot_all`, replace:
  ```python
              analyzer.plot(ax, summaries[analyzer.title], color=color)
  ```
  with:
  ```python
              analyzer.plot(ax, summaries[analyzer.effective_title], color=color)
  ```

- [ ] **Step 6.6: Switch every analyzer's `plot` to use `self.effective_title`**

  In each of the six `plot` methods, find every `_style_axes(ax, self.title, ...)` call and change `self.title` to `self.effective_title`. Same for `f"{self.title} (...)"` formatting.

  Locations to change:
  - GenreAnalyzer.plot — 2 calls (one in empty path, one in data path)
  - YearAnalyzer.plot — 2 calls
  - ArtistAnalyzer.plot — 2 calls
  - PopularityAnalyzer.plot — 2 calls (one is `_style_axes(ax, f"{self.title} (mean ≈ ...)", summary)` — change to `f"{self.effective_title} (mean ≈ ...)"`)
  - DurationAnalyzer.plot — 2 calls (`f"{self.title} (total runtime: ...)"` → `f"{self.effective_title} (total runtime: ...)"`)
  - TimelineAnalyzer.plot — 2 calls

- [ ] **Step 6.7: Run the failing test — expect pass**

  Run:
  ```
  .venv/Scripts/python.exe -m pytest tests/test_analyzer.py::test_playlist_analyzer_accepts_two_year_analyzers_with_distinct_titles -v
  ```
  Expected: `1 passed`.

- [ ] **Step 6.8: Run the full suite**

  Run:
  ```
  .venv/Scripts/python.exe -m pytest -q
  ```
  Expected: `40 passed`.

- [ ] **Step 6.9: Format, lint, type-check**

  Run:
  ```
  .venv/Scripts/python.exe -m ruff format src tests
  .venv/Scripts/python.exe -m ruff check src tests
  .venv/Scripts/python.exe -m pyright src tests
  ```
  Expected: clean.

- [ ] **Step 6.10: Commit**

  ```
  git add src/spotify_project/analyzer.py tests/test_analyzer.py
  git commit -m "feat(analyzer): per-instance title override for same-class analyzer combos"
  ```

> **CHECKPOINT 4 — STOP HERE.** All visual + ABC plumbing is in. The remaining tasks are smaller cleanups + notebook + README.

---

### Task 7: Cleanup — drop `all_artists` from the schema

**Files:**
- Modify: `src/spotify_project/analyzer.py` (`PlaylistAnalyzer.from_playlist`)
- Modify: `tests/test_playlist_analyzer.py` (parquet fixture)
- Modify: `tests/test_analyzer.py` (any test referencing `all_artists` — likely none, but verify)

- [ ] **Step 7.1: Drop the key from `from_playlist`**

  In `src/spotify_project/analyzer.py`, inside `PlaylistAnalyzer.from_playlist`, locate the row dict and remove the `"all_artists": ...` line. The before:

  ```python
                  "primary_artist_name": primary.name if primary else "",
                  "all_artists": " | ".join(a.name for a in t.artists),
                  "artist_ids": [a.id for a in t.artists],
                  "artist_names": [a.name for a in t.artists],
                  "album_name": t.album_name,
  ```

  After:

  ```python
                  "primary_artist_name": primary.name if primary else "",
                  "artist_ids": [a.id for a in t.artists],
                  "artist_names": [a.name for a in t.artists],
                  "album_name": t.album_name,
  ```

- [ ] **Step 7.2: Update the parquet round-trip test fixture**

  In `tests/test_playlist_analyzer.py`, find the dict containing `"all_artists": "Alice"` and remove that key (just the one line). The test assertions reference `artist_ids`, `artist_names`, `genres` — none of them reference `all_artists`, so the assertions don't need changes.

- [ ] **Step 7.3: Search for any other reference to `all_artists`**

  Run:
  ```
  .venv/Scripts/python.exe -c "import pathlib; [print(p) for p in pathlib.Path('.').rglob('*.py') if 'all_artists' in p.read_text(encoding='utf-8')]"
  ```
  Expected: only `tests/test_playlist_analyzer.py` (already updated). If anything else surfaces, update it (drop the reference); the column is gone.

  Also check the notebook:
  ```
  .venv/Scripts/python.exe -c "import json; nb = json.load(open('notebooks/01_explore_playlist.ipynb', encoding='utf-8')); [print(i, 'has all_artists') for i, c in enumerate(nb['cells']) if c.get('cell_type') == 'code' and any('all_artists' in line for line in c.get('source', []))]"
  ```
  Expected: empty output (no notebook cell references it).

- [ ] **Step 7.4: Run the full suite**

  Run:
  ```
  .venv/Scripts/python.exe -m pytest -q
  ```
  Expected: `40 passed` (no test relied on `all_artists` being present).

- [ ] **Step 7.5: Format, lint, type-check**

  Run:
  ```
  .venv/Scripts/python.exe -m ruff format src tests
  .venv/Scripts/python.exe -m ruff check src tests
  .venv/Scripts/python.exe -m pyright src tests
  ```
  Expected: clean.

- [ ] **Step 7.6: Commit**

  ```
  git add src/spotify_project/analyzer.py tests/test_playlist_analyzer.py
  git commit -m "refactor(analyzer): drop all_artists pipe-string column (redundant with artist_names)"
  ```

---

### Task 8: Cleanup — bump default analyzer list to all 6

**Files:**
- Modify: `src/spotify_project/analyzer.py` (`PlaylistAnalyzer.__init__`)

- [ ] **Step 8.1: Update the default list**

  In `src/spotify_project/analyzer.py`, find `PlaylistAnalyzer.__init__` and replace the `else [...]` block:

  Before:
  ```python
          self.analyzers = (
              analyzers
              if analyzers is not None
              else [
                  GenreAnalyzer(),
                  YearAnalyzer(),
              ]
          )
  ```

  After:
  ```python
          self.analyzers = (
              analyzers
              if analyzers is not None
              else [
                  GenreAnalyzer(),
                  YearAnalyzer(),
                  ArtistAnalyzer(),
                  PopularityAnalyzer(),
                  DurationAnalyzer(),
                  TimelineAnalyzer(),
              ]
          )
  ```

- [ ] **Step 8.2: Run the full suite**

  Run:
  ```
  .venv/Scripts/python.exe -m pytest -q
  ```
  Expected: `40 passed`. The existing test `test_plot_all_with_no_analyzers_does_not_crash` passes `analyzers=[]` explicitly and is unaffected; no test uses the default-list path so nothing else changes.

- [ ] **Step 8.3: Format, lint, type-check**

  Run:
  ```
  .venv/Scripts/python.exe -m ruff format src
  .venv/Scripts/python.exe -m ruff check src
  .venv/Scripts/python.exe -m pyright src
  ```
  Expected: clean.

- [ ] **Step 8.4: Commit**

  ```
  git add src/spotify_project/analyzer.py
  git commit -m "feat(analyzer): default PlaylistAnalyzer registers all six analyzers"
  ```

---

### Task 9: Test — ArtistAnalyzer ValueError on mismatched lists

**Files:**
- Modify: `tests/test_analyzer.py`

- [ ] **Step 9.1: Add the test**

  Append to `tests/test_analyzer.py`:

  ```python
  def test_artist_analyzer_raises_value_error_on_mismatched_list_lengths() -> None:
      """ArtistAnalyzer.analyze raises ValueError when artist_ids and
      artist_names lists are different lengths in any row.

      The docstring documents this contract; previously no test exercised it.
      """
      from spotify_project.analyzer import ArtistAnalyzer

      df = _frame(
          [
              {
                  "track_id": "t1",
                  "artist_ids": ["a1", "a2"],
                  "artist_names": ["Alice"],
                  "duration_min": 4.0,
              },
          ]
      )
      with pytest.raises(ValueError):
          ArtistAnalyzer().analyze(df)
  ```

- [ ] **Step 9.2: Run — expect pass**

  Run:
  ```
  .venv/Scripts/python.exe -m pytest tests/test_analyzer.py::test_artist_analyzer_raises_value_error_on_mismatched_list_lengths -v
  ```
  Expected: `1 passed`. The behavior already exists (Sprint B's `_zip_pairs(strict=True)`); this just locks it in.

- [ ] **Step 9.3: Run the full suite**

  Run:
  ```
  .venv/Scripts/python.exe -m pytest -q
  ```
  Expected: `41 passed`.

- [ ] **Step 9.4: Format, lint, type-check**

  Run:
  ```
  .venv/Scripts/python.exe -m ruff format tests
  .venv/Scripts/python.exe -m ruff check tests
  .venv/Scripts/python.exe -m pyright tests
  ```
  Expected: clean.

- [ ] **Step 9.5: Commit**

  ```
  git add tests/test_analyzer.py
  git commit -m "test(analyzer): pin ArtistAnalyzer ValueError on mismatched artist list lengths"
  ```

---

### Task 10: Notebook — narrative cells + Liked Songs toggle + execute end-to-end

**Files:**
- Modify: `notebooks/01_explore_playlist.ipynb`

**Tool note:** `NotebookEdit` is a deferred tool — load it via `ToolSearch(query="select:NotebookEdit", max_results=1)` before first use.

**Subprocess auth context:** The user's `.env` and `.cache/spotify_token` are populated. Running `.venv/Scripts/python.exe -m jupyter nbconvert --execute ...` authenticates headlessly via the cached token. The harness `deny`s your direct Read/Edit access to `.env` and `.cache`, but Python subprocesses access them in user space invisibly to your tool layer. **Do NOT try to Read those files yourself.**

- [ ] **Step 10.1: Inspect current notebook cell structure**

  Run:
  ```
  .venv/Scripts/python.exe -c "import nbformat; nb = nbformat.read('notebooks/01_explore_playlist.ipynb', as_version=4); [print(i, c.cell_type, repr(c.source.split(chr(10))[0][:80])) for i, c in enumerate(nb.cells)]"
  ```
  Expected: 14 cells (Sprint B end-state). Note the indices for §A–§G below.

- [ ] **Step 10.2: Update the title cell (cell 0) to mention coverage / colorblind palette**

  Replace cell 0's source:

  ```markdown
  # Spotify Playlist Explorer

  Phase 1 demo (Sprint C, final): authenticate, pick a playlist (or your
  Liked Songs), run six analyzers (genres, release year, top artists,
  popularity, duration, timeline) with coordinated colorblind palette and
  inline coverage annotations, render plots, and optionally export to parquet.
  ```

- [ ] **Step 10.3: Update the playlist-fetch cell to support Liked Songs toggle**

  Replace cell 7's source (currently `PLAYLIST_ID = '3v8PWRLiPHGPY0oHgkoZvV' ...`):

  ```python
  PLAYLIST_ID = "3v8PWRLiPHGPY0oHgkoZvV"  # or "__liked__" for your saved tracks
  playlist = (
      client.liked_songs() if PLAYLIST_ID == "__liked__" else client.playlist(PLAYLIST_ID)
  )
  print(f"{playlist.name}: {len(playlist.tracks)} tracks")
  ```

- [ ] **Step 10.4: Add narrative markdown cells**

  Insert short markdown cells (1–2 sentences each) at these positions, using NotebookEdit's `insert` mode:

  - **Before cell 1 (setup code)** — insert AFTER cell 0:
    ```markdown
    Setup: load credentials from `.env`, set the seaborn theme, and build a
    cached `SpotifyClient`. The cache lives at `.cache/api/` (7-day TTL) so
    repeated notebook runs don't re-hit the API.
    ```

  - **Before cell 9 (run_all)** — insert AFTER the `## 4.` markdown:
    ```markdown
    Each analyzer reports a small summary DataFrame. Numbers come from the
    flattened track DataFrame produced by `PlaylistAnalyzer.from_playlist`.
    Coverage attached to each summary surfaces in the chart titles below.
    ```

  - **Before cell 11 (plot_all)** — insert AFTER the `## 5.` markdown:
    ```markdown
    All six panels stack vertically, each in a distinct colorblind-safe color.
    `GenreAnalyzer` shows a small grey band at the bottom whenever some
    tracks have no genre data — a common case for editorial playlists.
    ```

  - **Before the parquet cell (cell 13)** — insert AFTER the `## 6.` markdown:
    ```markdown
    The exported parquet preserves the full flattened track DataFrame (track
    id/name, primary artist, all artists, album, release date, duration in
    minutes, popularity, added_at, genres). Useful for archiving the
    snapshot you analyzed today.
    ```

  After insertion the notebook should have 18 cells (14 original + 4 new markdown).

- [ ] **Step 10.5: Confirm structure**

  Run:
  ```
  .venv/Scripts/python.exe -c "import nbformat; nb = nbformat.read('notebooks/01_explore_playlist.ipynb', as_version=4); print(f'cells: {len(nb.cells)}'); [print(i, c.cell_type, repr(c.source.split(chr(10))[0][:80])) for i, c in enumerate(nb.cells)]"
  ```
  Expected: `cells: 18`, with markdown narrative cells correctly positioned.

- [ ] **Step 10.6: Synthetic-data execution check (no Spotify API)**

  Sanity-check every analyzer + plot_all against fabricated data — same harness as Sprint B's check, just verify Sprint C visual changes don't regress:

  ```
  .venv/Scripts/python.exe -c "
  from datetime import UTC, datetime
  import matplotlib
  matplotlib.use('Agg')
  import matplotlib.pyplot as plt
  from spotify_project.models import Artist, Playlist, Track
  from spotify_project.analyzer import (
      PlaylistAnalyzer, GenreAnalyzer, YearAnalyzer, ArtistAnalyzer,
      PopularityAnalyzer, DurationAnalyzer, TimelineAnalyzer,
  )
  a1 = Artist(id='a1', name='Alice', genres=('rock','indie'), popularity=70)
  a2 = Artist(id='a2', name='Bob', genres=(), popularity=55)
  tracks = tuple(
      Track(id=f't{i}', name=f'Song {i}', artists=(a1, a2) if i % 2 == 0 else (a1,),
            album_name='Album', release_date=f'{1980 + i}-01-01',
            duration_ms=180_000 + i * 5_000, popularity=10 + i * 3,
            explicit=False, added_at=datetime(2024, 1 + (i % 12), 1, tzinfo=UTC),
            is_local=False)
      for i in range(12)
  )
  playlist = Playlist(id='pl', name='Synthetic', owner_display_name='test',
                      public=True, collaborative=False, description='', tracks=tracks)
  pa = PlaylistAnalyzer.from_playlist(playlist)
  results = pa.run_all()
  for title, df in results.items():
      cov = df.attrs.get('coverage')
      print(f'{title}: {len(df)} rows, cov={cov}, cols={list(df.columns)}')
  fig = plt.figure(figsize=(12, 24))
  pa.plot_all(fig)
  print('plot_all OK')
  "
  ```

  Expected: 6 lines like `Top Genres: 2 rows, cov=(12, 12), cols=['genre', 'count']` plus `plot_all OK`. Each analyzer must report a sensible `cov` tuple (Genre coverage may be partial since `a2` has empty genres).

- [ ] **Step 10.7: Real-Spotify execution end-to-end**

  Run the notebook against the user's real Spotify account:

  ```
  .venv/Scripts/python.exe -m jupyter nbconvert --to notebook --execute --inplace notebooks/01_explore_playlist.ipynb --ExecutePreprocessor.timeout=300
  ```

  Expected: success, no traceback. If auth fails, escalate BLOCKED.

- [ ] **Step 10.8: Verify outputs programmatically**

  ```
  .venv/Scripts/python.exe -c "
  import nbformat
  nb = nbformat.read('notebooks/01_explore_playlist.ipynb', as_version=4)
  for i, c in enumerate(nb.cells):
      if c.cell_type != 'code':
          continue
      has_image = any('image/png' in (out.get('data') or {}) for out in c.get('outputs', []))
      text_outputs = []
      for out in c.get('outputs', []):
          text = out.get('text') or out.get('data', {}).get('text/plain', '')
          if isinstance(text, list):
              text = ''.join(text)
          if text:
              text_outputs.append(text[:400])
      print(f'--- cell {i} {\"(image)\" if has_image else \"\"} ---')
      for t in text_outputs:
          print(t)
  "
  ```

  Verify (every checkpoint must be true before claiming success):
  - Setup cell: no `RuntimeError`.
  - `current_user`: prints `Hello, <name>`.
  - `user_playlists`: non-zero rows.
  - Fetch playlist: `<name>: <N> tracks` with N > 0.
  - `run_all` print: six analyzer summaries with sensible row counts.
  - Plot cell: produces an `image/png` output.
  - Parquet cell: no traceback (silent with `EXPORT = False`).

  If any checkpoint fails, surface BLOCKED with cell index + traceback excerpt.

- [ ] **Step 10.9: Clear outputs**

  ```
  .venv/Scripts/python.exe -m jupyter nbconvert --clear-output --inplace notebooks/01_explore_playlist.ipynb
  ```

- [ ] **Step 10.10: Confirm working tree**

  ```
  git status
  git diff --stat notebooks/01_explore_playlist.ipynb
  ```
  Expected: only the notebook is modified; the diff stat shows reasonable cell-edit changes (no `outputs:` JSON additions).

- [ ] **Step 10.11: Commit**

  ```
  git add notebooks/01_explore_playlist.ipynb
  git commit -m "feat(notebook): Sprint C — narrative cells, Liked Songs toggle, polished palette"
  ```

> **CHECKPOINT 5 — STOP HERE.** Notebook ships and runs cleanly against real Spotify. Just README left.

---

### Task 11: Docs — README "How to run" section

**Files:**
- Modify: `README.md`

- [ ] **Step 11.1: Read current README**

  Run:
  ```
  .venv/Scripts/python.exe -c "print(open('README.md', encoding='utf-8').read())"
  ```
  Note the existing structure. The "How to run" section may be empty or a stub.

- [ ] **Step 11.2: Replace / add the "How to run" section**

  Use `Edit` to replace the existing placeholder (or append if there's no existing section) with:

  ```markdown
  ## How to run

  ### Prerequisites

  - Python 3.11 or later (3.14 tested)
  - A Spotify Developer App — register one at <https://developer.spotify.com/dashboard>

  ### Setup

  1. Clone the repo and enter the directory:
     ```
     git clone <repo-url> py_spotify_project
     cd py_spotify_project
     ```

  2. Create and activate a virtual environment:
     ```
     # Windows
     python -m venv .venv
     .venv\Scripts\activate

     # macOS / Linux
     python3 -m venv .venv
     source .venv/bin/activate
     ```

  3. Install dependencies:
     ```
     pip install -r requirements.txt
     ```

  4. Register a Spotify app (if you don't have one):
     - Go to <https://developer.spotify.com/dashboard> → "Create app"
     - Set the redirect URI to `http://127.0.0.1:8888/callback`
     - Copy your `client_id` and `client_secret`

  5. Configure credentials:
     ```
     cp .env.example .env
     ```
     Then edit `.env` and fill in:
     - `SPOTIPY_CLIENT_ID` — from the dashboard
     - `SPOTIPY_CLIENT_SECRET` — from the dashboard
     - `SPOTIPY_REDIRECT_URI` — e.g. `http://127.0.0.1:8888/callback`

  ### Run the notebook

  ```
  jupyter notebook notebooks/01_explore_playlist.ipynb
  ```

  - The first run opens a browser for OAuth; grant the scopes.
  - Subsequent runs use the cached token at `.cache/spotify_token` and don't prompt.
  - To analyze a different playlist, replace the `PLAYLIST_ID` in cell 7 with one of your own playlist IDs (visible in cell 5's output).
  - To analyze your "Liked Songs" instead, set `PLAYLIST_ID = "__liked__"`.

  ### Run the test suite

  ```
  .venv/Scripts/python.exe -m pytest -q          # Windows
  .venv/bin/python -m pytest -q                  # macOS / Linux
  ```

  Expected: ~41 tests pass.
  ```

- [ ] **Step 11.3: Verify the markdown renders sensibly**

  Run:
  ```
  .venv/Scripts/python.exe -c "
  text = open('README.md', encoding='utf-8').read()
  # Quick sanity: section header present, no broken backtick fences
  assert '## How to run' in text, 'Missing How to run section'
  assert text.count('```') % 2 == 0, 'Unbalanced code fences'
  print('README structure OK')
  "
  ```
  Expected: `README structure OK`.

- [ ] **Step 11.4: Format check (no .md formatter, but make sure no other files dirtied)**

  Run:
  ```
  git status
  ```
  Expected: only `README.md` modified.

- [ ] **Step 11.5: Commit**

  ```
  git add README.md
  git commit -m "docs(readme): How to run section — venv, .env, OAuth, jupyter, pytest"
  ```

> **🎉 SPRINT C COMPLETE — Phase 1 final.** All deliverables shipped. Run `pytest -q` for the final green check; expect ~41 passed.

---

## Self-review

**Spec coverage** — every section of the spec (`docs/superpowers/specs/2026-05-06-spotify-phase1-sprint-c.md`) → task that implements it:

- §1 Liked Songs feature → **Task 4** ✓
- §1.3 Notebook integration → **Task 10 Step 10.3** ✓
- §1.4 Liked Songs test → **Task 4 Step 4.1** ✓
- §2.1–§2.3 Palette + color wiring + style tweaks → **Task 1** ✓
- §2.4 Coverage method + per-class overrides → **Task 2** ✓
- §2.5 attrs flow → **Task 2 Step 2.5 / 2.9** ✓
- §2.6 GenreAnalyzer bottom band → **Task 3** ✓
- §3.1 TimelineAnalyzer source column → **Task 5** ✓
- §3.2 Title-instance-override → **Task 6** ✓
- §3.3 Drop `all_artists` → **Task 7** ✓
- §3.4 Default analyzer list bump → **Task 8** ✓
- §3.5 ArtistAnalyzer ValueError test → **Task 9** ✓
- §4.1 Notebook narrative → **Task 10 Step 10.4** ✓
- §4.2 README "How to run" → **Task 11** ✓
- §5 Test target ~40 → end of Task 9: 41 tests ✓

**Placeholder scan:** No `TBD`, `TODO`, "implement later", "fill in details". Every code step contains the actual code. Test bodies and commit messages are explicit. The Step 10.4 markdown narrative blocks are short on purpose (oral-exam tight).

The forward reference in Tasks 1–3 to `self.effective_title` is documented (those tasks use `self.title` temporarily; Task 6 swaps them). This is acknowledged in Task 1 Step 1.4's parenthetical note.

**Type / signature consistency:**
- `Analyzer.plot(self, ax, summary, *, color: str | None = None) -> None` — used identically by all six subclasses and called by `PlaylistAnalyzer.plot_all` with the same kwarg name.
- `Analyzer.coverage(self, df) -> tuple[int, int]` — same signature on every override.
- `Analyzer._attach_coverage(self, summary, df) -> pd.DataFrame` — called by every concrete `analyze()` consistently.
- `Analyzer.effective_title -> str` — read from the same property name in `PlaylistAnalyzer.__init__`, `run_all`, `plot_all`, and every analyzer's `plot`.
- `SpotifyClient.liked_songs(self, *, force_refresh: bool = False) -> Playlist` — matches the spec exactly.
- All numeric types in tests use the same primitives (`int` for counts, `float` for `pytest.approx`, etc.).
- Pseudo-playlist id `"__liked__"` is consistent between `client.py`, the test, and the notebook toggle.

**File structure consistency:** No new files. Eleven files modified across the sprint (`analyzer.py`, `client.py`, `test_analyzer.py`, `test_client.py`, `test_playlist_analyzer.py`, `01_explore_playlist.ipynb`, `README.md`).

---

## Execution handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-06-spotify-phase1-sprint-c.md`.

**Two execution options:**

1. **Subagent-Driven (recommended)** — fresh subagent per task, two-stage review between tasks, fast iteration.
2. **Inline Execution** — execute tasks in this session with checkpoints batched for review.

Which approach?
