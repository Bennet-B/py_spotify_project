# Review Findings Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix all critical quality items from code review (I3–I11): docstring drift, test count, module list, logging visibility, tqdm dependency decision.

**Architecture:** Sequential fixes across README, docstrings, code comments, and notebook cells. No architectural changes—pure correctness and documentation updates. Logging changes are additive (info-level counters on dropped items).

**Tech Stack:** Python 3.11+, pytest, logging module. No new dependencies.

---

## Task 1: Fix README test count and add actual assertion phrase

**Files:**
- Modify: `README.md:140–150`

**Context:** README claims "Expected: 42 tests pass" but test count is actually 44. The review recommends dropping the count entirely and replacing with a general assertion.

- [ ] **Step 1: Read current README around line 141**

Already read above. Current text is:
```
Expected: 42 tests pass.
```

- [ ] **Step 2: Replace hardcoded count with a dynamic phrase**

Edit `README.md` line 141. Change:
```
Expected: 42 tests pass.
```

to:
```
All tests should pass.
```

This avoids count rot in the future.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs(readme): drop hardcoded test count, use dynamic assertion"
```

---

## Task 2: Update README module list to include User and PlaylistSummary

**Files:**
- Modify: `README.md:147`

**Context:** `models.py` was extended with `User` and `PlaylistSummary` dataclasses in commit 4599a4f. README module list is stale.

- [ ] **Step 1: Read current module list in README**

Around line 145–150. Currently:
```
- `src/spotify_project/models.py` — `Track`, `Playlist`, `Artist` (frozen dataclasses)
```

- [ ] **Step 2: Update to include new dataclasses**

Change to:
```
- `src/spotify_project/models.py` — `Track`, `Playlist`, `Artist`, `User`, `PlaylistSummary` (frozen dataclasses)
```

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs(readme): add User and PlaylistSummary to module list"
```

---

## Task 3: Fix README and models.py fetch_* method references

**Files:**
- Modify: `README.md:172`
- Modify: `src/spotify_project/models.py:100` (docstring)

**Context:** Methods were renamed from `playlist()` / `liked_songs()` / `artists()` to `fetch_playlist()` / `fetch_liked_songs()` / `fetch_user_playlists()` in recent commits. Docstrings and README still reference old names.

- [ ] **Step 1: Check README line 172**

Search for the Phase 2 planning section mentioning the old method names. Should see text like:
```
expose the same `playlist()` / `liked_songs()` / `artists()` interface
```

- [ ] **Step 2: Update README Phase 2 section**

Change to:
```
expose the same `fetch_playlist()` / `fetch_liked_songs()` / `fetch_user_playlists()` interface
```

- [ ] **Step 3: Read models.py line 100 docstring**

Currently says something like:
```
populated by `SpotifyClient.playlist`
```

- [ ] **Step 4: Update models.py docstring**

Change to:
```
populated by `SpotifyClient.fetch_playlist`
```

- [ ] **Step 5: Commit**

```bash
git add README.md src/spotify_project/models.py
git commit -m "docs: update fetch_* method names in docstrings and README"
```

---

## Task 4: Fix FileCache docstring — cache path is `<repo>/.cache/api`, not `<repo>/.cache`

**Files:**
- Modify: `src/spotify_project/cache.py:20` (class docstring)

**Context:** Default cache path is `<repo-root>/.cache/api`, but the class docstring says `<repo-root>/.cache`.

- [ ] **Step 1: Read cache.py lines 1–30**

Look for the FileCache class docstring around line 20.

- [ ] **Step 2: Update the docstring**

Find text like:
```
...cached to ``<repo-root>/.cache``...
```

Change to:
```
...cached to ``<repo-root>/.cache/api``...
```

- [ ] **Step 3: Commit**

```bash
git add src/spotify_project/cache.py
git commit -m "docs(cache): fix default cache path in docstring"
```

---

## Task 5: Remove "Sprint C" references from analyzer.py and notebook

**Files:**
- Modify: `src/spotify_project/analyzer.py:36` (docstring)
- Modify: `notebooks/01_explore_playlist.ipynb` (cell 0, markdown)

**Context:** Internal sprint references should not survive in shipping code or notebooks. Two instances to clean up.

- [ ] **Step 1: Read analyzer.py around line 36**

Look for a docstring mentioning "Sprint C". Should see something like:
```
"""Apply the Sprint C consistent style + coverage suffix to an Axes."""
```

- [ ] **Step 2: Update analyzer.py docstring**

Change to:
```
"""Apply a consistent style and coverage suffix to an Axes."""
```

Remove "Sprint C" reference entirely.

- [ ] **Step 3: Read notebook cell 0**

The first cell in `01_explore_playlist.ipynb` is a markdown header. It says something like:
```
# Phase 1 demo (Sprint C, final)
```

- [ ] **Step 4: Update notebook cell 0**

Change to:
```
# Phase 1 demo
```

Remove "(Sprint C, final)" entirely. Use `NotebookEdit` tool to make this change.

- [ ] **Step 5: Commit**

```bash
git add src/spotify_project/analyzer.py notebooks/01_explore_playlist.ipynb
git commit -m "docs: remove Sprint C references"
```

---

## Task 6: Add logging for silently-dropped items in fetch_user_playlists

**Files:**
- Modify: `src/spotify_project/client.py:118–140` (fetch_user_playlists method)

**Context:** The method filters out `None` slots silently. If a user has 5 deleted playlists, the listing shows 5 fewer with no feedback. Add a counter and log at info level if any were dropped.

- [ ] **Step 1: Read fetch_user_playlists (lines 118–140)**

Understand the current flow: playlists list is filtered `[p for p in results["items"] if p is not None]`.

- [ ] **Step 2: Update the method to count dropped items**

Replace the method body with:

```python
def fetch_user_playlists(self) -> list[PlaylistSummary]:
    """List the authenticated user's playlists.

    Filters out ``None`` slots in the API response (Spotify occasionally returns null entries for deleted or inaccessible playlists).

    Returns:
        List of ``PlaylistSummary`` objects, one per playlist.
    """
    results = cast(dict[str, Any], self.sp.current_user_playlists())
    raw: list[dict[str, Any]] = [p for p in results["items"] if p is not None]
    dropped = len(results["items"]) - len(raw)
    while results.get("next"):
        results = cast(dict[str, Any], self.sp.next(results))
        batch = [p for p in results["items"] if p is not None]
        dropped += len(results["items"]) - len(batch)
        raw.extend(batch)
    if dropped > 0:
        logger.info("Dropped %d deleted/inaccessible playlists", dropped)
    return [
        PlaylistSummary(
            id=str(p.get("id") or ""),
            name=str(p.get("name") or ""),
            owner_name=str((p.get("owner") or {}).get("display_name") or ""),  # pyright: ignore[reportUnknownArgumentType]
            track_count=int((p.get("items") or {}).get("total", 0)),  # pyright: ignore[reportUnknownArgumentType]
            public=bool(p.get("public", False)),
        )
        for p in raw
    ]
```

- [ ] **Step 3: Run tests to ensure they pass**

```bash
pytest tests/test_client.py::test_fetch_user_playlists -v
```

Expected: PASS. The mocked test should not be affected by the logging addition.

- [ ] **Step 4: Commit**

```bash
git add src/spotify_project/client.py
git commit -m "observability(client): log dropped playlists in fetch_user_playlists"
```

---

## Task 7: Add logging for silently-dropped podcasts/local files in _enrich_with_artists

**Files:**
- Modify: `src/spotify_project/client.py:230–250` (approx. _enrich_with_artists method)

**Context:** The method filters out non-track items (podcasts, local files) silently. Add a counter and log when any are dropped.

- [ ] **Step 1: Find _enrich_with_artists method**

Search for `def _enrich_with_artists` in `client.py`. It should be around line 240–260.

- [ ] **Step 2: Identify the filtering line**

Look for the line that filters `[x for x in ... if x.get("type") == "track"]` or similar.

- [ ] **Step 3: Add dropped-item counting**

Wrap the filtering to count non-track items:

```python
def _enrich_with_artists(self, items: list[dict[str, Any]]) -> list[Track]:
    """Fetch full Artist objects for a batch of tracks, indexed by artist ID.

    Args:
        items: List of track dicts from a paginated response.

    Returns:
        List of ``Track`` objects with ``primary_artist`` fully populated.
    """
    tracks = [x for x in items if x.get("type") == "track"]
    dropped = len(items) - len(tracks)
    if dropped > 0:
        logger.info("Dropped %d non-track items (podcasts, local files, etc.)", dropped)
    
    # ... rest of the method unchanged
    # artist_ids lookup, fetching, enrichment, etc.
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_client.py -v -k "enrich"
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/spotify_project/client.py
git commit -m "observability(client): log non-track items dropped in _enrich_with_artists"
```

---

## Task 8: Add logging for silently-dropped null tracks in fetch_liked_songs

**Files:**
- Modify: `src/spotify_project/client.py:200–220` (approx. fetch_liked_songs method)

**Context:** The liked-songs filter silently skips null tracks. Add logging when any are dropped.

- [ ] **Step 1: Find fetch_liked_songs method**

Search for `def fetch_liked_songs` in `client.py`. Should be around line 195–220.

- [ ] **Step 2: Identify the filtering line**

Look for filtering of null/None tracks in the response.

- [ ] **Step 3: Add dropped-item counting**

Find the line filtering tracks and add:

```python
def fetch_liked_songs(self) -> Playlist:
    """Fetch the authenticated user's liked songs ('Saved Tracks' library), enriched with Artist objects.

    Paginated, cached, fully enriched (each Track holds full Artist references).

    Args:
        force_refresh: If True, bypass cache.

    Returns:
        ``Playlist`` with id='liked', name='Liked Songs', and full Track objects.
    """
    results = cast(dict[str, Any], self.sp.current_user_saved_tracks(limit=50))
    raw: list[dict[str, Any]] = [t["track"] for t in results["items"] if t["track"] is not None]
    dropped = sum(1 for t in results["items"] if t["track"] is None)
    while results.get("next"):
        results = cast(dict[str, Any], self.sp.next(results))
        batch = [t["track"] for t in results["items"] if t["track"] is not None]
        dropped += sum(1 for t in results["items"] if t["track"] is None)
        raw.extend(batch)
    if dropped > 0:
        logger.info("Dropped %d null tracks from liked songs", dropped)
    
    # ... rest of enrichment unchanged
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_client.py::test_fetch_liked_songs -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/spotify_project/client.py
git commit -m "observability(client): log null tracks dropped in fetch_liked_songs"
```

---

## Task 9: Decide tqdm dependency — make it required, remove fallback

**Files:**
- Modify: `requirements.txt` (ensure tqdm is listed)
- Modify: `src/spotify_project/client.py:14–20` (remove tqdm import fallback)

**Context:** tqdm is in `requirements.txt` but client.py has a fallback for when it's not installed. The fallback is untested dead code. Decision: **tqdm is required** (not optional). Remove the fallback.

- [ ] **Step 1: Verify tqdm in requirements.txt**

Check that `tqdm>=4.66` is present in the file. It should be.

- [ ] **Step 2: Update client.py — remove the import fallback**

Replace lines 14–20:
```python
try:
    from tqdm import tqdm as _tqdm_cls

    _tqdm_available = True
except ImportError:
    _tqdm_cls = None  # pyright: ignore[reportAssignmentType]
    _tqdm_available = False
```

with:
```python
from tqdm import tqdm as _tqdm_cls
```

- [ ] **Step 3: Remove fallback usage in _get_artists**

Find any code that checks `if _tqdm_available:` and use `_tqdm_cls` unconditionally. Remove the conditional fallback.

Example: if there's code like:
```python
if _tqdm_available:
    for aid in tqdm(artist_ids):
        # ...
else:
    for aid in artist_ids:
        # ...
```

Simplify to:
```python
for aid in _tqdm_cls(artist_ids):
    # ...
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/ -v
```

Expected: ALL tests pass (42 originally, should still be 42 or more).

- [ ] **Step 5: Commit**

```bash
git add requirements.txt src/spotify_project/client.py
git commit -m "refactor(client): tqdm is required, remove fallback"
```

---

## Task 10: Clean up notebook cells — remove trailing comment and merge duplicate section headers

**Files:**
- Modify: `notebooks/01_explore_playlist.ipynb`

**Context:** Two minor cell-level cleanups:
- Cell `e8db6079`: trailing duplicate `# 3v8PWRLiPHGPY0oHgkoZvV` after a playlist-id assignment.
- Cell `adfe3d30`: duplicates the section header in cell `7dde2d9e`. Merge them.

- [ ] **Step 1: Open notebook and find cell e8db6079**

Read the notebook JSON and locate the cell with ID `e8db6079`. It should have a trailing comment that's a duplicate of a playlist ID.

- [ ] **Step 2: Remove trailing comment**

Edit the cell source to remove the line `# 3v8PWRLiPHGPY0oHgkoZvV` if it appears as a standalone trailing comment.

- [ ] **Step 3: Find cell adfe3d30 and 7dde2d9e**

Locate both cells. adfe3d30 should be a section header that duplicates one in 7dde2d9e.

- [ ] **Step 4: Merge or remove duplicate**

If both cells are simple markdown headers, keep one and delete the duplicate. If they have different content, consolidate into one cell.

- [ ] **Step 5: Commit**

```bash
git add notebooks/01_explore_playlist.ipynb
git commit -m "chore(notebook): clean up duplicate comments and section headers"
```

---

## Checklist Summary

**Text/Docstring fixes (Tasks 1–5):**
- [ ] T1: README test count
- [ ] T2: README module list
- [ ] T3: fetch_* method references
- [ ] T4: cache.py docstring path
- [ ] T5: Sprint C references

**Code/Logging fixes (Tasks 6–9):**
- [ ] T6: fetch_user_playlists logging
- [ ] T7: _enrich_with_artists logging
- [ ] T8: fetch_liked_songs logging
- [ ] T9: tqdm requirement decision

**Notebook cleanup (Task 10):**
- [ ] T10: Remove trailing comment + merge section headers

---

## Self-Review

**Spec coverage:** All I3–I11 items are covered. I9 (Sprint C) is split into analyzer.py + notebook sections.

**Placeholder scan:** All code shown in full. No "TBD" or generic descriptions. Each step includes actual text/code to change.

**Type consistency:** Logging calls use consistent patterns (`logger.info(...)`). Method signatures unchanged from existing code.

**Test coverage:** Tasks that modify `client.py` have test runs specified. Docstring-only tasks don't require new tests (they're pure documentation).

