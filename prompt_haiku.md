# Haiku 4.5 handoff — mechanical text edits + naming sweep

Hi! Spotify analytics project, Python 3.11, src/ layout. **Read `CLAUDE.md` first** for context (course rubric, no-dead-API rule, docstring style preference).

Six small mechanical tasks, no architecture changes. **One commit per task** (six commits) in conventional-commits style (see `git log` for examples). Run `ruff format` after every task.

> ⚠️ **If the Sonnet handoff has not yet been merged**, some method names below may already have moved. Re-check before editing — `grep` for the symbol first.

---

## 1. README: "Code quality" section

Add a short "Code quality" section to `README.md` explaining how to run the toolchain. Keep it 5–10 lines max.

- `ruff check` — lint
- `ruff format` — format (Black-compatible)
- `pyright` — strict type check
- `pytest` — tests

Reference `pyproject.toml` for tool config. Don't duplicate the config in the README.

---

## 2. Docstring TTL notes (3 small additions)

Match the existing docstring style (Google/Sphinx-mixed — see other methods in the file).

- **`SpotifyClient.artists()` docstring**: add a sentence — *"Cached with default TTL (see `FileCache`); pass `force_refresh=True` to bypass."*
- **`SpotifyClient.playlist()` docstring**: it already mentions `force_refresh`; add the TTL hint as well.
- **`FileCache` class docstring**: add a sentence — *"TTL is the default; individual `set()` calls can override it per-call."*

---

## 3. Error message — restore owner + name

In `client.py`, this line:

```python
raise ValueError(f"Playlist {playlist_id} returned no track details.")
```

Change to include the playlist owner and name where available:

```python
raise ValueError(
    f"Playlist {playlist_id} [Owner: {owner_name}, Name: {playlist_name}] "
    f"returned no track details."
)
```

Extract `owner_name` and `playlist_name` from the `data` dict that's already in scope (`data["owner"]["display_name"]` and `data["name"]`). Fall back to `"<unknown>"` if missing.

---

## 4. Fix `user_playlists` docstring

Currently says `"List the authenticated user's playlists (id, name, track count)."` — misleading because it returns **raw Spotify dicts** with many more fields. Replace with:

```
List the authenticated user's playlists as raw Spotify playlist dicts
(id, name, owner, tracks.total, images, …). Filters out None slots
that Spotify occasionally returns for deleted or otherwise inaccessible
playlists.
```

---

## 5. Naming convention sweep

Scan `src/spotify_project/` for naming inconsistencies:

- **Logger names**: `client.py` uses `logger`, `models.py` uses `_log`. Pick one (suggest `logger`) and apply everywhere. *(May already be done by Sonnet — re-check first.)*
- **Methods that look like properties but do network I/O**: rename to `fetch_*` to make the I/O obvious.
  - `SpotifyClient.playlist()` → `fetch_playlist()`
  - `SpotifyClient.artists()` → `fetch_artists()`
  - `SpotifyClient.user_playlists()` → `fetch_user_playlists()`
  - any others you find that do network I/O.
- Update **all callers** — `tests/`, `notebooks/`, anywhere in `src/`.

**Before doing the renames**, list them in a short proposal so the user can sanity-check. Then proceed.

---

## 6. Delete + gitignore stray files

`test_output.txt` and `test_pyright.txt` at the repo root are tracked but look like local test-run captures.

- `git rm` both files.
- Add `test_output.txt` and `test_pyright.txt` to `.gitignore`.

---

## Constraints

- Run `ruff format` after each task.
- Don't refactor anything beyond what's listed.
- If anything is ambiguous, **ASK** — don't guess.
