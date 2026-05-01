"""One-shot generator for notebooks/01_explore_playlist.ipynb.

Run after editing the cell content here:

    .venv/Scripts/python.exe scripts/create_notebook.py
"""

from __future__ import annotations

from pathlib import Path

import nbformat as nbf

CELLS = [
    ("md", "# Spotify Playlist Explorer\n\n"
           "Phase 1 demo: authenticate, pick a playlist, run "
           "Genre + Year analyses, render plots."),
    ("code", (
        "from pathlib import Path\n"
        "from dotenv import load_dotenv\n"
        "import matplotlib.pyplot as plt\n"
        "import seaborn as sns\n"
        "from spotify_project.cache import FileCache\n"
        "from spotify_project.client import SpotifyClient\n"
        "from spotify_project.analyzer import PlaylistAnalyzer\n\n"
        "load_dotenv()\n"
        "sns.set_theme(style='whitegrid')\n"
        "cache = FileCache(root=Path('.cache') / 'api')\n"
        "client = SpotifyClient.from_env(cache=cache)"
    )),
    ("md", "## 1. Confirm authentication"),
    ("code", (
        "user = client.current_user()\n"
        "print(f\"Hello, {user['display_name']} ({user['id']})\")"
    )),
    ("md", "## 2. List your playlists\n\n"
           "Spotify renamed `tracks` → `items` in their Feb 2026 migration. "
           "The `items` field is only present on playlists you own or "
           "collaborate on; for followed playlists, `tracks` reads as 0."),
    ("code", (
        "import pandas as pd\n"
        "playlists = client.user_playlists()\n"
        "summary = pd.DataFrame([\n"
        "    {\n"
        "        'id': p.get('id', ''),\n"
        "        'name': p.get('name', '<unnamed>'),\n"
        "        'tracks': (p.get('items') or {}).get('total', 0),\n"
        "        'owner': p.get('owner', {}).get('display_name', ''),\n"
        "    }\n"
        "    for p in playlists\n"
        "])\n"
        "summary.head(20)"
    )),
    ("md", "## 3. Pick a playlist and fetch it\n\n"
           "Replace `PLAYLIST_ID` below with one of the IDs from the table above."),
    ("code", (
        "PLAYLIST_ID = 'REPLACE_WITH_AN_ID_FROM_THE_TABLE_ABOVE'\n"
        "playlist = client.playlist(PLAYLIST_ID)\n"
        "print(f\"{playlist.name}: {len(playlist.tracks)} tracks\")"
    )),
    ("md", "## 4. Build the PlaylistAnalyzer and run analyses"),
    ("code", (
        "analyzer = PlaylistAnalyzer.from_playlist(playlist)\n"
        "results = analyzer.run_all()\n"
        "for title, df in results.items():\n"
        "    print(title)\n"
        "    print(df.head(), end='\\n\\n')"
    )),
    ("md", "## 5. Render plots"),
    ("code", (
        "fig = plt.figure(figsize=(10, 8))\n"
        "analyzer.plot_all(fig)\n"
        "plt.show()"
    )),
]


def main() -> None:
    nb = nbf.v4.new_notebook()
    nb.cells = [
        nbf.v4.new_markdown_cell(content) if kind == "md"
        else nbf.v4.new_code_cell(content)
        for kind, content in CELLS
    ]
    out_path = Path("notebooks") / "01_explore_playlist.ipynb"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    nbf.write(nb, out_path)
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
