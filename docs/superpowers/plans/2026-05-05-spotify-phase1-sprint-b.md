# Phase 1 Sprint B Implementation Plan — py_spotify_project

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the Phase 1 library with four new `Analyzer` subclasses (Artist, Popularity, Duration, Timeline), parameterize the existing `YearAnalyzer` with a `bucket_size` knob, ship a parquet round-trip test, and rebuild the demo notebook to surface all six analyzers plus an opt-in parquet export.

**Architecture:** Strict Strategy-pattern extension. Each new analyzer is a standalone subclass of the existing `Analyzer` ABC — `analyze(df) -> pd.DataFrame` and `plot(ax, summary) -> None`, no figure-level mutation. The `PlaylistAnalyzer.from_playlist` schema gains two new columns (`artist_ids`, `artist_names`) so artist-level explosion stays in pandas-land instead of reaching back into the Track object graph. No changes to `client.py`, `cache.py`, or `models.py`.

**Tech Stack:** Same as Sprint A — Python 3.14, spotipy 2.26, pandas 2.3, matplotlib 3.10 + seaborn 0.13, pytest 8.4, **ruff** (format + lint, replaced black), **pyright** strict (replaced mypy). All installed in `.venv`.

---

## Sprint A retrospective — assumptions feeding this plan

These are baked into task ordering and design choices below; if any of them is wrong, flag it before execution starts.

- The `Analyzer` ABC's strict `__init_subclass__` `title` check is settled — Sprint B keeps `title` as a class-level constant per subclass. A real future need for "two YearAnalyzer instances with different `bucket_size` in one PlaylistAnalyzer" would require an instance-level title override; that is **NOT** in scope for Sprint B (would collide on `run_all()`'s `{title: df}` dict key). **Documented constraint, not a bug.**
- The `from_playlist` flattening currently joins all artist names into a single pipe-delimited string (`all_artists`). That string is fine for display but useless for grouping. Sprint B adds parallel `artist_ids: list[str]` and `artist_names: list[str]` columns so the new `ArtistAnalyzer` can `.explode("artist_ids")` cleanly.
- pyright is run via `.venv/Scripts/python.exe -m pyright` (or the bundled `pyright` CLI) — confirm during pre-flight.
- ~~The notebook generator (`scripts/create_notebook.py`) is the single source of truth for `notebooks/01_explore_playlist.ipynb`. We regenerate, never hand-edit.~~ **REVERSED for Sprint B per user direction**: the `.ipynb` is the source of truth; we hand-edit it directly via `NotebookEdit`. The generator script is **deleted** in Task 7.
- The user has populated `.env` and authenticated at least once (`.cache/spotify_token` is on disk). My subprocess workflow (`.venv/Scripts/python.exe -c "..."` or `jupyter nbconvert --execute`) authenticates headlessly via the cached token; if auth fails (e.g. expired refresh token), I escalate to the user for a one-time browser-flow re-auth, then resume.

---

## Pre-flight

Five seconds of check, lots of mistakes prevented.

- [ ] **Step 0.1: Confirm working tree is clean enough**

  Run:
  ```
  git status
  ```
  Expected: only the kernel-metadata diff on `notebooks/01_explore_playlist.ipynb` (or fully clean). If anything else is modified, surface it before continuing — Sprint B will regenerate the notebook anyway, so the kernel-metadata change is fine to leave or reset.

- [ ] **Step 0.2: Confirm baseline tests pass**

  Run:
  ```
  .venv/Scripts/python.exe -m pytest -q
  ```
  Expected: `8 passed` (matches the suite at end of Sprint A — 2 cache + 1 model + 1 client + 4 analyzer). If anything fails, stop — Sprint A regression must be fixed first.

- [ ] **Step 0.3: Confirm pyright is wired up**

  Run:
  ```
  .venv/Scripts/python.exe -m pyright src
  ```
  Expected: 0 errors. (Warnings about `reportMissingTypeStubs` are silenced via pyproject.toml; anything else means tooling drifted since last commit.)

- [ ] **Step 0.4: Confirm ruff format + lint are clean**

  Run:
  ```
  .venv/Scripts/python.exe -m ruff format --check src tests
  .venv/Scripts/python.exe -m ruff check src tests
  ```
  Expected: both clean. If format reports differences, run without `--check` and investigate before continuing.

---

## File structure (locked)

| File | Created/Modified in | Responsibility |
|---|---|---|
| `src/spotify_project/analyzer.py` | T1, T2, T3, T4, T5 | Adds `bucket_size` to YearAnalyzer (T1); adds `ArtistAnalyzer` (T2), `PopularityAnalyzer` (T3), `DurationAnalyzer` (T4), `TimelineAnalyzer` (T5); extends `from_playlist` schema (T2). |
| `tests/test_analyzer.py` | T1, T2, T3, T4, T5 | New tests per analyzer. |
| `tests/test_playlist_analyzer.py` | T6 | Parquet round-trip test (split out — keeps `test_analyzer.py` focused on per-analyzer behavior). |
| `scripts/create_notebook.py` | T7 | **DELETED** in T7 — user prefers the `.ipynb` to be the source of truth, not a generator script. |
| `notebooks/01_explore_playlist.ipynb` | T7 | Hand-edited via `NotebookEdit` (deferred tool — load via ToolSearch). |

Nothing else in `src/` changes — no client, cache, or models edits.

---

## Sprint B — tasks

### Task 1: `YearAnalyzer.bucket_size` parameter

**Why first:** Smallest, most contained change. Demonstrates the parameterization pattern other tasks reuse. No new schema, no new file.

**Files:**
- Modify: `src/spotify_project/analyzer.py` (`YearAnalyzer` class only)
- Modify: `tests/test_analyzer.py` (existing test stays; one new test)

- [ ] **Step 1.1: Add the failing test for bucketed years**

  Append to `tests/test_analyzer.py`:

  ```python
  def test_year_analyzer_groups_into_decade_buckets() -> None:
      """YearAnalyzer with bucket_size=10 groups years into decade ranges.

      The ``year`` column reports the bucket's lower bound (e.g. 1970 means
      1970-1979 inclusive); the ``count`` column sums tracks across the bucket.
      """
      df = _frame(
          [
              {"track_id": "1", "release_date": "1972-05-01"},
              {"track_id": "2", "release_date": "1979-12-31"},
              {"track_id": "3", "release_date": "1980-01-01"},
              {"track_id": "4", "release_date": "2021-06-01"},
              {"track_id": "5", "release_date": "2024-03-15"},
          ]
      )
      summary = YearAnalyzer(bucket_size=10).analyze(df)
      counts = dict(zip(summary["year"], summary["count"], strict=True))
      assert counts[1970] == 2
      assert counts[1980] == 1
      assert counts[2020] == 2
  ```

- [ ] **Step 1.2: Run the new test — expect failure**

  Run:
  ```
  .venv/Scripts/python.exe -m pytest tests/test_analyzer.py::test_year_analyzer_groups_into_decade_buckets -v
  ```
  Expected: `TypeError: YearAnalyzer.__init__() got an unexpected keyword argument 'bucket_size'`. Confirms the test runs and fails for the expected reason.

- [ ] **Step 1.3: Update `YearAnalyzer` to accept `bucket_size`**

  Replace the existing `YearAnalyzer` class in `src/spotify_project/analyzer.py` with:

  ```python
  class YearAnalyzer(Analyzer):
      """Release-year distribution, robust to year-only release_date strings.

      Args:
          bucket_size: Year-bucket width. ``1`` (default) yields per-year bars.
              ``5`` groups into 5-year buckets (1970, 1975, 1980, ...); ``10``
              into decades (1970, 1980, ...). The reported ``year`` value is
              always the bucket's lower bound. Must be a positive integer.

      Raises:
          ValueError: If ``bucket_size`` is not a positive integer.
      """

      title = "Release Year Distribution"

      def __init__(self, bucket_size: int = 1) -> None:
          if bucket_size < 1:
              raise ValueError(
                  f"bucket_size must be a positive integer, got {bucket_size}"
              )
          self.bucket_size = bucket_size

      def analyze(self, df: pd.DataFrame) -> pd.DataFrame:
          """Count tracks per release year (or per year-bucket).

          Handles both full ISO dates (``2020-01-01``) and year-only strings
          (``1979``). Rows with ``None`` or unparseable release_date are dropped.
          When ``bucket_size > 1``, years are floor-divided onto bucket
          boundaries before counting.

          Args:
              df: Track-level DataFrame with a ``release_date`` column.

          Returns:
              DataFrame with columns ``year`` (int — bucket lower bound) and
              ``count``, sorted ascending by year.
          """
          if df.empty or "release_date" not in df.columns:
              return pd.DataFrame({"year": [], "count": []})
          years = (
              pd.to_numeric(df["release_date"].str.slice(0, 4), errors="coerce")
              .dropna()
              .astype(int)
          )
          if years.empty:
              return pd.DataFrame({"year": [], "count": []})
          if self.bucket_size > 1:
              years = (years // self.bucket_size) * self.bucket_size
          return (
              years.value_counts()
              .sort_index()
              .rename_axis("year")
              .reset_index(name="count")
          )

      def plot(self, ax: Axes, summary: pd.DataFrame) -> None:
          """Render a vertical bar chart of track counts per year-bucket.

          Bar width is proportional to ``bucket_size`` so adjacent buckets
          touch (decade plot looks like a histogram, not isolated columns).

          Args:
              ax: Matplotlib Axes to draw on.
              summary: Output of ``analyze``; columns ``year`` and ``count``.
          """
          if summary.empty:
              ax.text(0.5, 0.5, "No year data", ha="center", va="center")
              ax.set_title(self.title)
              return
          ax.bar(
              summary["year"],
              summary["count"],
              width=self.bucket_size * 0.9,
              align="edge",
          )
          xlabel = "Year" if self.bucket_size == 1 else f"Year ({self.bucket_size}-year buckets)"
          ax.set_xlabel(xlabel)
          ax.set_ylabel("Track count")
          ax.set_title(self.title)
  ```

- [ ] **Step 1.4: Run the new test — expect pass**

  Run:
  ```
  .venv/Scripts/python.exe -m pytest tests/test_analyzer.py::test_year_analyzer_groups_into_decade_buckets -v
  ```
  Expected: `1 passed`.

- [ ] **Step 1.5: Run the full analyzer suite — confirm no regression**

  Run:
  ```
  .venv/Scripts/python.exe -m pytest tests/test_analyzer.py -v
  ```
  Expected: `5 passed` (4 existing + 1 new).

- [ ] **Step 1.6: Add a defensive-input test**

  Append to `tests/test_analyzer.py`:

  ```python
  def test_year_analyzer_rejects_non_positive_bucket_size() -> None:
      """YearAnalyzer's __init__ rejects bucket_size < 1."""
      with pytest.raises(ValueError, match="bucket_size"):
          YearAnalyzer(bucket_size=0)
  ```

- [ ] **Step 1.7: Run the new defensive test — expect pass**

  Run:
  ```
  .venv/Scripts/python.exe -m pytest tests/test_analyzer.py::test_year_analyzer_rejects_non_positive_bucket_size -v
  ```
  Expected: `1 passed`.

- [ ] **Step 1.8: Format, lint, type-check**

  Run:
  ```
  .venv/Scripts/python.exe -m ruff format src/spotify_project/analyzer.py tests/test_analyzer.py
  .venv/Scripts/python.exe -m ruff check src/spotify_project/analyzer.py tests/test_analyzer.py
  .venv/Scripts/python.exe -m pyright src/spotify_project/analyzer.py
  ```
  Expected: clean.

- [ ] **Step 1.9: Commit**

  ```
  git add src/spotify_project/analyzer.py tests/test_analyzer.py
  git commit -m "feat(analyzer): YearAnalyzer.bucket_size for decade/multi-year grouping"
  ```

> **CHECKPOINT 1 — STOP HERE.** Confirm with the user that the bucket-size semantics (lower-bound label, floor-division grouping, bar-width scaling) match their mental model before moving on. Show: `pytest tests/test_analyzer.py -v` output and the `analyzer.py` diff.

---

### Task 2: Schema extension + `ArtistAnalyzer`

**Why second:** `ArtistAnalyzer` needs per-track artist lists, which the current `from_playlist` schema doesn't expose. We extend the schema and ship the analyzer that consumes it in one task — they're inseparable.

**Files:**
- Modify: `src/spotify_project/analyzer.py` (`PlaylistAnalyzer.from_playlist` adds two columns; new `ArtistAnalyzer` class added before `PlaylistAnalyzer`)
- Modify: `tests/test_analyzer.py` (new tests)

- [ ] **Step 2.1: Write the failing schema-extension test**

  Append to `tests/test_analyzer.py`:

  ```python
  def test_from_playlist_exposes_artist_id_and_name_lists() -> None:
      """PlaylistAnalyzer.from_playlist surfaces parallel artist_ids/names lists.

      ArtistAnalyzer needs grouping-friendly columns (lists, not pipe-joined
      strings). This test pins the schema additions; if they regress, the
      analyzer breaks.
      """
      from datetime import datetime, timezone

      from spotify_project.models import Artist, Playlist, Track

      a1 = Artist(id="a1", name="Alice", genres=("rock",), popularity=50)
      a2 = Artist(id="a2", name="Bob", genres=("indie",), popularity=40)
      track = Track(
          id="t1",
          name="Song",
          artists=(a1, a2),
          album_name="Album",
          release_date="2020-01-01",
          duration_ms=200_000,
          popularity=60,
          explicit=False,
          added_at=datetime(2024, 6, 1, tzinfo=timezone.utc),
          is_local=False,
      )
      playlist = Playlist(
          id="pl1",
          name="Test",
          owner_display_name="Bennet",
          public=True,
          collaborative=False,
          description="",
          tracks=(track,),
      )
      pa = PlaylistAnalyzer.from_playlist(playlist)
      row = pa.df.iloc[0]
      assert row["artist_ids"] == ["a1", "a2"]
      assert row["artist_names"] == ["Alice", "Bob"]
  ```

- [ ] **Step 2.2: Run the test — expect failure**

  Run:
  ```
  .venv/Scripts/python.exe -m pytest tests/test_analyzer.py::test_from_playlist_exposes_artist_id_and_name_lists -v
  ```
  Expected: `KeyError: 'artist_ids'` or similar — confirms the schema needs extending.

- [ ] **Step 2.3: Extend `from_playlist` schema**

  In `src/spotify_project/analyzer.py`, locate the `rows.append(...)` call inside `PlaylistAnalyzer.from_playlist` and add two keys to the row dict — between `"all_artists": ...` and `"album_name": ...`:

  ```python
              "all_artists": " | ".join(a.name for a in t.artists),
              "artist_ids": [a.id for a in t.artists],
              "artist_names": [a.name for a in t.artists],
              "album_name": t.album_name,
  ```

  Both lists are empty for local files (matches `t.artists == ()`).

- [ ] **Step 2.4: Run the schema test — expect pass**

  Run:
  ```
  .venv/Scripts/python.exe -m pytest tests/test_analyzer.py::test_from_playlist_exposes_artist_id_and_name_lists -v
  ```
  Expected: `1 passed`.

- [ ] **Step 2.5: Add the ArtistAnalyzer test (all-artists default)**

  Append to `tests/test_analyzer.py`:

  ```python
  def test_artist_analyzer_counts_all_artists_by_default() -> None:
      """ArtistAnalyzer with default primary_only=False counts every artist on every track.

      A track with two artists contributes 1 to each artist's track_count and
      its full duration to each artist's total_minutes (naive credit).
      """
      from spotify_project.analyzer import ArtistAnalyzer

      df = _frame(
          [
              {
                  "track_id": "t1",
                  "artist_ids": ["a1", "a2"],
                  "artist_names": ["Alice", "Bob"],
                  "primary_artist_id": "a1",
                  "primary_artist_name": "Alice",
                  "duration_min": 4.0,
              },
              {
                  "track_id": "t2",
                  "artist_ids": ["a1"],
                  "artist_names": ["Alice"],
                  "primary_artist_id": "a1",
                  "primary_artist_name": "Alice",
                  "duration_min": 3.0,
              },
              {
                  "track_id": "t3",
                  "artist_ids": ["a2"],
                  "artist_names": ["Bob"],
                  "primary_artist_id": "a2",
                  "primary_artist_name": "Bob",
                  "duration_min": 5.0,
              },
          ]
      )
      summary = ArtistAnalyzer(top_n=10).analyze(df)
      by_id = {row["artist_id"]: row for _, row in summary.iterrows()}
      assert by_id["a1"]["track_count"] == 2
      assert by_id["a1"]["total_minutes"] == 7.0
      assert by_id["a1"]["artist_name"] == "Alice"
      assert by_id["a2"]["track_count"] == 2
      assert by_id["a2"]["total_minutes"] == 9.0
  ```

- [ ] **Step 2.6: Add the primary-only mode test**

  Append to `tests/test_analyzer.py`:

  ```python
  def test_artist_analyzer_primary_only_mode_ignores_collaborators() -> None:
      """ArtistAnalyzer(primary_only=True) only counts the lead artist per track."""
      from spotify_project.analyzer import ArtistAnalyzer

      df = _frame(
          [
              {
                  "track_id": "t1",
                  "artist_ids": ["a1", "a2"],
                  "artist_names": ["Alice", "Bob"],
                  "primary_artist_id": "a1",
                  "primary_artist_name": "Alice",
                  "duration_min": 4.0,
              },
              {
                  "track_id": "t2",
                  "artist_ids": ["a2"],
                  "artist_names": ["Bob"],
                  "primary_artist_id": "a2",
                  "primary_artist_name": "Bob",
                  "duration_min": 5.0,
              },
          ]
      )
      summary = ArtistAnalyzer(primary_only=True).analyze(df)
      by_id = {row["artist_id"]: row for _, row in summary.iterrows()}
      # Bob is a collaborator on t1, so primary-only does NOT credit him for that track.
      assert by_id["a1"]["track_count"] == 1
      assert by_id["a2"]["track_count"] == 1
      assert by_id["a2"]["total_minutes"] == 5.0
  ```

- [ ] **Step 2.7: Add the empty-input test**

  Append to `tests/test_analyzer.py`:

  ```python
  def test_artist_analyzer_returns_empty_summary_for_empty_df() -> None:
      """ArtistAnalyzer.analyze returns an empty summary for an empty df."""
      from spotify_project.analyzer import ArtistAnalyzer

      summary = ArtistAnalyzer().analyze(_frame([]))
      assert summary.empty
      assert list(summary.columns) == [
          "artist_id",
          "artist_name",
          "track_count",
          "total_minutes",
      ]
  ```

- [ ] **Step 2.8: Run the new tests — expect import failure**

  Run:
  ```
  .venv/Scripts/python.exe -m pytest tests/test_analyzer.py -k artist -v
  ```
  Expected: `ImportError: cannot import name 'ArtistAnalyzer'`.

- [ ] **Step 2.9: Implement `ArtistAnalyzer`**

  In `src/spotify_project/analyzer.py`, insert this class **between `YearAnalyzer` and `PlaylistAnalyzer`** (so the order goes Genre → Year → Artist → … → PlaylistAnalyzer at the bottom):

  ```python
  class ArtistAnalyzer(Analyzer):
      """Top artists by track count and total minutes.

      With ``primary_only=False`` (default), every artist on every track gets
      naive credit — a 4-minute track with two artists adds 4 minutes to each.
      With ``primary_only=True``, only the first-listed (lead) artist on each
      track is counted.

      Args:
          top_n: How many artists to return; default 15.
          primary_only: If True, count only each track's primary artist;
              default False (count all listed artists).
      """

      title = "Top Artists"

      def __init__(self, top_n: int = 15, primary_only: bool = False) -> None:
          self.top_n = top_n
          self.primary_only = primary_only

      def analyze(self, df: pd.DataFrame) -> pd.DataFrame:
          """Aggregate track count and total minutes per artist.

          Args:
              df: Track-level DataFrame with either ``artist_ids`` /
                  ``artist_names`` (list columns; used when
                  ``primary_only=False``) or ``primary_artist_id`` /
                  ``primary_artist_name`` (used when ``primary_only=True``).

          Returns:
              DataFrame with columns ``artist_id``, ``artist_name``,
              ``track_count``, ``total_minutes``, sorted descending by
              ``track_count``, limited to ``top_n`` rows.
          """
          empty = pd.DataFrame(
              {"artist_id": [], "artist_name": [], "track_count": [], "total_minutes": []}
          )
          if df.empty:
              return empty

          if self.primary_only:
              required = {"primary_artist_id", "primary_artist_name", "duration_min"}
              if not required.issubset(df.columns):
                  return empty
              source = df[["primary_artist_id", "primary_artist_name", "duration_min"]].rename(
                  columns={
                      "primary_artist_id": "artist_id",
                      "primary_artist_name": "artist_name",
                  }
              )
          else:
              required = {"artist_ids", "artist_names", "duration_min"}
              if not required.issubset(df.columns):
                  return empty
              # Explode artist_ids and artist_names in lock-step so each
              # exploded row holds the matching name. Pandas explode preserves
              # ordering within the row, so the parallelism is preserved.
              exploded = df[["artist_ids", "artist_names", "duration_min"]].copy()
              exploded["pair"] = exploded.apply(
                  lambda r: list(zip(r["artist_ids"], r["artist_names"], strict=True)),
                  axis=1,
              )
              exploded = exploded.explode("pair").dropna(subset=["pair"])
              if exploded.empty:
                  return empty
              source = pd.DataFrame(
                  {
                      "artist_id": exploded["pair"].map(lambda p: p[0]),
                      "artist_name": exploded["pair"].map(lambda p: p[1]),
                      "duration_min": exploded["duration_min"],
                  }
              )

          source = source.dropna(subset=["artist_id"])
          if source.empty:
              return empty
          grouped = (
              source.groupby(["artist_id", "artist_name"], as_index=False)
              .agg(track_count=("duration_min", "size"), total_minutes=("duration_min", "sum"))
              .sort_values("track_count", ascending=False)
              .head(self.top_n)
              .reset_index(drop=True)
          )
          return grouped

      def plot(self, ax: Axes, summary: pd.DataFrame) -> None:
          """Render a horizontal bar chart of artists by track count.

          Args:
              ax: Matplotlib Axes to draw on.
              summary: Output of ``analyze``; must include ``artist_name``
                  and ``track_count`` columns.
          """
          if summary.empty:
              ax.text(0.5, 0.5, "No artist data", ha="center", va="center")
              ax.set_title(self.title)
              return
          ax.barh(summary["artist_name"], summary["track_count"])
          ax.invert_yaxis()
          ax.set_xlabel("Track count")
          ax.set_title(self.title)
  ```

- [ ] **Step 2.10: Run all artist tests — expect pass**

  Run:
  ```
  .venv/Scripts/python.exe -m pytest tests/test_analyzer.py -k artist -v
  ```
  Expected: `4 passed` (1 schema + 3 analyzer).

- [ ] **Step 2.11: Run the full suite — confirm no regression**

  Run:
  ```
  .venv/Scripts/python.exe -m pytest -q
  ```
  Expected: all green; count is now `8 (Sprint A) + 2 (Task 1) + 4 (Task 2) = 14 passed`.

- [ ] **Step 2.12: Format, lint, type-check**

  Run:
  ```
  .venv/Scripts/python.exe -m ruff format src tests
  .venv/Scripts/python.exe -m ruff check src tests
  .venv/Scripts/python.exe -m pyright src
  ```
  Expected: clean. (If pyright complains about the lambda's untyped row argument, type-narrow with `cast` or pull the lambda out into a typed helper — see "If pyright complains" sidebar below.)

  > **If pyright complains** about `lambda r: list(zip(r["artist_ids"], r["artist_names"], strict=True))`: replace it with a typed helper above the class:
  > ```python
  > def _zip_pairs(row: pd.Series[Any]) -> list[tuple[str, str]]:
  >     return list(zip(row["artist_ids"], row["artist_names"], strict=True))
  > ```
  > then `exploded["pair"] = exploded.apply(_zip_pairs, axis=1)`.

- [ ] **Step 2.13: Commit**

  ```
  git add src/spotify_project/analyzer.py tests/test_analyzer.py
  git commit -m "feat(analyzer): ArtistAnalyzer (all-artists default, primary_only flag) + schema columns"
  ```

> **CHECKPOINT 2 — STOP HERE.** Confirm with the user that the all-artists naive-credit semantic and the schema extension look right. The schema change is observable from the notebook side, so it's worth a quick sanity check before adding three more analyzers on top.

---

### Task 3: `PopularityAnalyzer`

**Files:**
- Modify: `src/spotify_project/analyzer.py`
- Modify: `tests/test_analyzer.py`

- [ ] **Step 3.1: Write the failing histogram test**

  Append to `tests/test_analyzer.py`:

  ```python
  def test_popularity_analyzer_returns_bin_counts() -> None:
      """PopularityAnalyzer bins track popularity 0-100 and reports counts per bin.

      Default 10 bins → bins of width 10. The summary has columns
      ``bin_low``, ``bin_high``, ``count``; bins are contiguous and cover [0, 100].
      """
      from spotify_project.analyzer import PopularityAnalyzer

      df = _frame(
          [
              {"track_id": "1", "popularity": 5},
              {"track_id": "2", "popularity": 12},
              {"track_id": "3", "popularity": 18},
              {"track_id": "4", "popularity": 95},
          ]
      )
      summary = PopularityAnalyzer(bins=10).analyze(df)
      assert list(summary.columns) == ["bin_low", "bin_high", "count"]
      assert len(summary) == 10
      first = summary.iloc[0]
      assert first["bin_low"] == 0
      assert first["bin_high"] == 10
      assert first["count"] == 1  # popularity=5 lives in [0, 10)
      second = summary.iloc[1]
      assert second["count"] == 2  # popularity=12 and 18 in [10, 20)
      assert summary.iloc[-1]["count"] == 1  # popularity=95 in [90, 100]
  ```

- [ ] **Step 3.2: Add the empty-input test**

  Append:

  ```python
  def test_popularity_analyzer_handles_empty_df() -> None:
      """PopularityAnalyzer returns an empty summary for an empty df."""
      from spotify_project.analyzer import PopularityAnalyzer

      summary = PopularityAnalyzer().analyze(_frame([]))
      assert summary.empty
      assert list(summary.columns) == ["bin_low", "bin_high", "count"]
  ```

- [ ] **Step 3.3: Add the all-zero-popularity test**

  Append:

  ```python
  def test_popularity_analyzer_all_zero_popularity_collapses_into_first_bin() -> None:
      """Tracks with popularity=0 (e.g. unreleased / unrated) all land in [0, 10)."""
      from spotify_project.analyzer import PopularityAnalyzer

      df = _frame(
          [{"track_id": str(i), "popularity": 0} for i in range(5)]
      )
      summary = PopularityAnalyzer(bins=10).analyze(df)
      assert summary.iloc[0]["count"] == 5
      assert summary["count"].sum() == 5
  ```

- [ ] **Step 3.4: Run the failing tests — expect import error**

  Run:
  ```
  .venv/Scripts/python.exe -m pytest tests/test_analyzer.py -k popularity -v
  ```
  Expected: `ImportError: cannot import name 'PopularityAnalyzer'`.

- [ ] **Step 3.5: Implement `PopularityAnalyzer`**

  Add this class to `src/spotify_project/analyzer.py` after `ArtistAnalyzer`. Add `import numpy as np` near the other imports if it's not already imported (matplotlib pulls numpy transitively, but explicit is better than implicit):

  ```python
  class PopularityAnalyzer(Analyzer):
      """Distribution of Spotify popularity scores (0-100) across the playlist.

      Args:
          bins: Number of equal-width bins covering [0, 100]; default 10.
              Must be a positive integer.

      Raises:
          ValueError: If ``bins`` is not a positive integer.
      """

      title = "Popularity Distribution"

      def __init__(self, bins: int = 10) -> None:
          if bins < 1:
              raise ValueError(f"bins must be a positive integer, got {bins}")
          self.bins = bins

      def analyze(self, df: pd.DataFrame) -> pd.DataFrame:
          """Bin track popularity into equal-width buckets across [0, 100].

          Args:
              df: Track-level DataFrame with a ``popularity`` column (0-100).

          Returns:
              DataFrame with columns ``bin_low``, ``bin_high``, ``count``.
              The right edge of the last bin is inclusive (np.histogram
              behavior); all other bins are right-open.
          """
          empty = pd.DataFrame({"bin_low": [], "bin_high": [], "count": []})
          if df.empty or "popularity" not in df.columns:
              return empty
          values = pd.to_numeric(df["popularity"], errors="coerce").dropna()
          if values.empty:
              return empty
          counts, edges = np.histogram(values, bins=self.bins, range=(0, 100))
          return pd.DataFrame(
              {
                  "bin_low": edges[:-1],
                  "bin_high": edges[1:],
                  "count": counts.astype(int),
              }
          )

      def plot(self, ax: Axes, summary: pd.DataFrame) -> None:
          """Render a histogram of popularity counts plus a vertical mean line.

          The mean is computed from the bin midpoints weighted by counts —
          accurate enough for visual annotation, even if the underlying data
          spread within bins is lost.

          Args:
              ax: Matplotlib Axes to draw on.
              summary: Output of ``analyze``.
          """
          if summary.empty or summary["count"].sum() == 0:
              ax.text(0.5, 0.5, "No popularity data", ha="center", va="center")
              ax.set_title(self.title)
              return
          widths = summary["bin_high"] - summary["bin_low"]
          ax.bar(summary["bin_low"], summary["count"], width=widths, align="edge")
          midpoints = (summary["bin_low"] + summary["bin_high"]) / 2
          weighted_mean = (midpoints * summary["count"]).sum() / summary["count"].sum()
          ax.axvline(weighted_mean, linestyle="--", linewidth=1)
          ax.set_xlabel("Popularity (0-100)")
          ax.set_ylabel("Track count")
          ax.set_xlim(0, 100)
          ax.set_title(f"{self.title} (mean ≈ {weighted_mean:.1f})")
  ```

  Add import at the top of the file (near `import pandas as pd`):

  ```python
  import numpy as np
  ```

- [ ] **Step 3.6: Run popularity tests — expect pass**

  Run:
  ```
  .venv/Scripts/python.exe -m pytest tests/test_analyzer.py -k popularity -v
  ```
  Expected: `3 passed`.

- [ ] **Step 3.7: Format, lint, type-check**

  Run:
  ```
  .venv/Scripts/python.exe -m ruff format src/spotify_project/analyzer.py tests/test_analyzer.py
  .venv/Scripts/python.exe -m ruff check src/spotify_project/analyzer.py tests/test_analyzer.py
  .venv/Scripts/python.exe -m pyright src/spotify_project/analyzer.py
  ```
  Expected: clean.

- [ ] **Step 3.8: Commit**

  ```
  git add src/spotify_project/analyzer.py tests/test_analyzer.py
  git commit -m "feat(analyzer): PopularityAnalyzer with binned histogram and weighted mean"
  ```

---

### Task 4: `DurationAnalyzer`

**Files:**
- Modify: `src/spotify_project/analyzer.py`
- Modify: `tests/test_analyzer.py`

**Design note:** Unlike `PopularityAnalyzer` (where the range is fixed at [0, 100]), durations are open-ended — songs can be 30 seconds or 30 minutes. We let `np.histogram` pick the range from the data. The `analyze` output adds a `minutes_in_bin` column (exact sum of durations in each bin) so `plot` can compute total runtime without re-touching the source df.

- [ ] **Step 4.1: Write the failing test**

  Append to `tests/test_analyzer.py`:

  ```python
  def test_duration_analyzer_returns_bins_with_exact_minutes_per_bin() -> None:
      """DurationAnalyzer reports both track count and exact total minutes per bin.

      The ``minutes_in_bin`` column is the exact sum of durations falling in
      that bin (not a midpoint approximation), so plot() can annotate total
      runtime accurately.
      """
      from spotify_project.analyzer import DurationAnalyzer

      df = _frame(
          [
              {"track_id": "1", "duration_min": 2.0},
              {"track_id": "2", "duration_min": 2.5},
              {"track_id": "3", "duration_min": 4.0},
              {"track_id": "4", "duration_min": 5.5},
          ]
      )
      summary = DurationAnalyzer(bins=4).analyze(df)
      assert list(summary.columns) == ["bin_low", "bin_high", "count", "minutes_in_bin"]
      assert summary["count"].sum() == 4
      assert summary["minutes_in_bin"].sum() == pytest.approx(14.0)
  ```

- [ ] **Step 4.2: Add the single-track edge case**

  Append:

  ```python
  def test_duration_analyzer_handles_single_track() -> None:
      """DurationAnalyzer returns a single-row summary for a single-track df."""
      from spotify_project.analyzer import DurationAnalyzer

      df = _frame([{"track_id": "1", "duration_min": 3.5}])
      summary = DurationAnalyzer(bins=10).analyze(df)
      assert summary["count"].sum() == 1
      assert summary["minutes_in_bin"].sum() == pytest.approx(3.5)
  ```

- [ ] **Step 4.3: Add the empty-input test**

  Append:

  ```python
  def test_duration_analyzer_handles_empty_df() -> None:
      """DurationAnalyzer returns an empty summary for an empty df."""
      from spotify_project.analyzer import DurationAnalyzer

      summary = DurationAnalyzer().analyze(_frame([]))
      assert summary.empty
      assert list(summary.columns) == ["bin_low", "bin_high", "count", "minutes_in_bin"]
  ```

- [ ] **Step 4.4: Run the failing tests**

  Run:
  ```
  .venv/Scripts/python.exe -m pytest tests/test_analyzer.py -k duration -v
  ```
  Expected: `ImportError: cannot import name 'DurationAnalyzer'`.

- [ ] **Step 4.5: Implement `DurationAnalyzer`**

  Add to `src/spotify_project/analyzer.py` after `PopularityAnalyzer`:

  ```python
  class DurationAnalyzer(Analyzer):
      """Track-duration distribution (in minutes) plus playlist total runtime.

      Args:
          bins: Number of equal-width bins; default 20. Range is inferred from
              the data (no fixed [0, 100] like popularity). Must be positive.

      Raises:
          ValueError: If ``bins`` is not a positive integer.
      """

      title = "Track Duration Distribution"

      def __init__(self, bins: int = 20) -> None:
          if bins < 1:
              raise ValueError(f"bins must be a positive integer, got {bins}")
          self.bins = bins

      def analyze(self, df: pd.DataFrame) -> pd.DataFrame:
          """Bin track durations and report exact minutes per bin.

          Args:
              df: Track-level DataFrame with a ``duration_min`` column.

          Returns:
              DataFrame with columns ``bin_low``, ``bin_high``, ``count``,
              ``minutes_in_bin``. ``minutes_in_bin`` is the exact sum of
              durations falling in the bin — useful for total-runtime
              annotation in ``plot``.
          """
          empty = pd.DataFrame(
              {"bin_low": [], "bin_high": [], "count": [], "minutes_in_bin": []}
          )
          if df.empty or "duration_min" not in df.columns:
              return empty
          values = pd.to_numeric(df["duration_min"], errors="coerce").dropna()
          if values.empty:
              return empty
          counts, edges = np.histogram(values, bins=self.bins)
          # Exact minutes per bin: digitize each value to its bin index, then
          # sum durations weighted into bincount. np.digitize uses 1-based
          # indices for values inside the range; subtract 1 and clip the last
          # edge so the rightmost value lands in the final bin (matches
          # np.histogram's right-inclusive last bin).
          bin_idx = np.clip(np.digitize(values, edges) - 1, 0, self.bins - 1)
          minutes_in_bin = np.bincount(bin_idx, weights=values, minlength=self.bins)
          return pd.DataFrame(
              {
                  "bin_low": edges[:-1],
                  "bin_high": edges[1:],
                  "count": counts.astype(int),
                  "minutes_in_bin": minutes_in_bin,
              }
          )

      def plot(self, ax: Axes, summary: pd.DataFrame) -> None:
          """Render a duration histogram with total-runtime annotation in the title.

          Args:
              ax: Matplotlib Axes to draw on.
              summary: Output of ``analyze``.
          """
          if summary.empty or summary["count"].sum() == 0:
              ax.text(0.5, 0.5, "No duration data", ha="center", va="center")
              ax.set_title(self.title)
              return
          widths = summary["bin_high"] - summary["bin_low"]
          ax.bar(summary["bin_low"], summary["count"], width=widths, align="edge")
          total_min = summary["minutes_in_bin"].sum()
          hours = int(total_min // 60)
          minutes = int(total_min % 60)
          ax.set_xlabel("Duration (minutes)")
          ax.set_ylabel("Track count")
          ax.set_title(f"{self.title} (total runtime: {hours}h {minutes}m)")
  ```

- [ ] **Step 4.6: Run duration tests — expect pass**

  Run:
  ```
  .venv/Scripts/python.exe -m pytest tests/test_analyzer.py -k duration -v
  ```
  Expected: `3 passed`.

- [ ] **Step 4.7: Format, lint, type-check**

  Run:
  ```
  .venv/Scripts/python.exe -m ruff format src/spotify_project/analyzer.py tests/test_analyzer.py
  .venv/Scripts/python.exe -m ruff check src/spotify_project/analyzer.py tests/test_analyzer.py
  .venv/Scripts/python.exe -m pyright src/spotify_project/analyzer.py
  ```
  Expected: clean.

- [ ] **Step 4.8: Commit**

  ```
  git add src/spotify_project/analyzer.py tests/test_analyzer.py
  git commit -m "feat(analyzer): DurationAnalyzer with exact per-bin minutes for runtime annotation"
  ```

---

### Task 5: `TimelineAnalyzer`

**Design note — fallback semantics:** Spotify-curated playlists return `added_at: null` for every track. To stay useful in that case, `TimelineAnalyzer` checks whether `added_at` is entirely missing/NaT; if so, it falls back to `release_date`. The result columns are the same in both cases (`period`, `count`); the analyzer reports its mode in the title via `plot()`.

**Files:**
- Modify: `src/spotify_project/analyzer.py`
- Modify: `tests/test_analyzer.py`

- [ ] **Step 5.1: Write the failing happy-path test**

  Append to `tests/test_analyzer.py`:

  ```python
  def test_timeline_analyzer_groups_added_at_by_month_by_default() -> None:
      """TimelineAnalyzer groups added_at into monthly periods by default."""
      from datetime import datetime, timezone

      from spotify_project.analyzer import TimelineAnalyzer

      df = _frame(
          [
              {"track_id": "1", "added_at": datetime(2024, 1, 5, tzinfo=timezone.utc)},
              {"track_id": "2", "added_at": datetime(2024, 1, 28, tzinfo=timezone.utc)},
              {"track_id": "3", "added_at": datetime(2024, 3, 10, tzinfo=timezone.utc)},
              {"track_id": "4", "added_at": None},
          ]
      )
      summary = TimelineAnalyzer().analyze(df)
      assert list(summary.columns) == ["period", "count"]
      counts = dict(zip(summary["period"].astype(str), summary["count"], strict=True))
      assert counts["2024-01"] == 2
      assert counts["2024-03"] == 1
  ```

- [ ] **Step 5.2: Add the fallback-to-release_date test**

  Append:

  ```python
  def test_timeline_analyzer_falls_back_to_release_date_when_all_added_at_missing() -> None:
      """When added_at is entirely missing, TimelineAnalyzer uses release_date.

      Models the Spotify-curated-playlist case: the API returns added_at=null
      for every track on official editorial playlists.
      """
      from spotify_project.analyzer import TimelineAnalyzer

      df = _frame(
          [
              {"track_id": "1", "added_at": None, "release_date": "2020-05-01"},
              {"track_id": "2", "added_at": None, "release_date": "2020-05-15"},
              {"track_id": "3", "added_at": None, "release_date": "2021-02-01"},
          ]
      )
      summary = TimelineAnalyzer().analyze(df)
      counts = dict(zip(summary["period"].astype(str), summary["count"], strict=True))
      assert counts["2020-05"] == 2
      assert counts["2021-02"] == 1
  ```

- [ ] **Step 5.3: Add the all-missing-data test**

  Append:

  ```python
  def test_timeline_analyzer_returns_empty_when_no_dates_at_all() -> None:
      """TimelineAnalyzer returns an empty summary if both added_at and release_date are missing."""
      from spotify_project.analyzer import TimelineAnalyzer

      df = _frame(
          [
              {"track_id": "1", "added_at": None, "release_date": None},
          ]
      )
      summary = TimelineAnalyzer().analyze(df)
      assert summary.empty
      assert list(summary.columns) == ["period", "count"]
  ```

- [ ] **Step 5.4: Run the failing tests**

  Run:
  ```
  .venv/Scripts/python.exe -m pytest tests/test_analyzer.py -k timeline -v
  ```
  Expected: `ImportError: cannot import name 'TimelineAnalyzer'`.

- [ ] **Step 5.5: Implement `TimelineAnalyzer`**

  Add to `src/spotify_project/analyzer.py` after `DurationAnalyzer`:

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
          # Track which column ``analyze`` last used, so ``plot`` can label
          # the chart correctly. Set in analyze(); read in plot().
          self._last_source: str = "added_at"

      def analyze(self, df: pd.DataFrame) -> pd.DataFrame:
          """Group track additions (or release dates) into time-period buckets.

          Args:
              df: Track-level DataFrame; must contain ``added_at`` and
                  optionally ``release_date``.

          Returns:
              DataFrame with columns ``period`` (pandas Period) and ``count``,
              sorted ascending by period.
          """
          empty = pd.DataFrame({"period": [], "count": []})
          if df.empty:
              self._last_source = "added_at"
              return empty

          source_col = "added_at"
          values = pd.to_datetime(df.get("added_at"), errors="coerce", utc=True)
          if values.isna().all() and "release_date" in df.columns:
              source_col = "release_date"
              values = pd.to_datetime(
                  df["release_date"].astype(str), errors="coerce", utc=True
              )
          self._last_source = source_col

          values = values.dropna()
          if values.empty:
              return empty

          periods = values.dt.to_period(self.freq)
          return (
              periods.value_counts()
              .sort_index()
              .rename_axis("period")
              .reset_index(name="count")
          )

      def plot(self, ax: Axes, summary: pd.DataFrame) -> None:
          """Render an area-style line chart of track additions over time.

          Args:
              ax: Matplotlib Axes to draw on.
              summary: Output of ``analyze``; columns ``period`` and ``count``.
          """
          if summary.empty:
              ax.text(0.5, 0.5, "No timeline data", ha="center", va="center")
              ax.set_title(self.title)
              return
          # Plot against period.start_time so matplotlib gets real datetimes.
          x = summary["period"].apply(lambda p: p.start_time)
          ax.fill_between(x, summary["count"], step="mid", alpha=0.4)
          ax.plot(x, summary["count"], marker="o")
          ax.set_xlabel("Time")
          ax.set_ylabel("Tracks added")
          source_label = "added_at" if self._last_source == "added_at" else "release_date (fallback)"
          ax.set_title(f"{self.title} (source: {source_label})")
  ```

  > **Note on `_last_source`:** This is a small piece of analyzer state that lets `plot` describe what `analyze` actually did. If we ever want side-effect-free analyzers (e.g. to parallelize), promote this to a column on the summary df. For Sprint B it stays as `_last_source` — simple and works.

- [ ] **Step 5.6: Run timeline tests — expect pass**

  Run:
  ```
  .venv/Scripts/python.exe -m pytest tests/test_analyzer.py -k timeline -v
  ```
  Expected: `3 passed`.

- [ ] **Step 5.7: Run the full suite**

  Run:
  ```
  .venv/Scripts/python.exe -m pytest -q
  ```
  Expected: 14 (post-Task 2) + 3 (Task 3) + 3 (Task 4) + 3 (Task 5) = `23 passed`.

- [ ] **Step 5.8: Format, lint, type-check the whole package**

  Run:
  ```
  .venv/Scripts/python.exe -m ruff format src tests
  .venv/Scripts/python.exe -m ruff check src tests
  .venv/Scripts/python.exe -m pyright src tests
  ```
  Expected: clean.

- [ ] **Step 5.9: Commit**

  ```
  git add src/spotify_project/analyzer.py tests/test_analyzer.py
  git commit -m "feat(analyzer): TimelineAnalyzer with release_date fallback for curated playlists"
  ```

> **CHECKPOINT 3 — STOP HERE.** Confirm with the user that the four new analyzers behave as expected on synthetic data. The library is now feature-complete for Sprint B; only parquet round-trip and notebook regen remain.

---

### Task 6: Parquet round-trip test

The `to_parquet` method already exists (Sprint A); we only need to confirm it round-trips with the new schema columns intact.

**Files:**
- Create: `tests/test_playlist_analyzer.py`

- [ ] **Step 6.1: Write the round-trip test**

  Create `tests/test_playlist_analyzer.py`:

  ```python
  from __future__ import annotations

  from pathlib import Path

  import pandas as pd

  from spotify_project.analyzer import PlaylistAnalyzer


  def test_to_parquet_round_trip_preserves_schema(tmp_path: Path) -> None:
      """to_parquet → read_parquet preserves columns and values exactly.

      Especially important for the list columns (``artist_ids``, ``artist_names``,
      ``genres``) which parquet stores as nested types.
      """
      df = pd.DataFrame(
          [
              {
                  "track_id": "t1",
                  "name": "Song",
                  "primary_artist_id": "a1",
                  "primary_artist_name": "Alice",
                  "all_artists": "Alice",
                  "artist_ids": ["a1"],
                  "artist_names": ["Alice"],
                  "album_name": "Album",
                  "release_date": "2020-01-01",
                  "release_year": pd.array([2020], dtype="Int64")[0],
                  "duration_ms": 200_000,
                  "duration_min": 200_000 / 60_000,
                  "popularity": 50,
                  "explicit": False,
                  "added_at": pd.Timestamp("2024-06-01", tz="UTC"),
                  "is_local": False,
                  "genres": ["rock"],
              }
          ]
      )
      pa = PlaylistAnalyzer(df=df, analyzers=[])
      out = tmp_path / "playlist.parquet"
      pa.to_parquet(out)
      assert out.exists()

      reloaded = pd.read_parquet(out)
      assert list(reloaded.columns) == list(df.columns)
      assert reloaded.iloc[0]["track_id"] == "t1"
      assert list(reloaded.iloc[0]["artist_ids"]) == ["a1"]
      assert list(reloaded.iloc[0]["genres"]) == ["rock"]
  ```

- [ ] **Step 6.2: Run the test — expect either pass, or a missing-engine error**

  Run:
  ```
  .venv/Scripts/python.exe -m pytest tests/test_playlist_analyzer.py -v
  ```
  Expected: pass — *or* `ImportError: Missing optional dependency 'pyarrow'` (or `fastparquet`). If it's the missing-dep case, install one and retry: `.venv/Scripts/python.exe -m pip install pyarrow` and add `pyarrow>=15` to `requirements.txt`.

- [ ] **Step 6.3: If pyarrow needed installing, commit the requirements bump first**

  Only if Step 6.2 surfaced a missing-dependency error:

  ```
  git add requirements.txt
  git commit -m "chore(deps): pin pyarrow for parquet engine"
  ```

- [ ] **Step 6.4: Format, lint, type-check the new test**

  Run:
  ```
  .venv/Scripts/python.exe -m ruff format tests/test_playlist_analyzer.py
  .venv/Scripts/python.exe -m ruff check tests/test_playlist_analyzer.py
  .venv/Scripts/python.exe -m pyright tests/test_playlist_analyzer.py
  ```
  Expected: clean.

- [ ] **Step 6.5: Commit the test**

  ```
  git add tests/test_playlist_analyzer.py
  git commit -m "test(analyzer): parquet round-trip preserves list-column schema"
  ```

---

### Task 7: Edit the demo notebook directly + real-Spotify smoke test

Per user direction, the `.ipynb` is the source of truth — we edit it via `NotebookEdit` (no committed generator script). We end with a real end-to-end execution against the user's Spotify account (their `.env` is filled and the OAuth token is cached at `.cache/spotify_token`); the agent sees only stdout, never the secrets.

**Files:**
- Delete: `scripts/create_notebook.py` (no longer the source of truth)
- Modify: `notebooks/01_explore_playlist.ipynb` (cells edited directly)

**Tool note:** `NotebookEdit` is a deferred tool — the executing subagent must load it once via `ToolSearch(query="select:NotebookEdit", max_results=1)` before its first call.

- [ ] **Step 7.1: Delete the legacy generator script**

  ```
  git rm scripts/create_notebook.py
  ```
  (If the directory `scripts/` is now empty, leave it — `git` will tidy it up at commit time, and an empty `scripts/` directory is harmless.)

- [ ] **Step 7.2: Inspect the current notebook to see what cells exist**

  ```
  .venv/Scripts/python.exe -c "import nbformat; nb = nbformat.read('notebooks/01_explore_playlist.ipynb', as_version=4); [print(i, c.cell_type, c.source.split(chr(10))[0][:80]) for i, c in enumerate(nb.cells)]"
  ```
  Expected: a numbered list of the existing 11 cells (markdown + code) from Sprint A. Use this output to know which cell indices to overwrite vs. append.

- [ ] **Step 7.3: Replace cell 1 (the imports/setup code cell — currently cell index 1) with the Sprint B imports**

  Use `NotebookEdit` with `cell_id` pointing at the imports cell (or by index per the tool's API), `edit_mode="replace"`. New source:

  ```python
  from pathlib import Path
  from dotenv import load_dotenv
  import matplotlib.pyplot as plt
  import seaborn as sns
  from spotify_project.cache import FileCache
  from spotify_project.client import SpotifyClient
  from spotify_project.analyzer import (
      PlaylistAnalyzer,
      GenreAnalyzer,
      YearAnalyzer,
      ArtistAnalyzer,
      PopularityAnalyzer,
      DurationAnalyzer,
      TimelineAnalyzer,
  )

  load_dotenv()
  sns.set_theme(style="whitegrid")
  cache = FileCache(root=Path(".cache") / "api")
  client = SpotifyClient.from_env(cache=cache)
  ```

- [ ] **Step 7.4: Replace the "build PlaylistAnalyzer" cell with the six-analyzer version**

  Locate the existing cell that constructs `PlaylistAnalyzer.from_playlist(playlist)` (Sprint A's section 4). Replace its source with:

  ```python
  analyzers = [
      GenreAnalyzer(top_n=15),
      YearAnalyzer(bucket_size=10),
      ArtistAnalyzer(top_n=15, primary_only=False),
      PopularityAnalyzer(bins=10),
      DurationAnalyzer(bins=20),
      TimelineAnalyzer(freq="M"),
  ]
  analyzer = PlaylistAnalyzer.from_playlist(playlist, analyzers=analyzers)
  results = analyzer.run_all()
  for title, df in results.items():
      print(title)
      print(df.head(), end="\n\n")
  ```

  And replace the markdown cell that precedes it (Sprint A's "## 4. Build the PlaylistAnalyzer …") with:

  ```markdown
  ## 4. Build the PlaylistAnalyzer with all six analyzers

  Tweak knobs here:
  - `YearAnalyzer(bucket_size=10)` for decade buckets — set to `1` for per-year bars.
  - `ArtistAnalyzer(primary_only=True)` to ignore collaborators.
  - `TimelineAnalyzer(freq='Y')` for yearly buckets instead of monthly.
  ```

- [ ] **Step 7.5: Update the plot cell to use a taller figure**

  Find the plot cell (Sprint A's "## 5. Render plots"); replace its source with:

  ```python
  fig = plt.figure(figsize=(12, 24))
  analyzer.plot_all(fig)
  plt.show()
  ```

  (Six subplots stacked vertically need more height than the original two.)

- [ ] **Step 7.6: Append the parquet-export cells**

  Append a new markdown cell (`edit_mode="insert"` after the last cell):

  ```markdown
  ## 6. (Optional) Export the flattened track DataFrame to parquet

  Useful for offline analysis in another tool, or for archiving the snapshot
  you analyzed today.
  ```

  Then append a new code cell:

  ```python
  EXPORT = False  # set True to write the file
  if EXPORT:
      out = Path("exports") / f"{playlist.id}.parquet"
      out.parent.mkdir(parents=True, exist_ok=True)
      analyzer.to_parquet(out)
      print(f"wrote {out}")
  ```

- [ ] **Step 7.7: Update the title markdown cell (cell 0) to reflect Sprint B**

  Replace the cell-0 source with:

  ```markdown
  # Spotify Playlist Explorer

  Phase 1 demo (Sprint B): authenticate, pick a playlist, run six analyzers
  (genres, release year, top artists, popularity, duration, timeline), render
  plots, and optionally export to parquet.
  ```

- [ ] **Step 7.8: Confirm the notebook is well-formed and lists 13 cells**

  Run:
  ```
  .venv/Scripts/python.exe -c "import nbformat; nb = nbformat.read('notebooks/01_explore_playlist.ipynb', as_version=4); print(f'cells: {len(nb.cells)}'); [print(i, c.cell_type) for i, c in enumerate(nb.cells)]"
  ```
  Expected: `cells: 13` (the original 11 from Sprint A − the section-6-and-below ones we did NOT have, + the 2 new parquet cells; adjust the number if your inspect-step in 7.2 showed different starting cell counts). The order should be `markdown, code, markdown, code, markdown, code, markdown, code, markdown, code, markdown, markdown, code` — title, setup, §1 md, §1 code, §2 md, §2 code, §3 md, §3 code, §4 md, §4 code, §5 md, §6 md, §6 code. (If reality differs from this, fix the structure before continuing.)

- [ ] **Step 7.9: Synthetic-data execution check (no Spotify API)**

  Quick sanity check before touching real Spotify — exercises every analyzer plus `plot_all` against fabricated data:

  ```
  .venv/Scripts/python.exe -c "
  from datetime import datetime, timezone
  import matplotlib
  matplotlib.use('Agg')
  import matplotlib.pyplot as plt
  from spotify_project.models import Artist, Playlist, Track
  from spotify_project.analyzer import (
      PlaylistAnalyzer, GenreAnalyzer, YearAnalyzer, ArtistAnalyzer,
      PopularityAnalyzer, DurationAnalyzer, TimelineAnalyzer,
  )
  a1 = Artist(id='a1', name='Alice', genres=('rock','indie'), popularity=70)
  a2 = Artist(id='a2', name='Bob', genres=('pop',), popularity=55)
  tracks = tuple(
      Track(id=f't{i}', name=f'Song {i}', artists=(a1, a2) if i % 2 == 0 else (a1,),
            album_name='Album', release_date=f'{1980 + i}-01-01',
            duration_ms=180_000 + i * 5_000, popularity=10 + i * 3,
            explicit=False, added_at=datetime(2024, 1 + (i % 12), 1, tzinfo=timezone.utc),
            is_local=False)
      for i in range(12)
  )
  playlist = Playlist(id='pl', name='Synthetic', owner_display_name='test',
                      public=True, collaborative=False, description='', tracks=tracks)
  analyzers = [
      GenreAnalyzer(top_n=10), YearAnalyzer(bucket_size=10),
      ArtistAnalyzer(top_n=10), PopularityAnalyzer(bins=10),
      DurationAnalyzer(bins=10), TimelineAnalyzer(freq='M'),
  ]
  pa = PlaylistAnalyzer.from_playlist(playlist, analyzers=analyzers)
  results = pa.run_all()
  for title, df in results.items():
      print(f'{title}: {len(df)} rows, cols={list(df.columns)}')
  fig = plt.figure(figsize=(12, 24))
  pa.plot_all(fig)
  print('plot_all OK')
  "
  ```
  Expected: six analyzer lines (each with >0 rows), then `plot_all OK`. If any analyzer reports 0 rows, fix before moving on.

- [ ] **Step 7.10: Real-Spotify execution — list playlists, pick one, fill the placeholder**

  The notebook still has `PLAYLIST_ID = 'REPLACE_WITH_AN_ID_FROM_THE_TABLE_ABOVE'`. To execute end-to-end we need a real playlist ID. Run a short subprocess to authenticate, list the user's playlists, and emit the first **owned** one (per the Feb 2026 API constraint — only owned/collaborative playlists return tracks):

  ```
  .venv/Scripts/python.exe -c "
  import os
  from pathlib import Path
  from dotenv import load_dotenv
  load_dotenv()
  from spotify_project.cache import FileCache
  from spotify_project.client import SpotifyClient
  client = SpotifyClient.from_env(cache=FileCache(root=Path('.cache') / 'api'))
  me = client.current_user()
  print('user:', me['display_name'], me['id'])
  pls = client.user_playlists()
  owned = [p for p in pls if p['owner']['id'] == me['id']]
  print('total playlists:', len(pls), 'owned:', len(owned))
  if owned:
      p = owned[0]
      print('PICKED', p['id'], p['name'], p['tracks']['total'], 'tracks')
  "
  ```

  Expected output: user identity + an `owned` playlist line. **If auth fails** with a token-expired error, escalate to the user with: "Run `.venv/Scripts/python.exe -c 'from spotify_project.cache import FileCache; from spotify_project.client import SpotifyClient; from pathlib import Path; SpotifyClient.from_env(cache=FileCache(root=Path(\".cache\")/\"api\"))'` once in your terminal to refresh the OAuth flow, then ping me to resume."

  **Capture the picked playlist ID** — you'll plug it into the notebook in the next step.

- [ ] **Step 7.11: Patch the notebook's `PLAYLIST_ID` to the picked ID**

  Use `NotebookEdit` to find the cell containing `PLAYLIST_ID = 'REPLACE_WITH_AN_ID_FROM_THE_TABLE_ABOVE'` and replace that string literal with the actual ID from Step 7.10. Replace just the literal — keep the rest of the cell unchanged.

  > **NOTE — temporary edit, will be reverted before commit.** This change is for verification only. Step 7.13 reverts the placeholder so the committed notebook stays generic.

- [ ] **Step 7.12: Execute the notebook end-to-end via nbconvert**

  ```
  .venv/Scripts/python.exe -m jupyter nbconvert --to notebook --execute --inplace notebooks/01_explore_playlist.ipynb --ExecutePreprocessor.timeout=180
  ```

  Expected: success, no traceback. Then inspect the executed cells programmatically:

  ```
  .venv/Scripts/python.exe -c "
  import nbformat
  nb = nbformat.read('notebooks/01_explore_playlist.ipynb', as_version=4)
  for i, c in enumerate(nb.cells):
      if c.cell_type != 'code':
          continue
      for out in c.get('outputs', []):
          text = out.get('text') or out.get('data', {}).get('text/plain', '')
          if isinstance(text, list):
              text = ''.join(text)
          if text:
              print(f'--- cell {i} ---')
              print(text[:500])
  "
  ```

  **Verify the agent-side checklist** (don't claim success until each is true):
  - cell `1` (setup) ran without raising → no `RuntimeError: Missing required env var`.
  - cell `3` (current_user) printed a `Hello, <name>` line.
  - cell `5` (user_playlists) printed a DataFrame head with non-zero rows.
  - cell `7` (fetch playlist) printed `<name>: <N> tracks` with N > 0.
  - cell `9` (run_all) printed six analyzer summaries, each with non-zero rows.
  - cell `11` (plot_all) produced an image output (in `outputs[*].data["image/png"]`) — but **the agent is not asked to judge the image's aesthetics, only its existence**.

  If any checkpoint fails, surface the failure to the user with the cell index and traceback excerpt before continuing.

- [ ] **Step 7.13: Revert the `PLAYLIST_ID` to the placeholder + clear outputs**

  Per repo policy (and per the Sprint A commit `e8ffc17`'s `--clear-output`), we don't commit personal playlist IDs or execution outputs. Restore the placeholder via `NotebookEdit` and clear outputs:

  ```
  .venv/Scripts/python.exe -m jupyter nbconvert --clear-output --inplace notebooks/01_explore_playlist.ipynb
  ```

  And use `NotebookEdit` to set the playlist-fetch cell back to `PLAYLIST_ID = 'REPLACE_WITH_AN_ID_FROM_THE_TABLE_ABOVE'`.

- [ ] **Step 7.14: Confirm the working tree shows expected diff**

  ```
  git status
  git diff --stat notebooks/01_explore_playlist.ipynb
  ```
  Expected: `scripts/create_notebook.py` deleted; `notebooks/01_explore_playlist.ipynb` modified. The notebook diff should include the new imports, six-analyzer block, and the parquet section, but NOT a real playlist ID and NOT execution outputs.

- [ ] **Step 7.15: Commit**

  ```
  git add notebooks/01_explore_playlist.ipynb scripts/create_notebook.py
  git commit -m "feat(notebook): Sprint B — six analyzers, bucket_size knob, parquet export; drop generator script"
  ```

- [ ] **Step 7.16: User-side final pass (visual check)**

  > **STOP HERE — user step.** Open `notebooks/01_explore_playlist.ipynb` in your IDE, replace the `PLAYLIST_ID` placeholder with one of your real playlists, run all cells, and eyeball the **visual output**:
  >
  > - Six subplots render in cell 11; each is labeled, axes have units, no overlap.
  > - The mean line on the popularity plot is visible.
  > - The total-runtime annotation on the duration plot reads sensibly (e.g. `4h 12m`, not `1234567h`).
  > - The timeline plot's title says `(source: added_at)` for your owned playlist (or `(source: release_date (fallback))` if you tested against a curated one).
  >
  > If anything looks off, paste a screenshot back — visual judgments are yours, not the agent's.

> **🎉 SPRINT B COMPLETE.** All six analyzers ship; the notebook surfaces them with the user's preferred parameter knobs (`bucket_size`, `primary_only`); parquet export is wired up with a regression test. Sprint C (polish) is optional from here.

---

## Self-review

**Spec coverage** (Sprint B outline → task that implements it):

- B.1 ArtistAnalyzer (top artists by track count + total minutes; primary_only flag) → **Task 2** ✓
- B.2 PopularityAnalyzer (histogram with mean line) → **Task 3** ✓ (weighted-mean line in `plot()`)
- B.3 DurationAnalyzer (histogram + total runtime annotation) → **Task 4** ✓ (`minutes_in_bin` for exact total in title)
- B.4 TimelineAnalyzer (added_at, fallback to release_date) → **Task 5** ✓
- B.5 Parquet export round-trip → **Task 6** ✓
- B.6 Plot polish → folded into per-analyzer plots (axis labels, titles, mean line, runtime annotation, source-column annotation). The `sns.set_theme` call already lives in cell 1 of the notebook. **No standalone polish task** — every analyzer's `plot()` is self-contained and labeled.
- B.7 Notebook regenerate → **Task 7** ✓

Open questions from the original Sprint A plan, addressed:

- **Decade buckets in YearAnalyzer?** ✓ Resolved via `bucket_size: int = 1` parameter (Task 1). Default unchanged.
- **ArtistAnalyzer primary-vs-all toggle?** ✓ Resolved via `primary_only: bool = False` parameter (Task 2). Default is all-artists per user preference.

**Placeholder scan:** No `TBD`, `TODO`, "fill in later", or "add appropriate handling". Each step contains the actual code or command. The notebook's `'REPLACE_WITH_AN_ID_FROM_THE_TABLE_ABOVE'` is a deliberate runtime placeholder for the user, not a plan placeholder.

**Type / signature consistency:**

- `Analyzer.analyze(df) -> pd.DataFrame` — every new subclass conforms.
- `Analyzer.plot(ax, summary) -> None` — every new subclass conforms (no figure-level mutation).
- `PlaylistAnalyzer.from_playlist(playlist, analyzers=None)` — schema additions in Task 2 don't change the signature; only the row-dict gets two new keys.
- `ArtistAnalyzer(top_n=15, primary_only=False)` — keyword args used consistently in tests and notebook.
- `YearAnalyzer(bucket_size=1)` — same.
- `PopularityAnalyzer(bins=10)` / `DurationAnalyzer(bins=20)` — both use `bins` keyword.
- `TimelineAnalyzer(freq="M")` — pandas Period string; documented and used in notebook.

**Known limitations not addressed in Sprint B (deferred to Sprint C if needed):**

- `run_all()` keys results by `Analyzer.title` (`ClassVar[str]`). Two instances of the same Analyzer subclass with different parameters cannot coexist in one `PlaylistAnalyzer` — the second overwrites the first. Fix would be an instance-level `title` override, plus loosening the `__init_subclass__` check to allow both class- and instance-level definitions. Not needed for any documented Sprint B use case.
- `TimelineAnalyzer._last_source` is per-instance state mutated by `analyze()` and read by `plot()`. Not thread-safe; not parallelizable. Fine for the notebook flow.

---

## Execution handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-05-spotify-phase1-sprint-b.md`.

**Two execution options:**

1. **Subagent-Driven (recommended)** — fresh subagent per task, two-stage review between tasks (build/correctness then code-quality). Good when you want to focus on green-lighting at checkpoints.
2. **Inline Execution** — execute tasks in this session with checkpoints batched for review. Good when you want to be in the room while it happens.

Which approach?
