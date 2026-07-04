"""Guards the core/web boundary: importing core modules must never pull in web frameworks.

The Phase 2 policy keeps ``src/spotify_project`` (minus ``web/``) framework-free so the analysis/organizer logic stays reusable from the notebook, tests,
and any future client. The check runs in a subprocess so this test cannot be poisoned by other tests having already imported FastAPI.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]

_CORE_MODULES = (
    "spotify_project.analyzer",
    "spotify_project.cache",
    "spotify_project.client",
    "spotify_project.genre_taxonomy",
    "spotify_project.insights",
    "spotify_project.lastfm_client",
    "spotify_project.logging_setup",
    "spotify_project.models",
)

_FORBIDDEN = ("fastapi", "pydantic", "starlette", "uvicorn")


def test_core_modules_do_not_import_web_frameworks() -> None:
    """Importing every core module leaves fastapi/pydantic/starlette/uvicorn out of sys.modules."""
    imports = "\n".join(f"import {module}" for module in _CORE_MODULES)
    code = f"{imports}\nimport sys\nleaked = [name for name in {_FORBIDDEN!r} if name in sys.modules]\nassert not leaked, f'core imports leaked web frameworks: {{leaked}}'"
    env = {**os.environ, "PYTHONPATH": str(_REPO_ROOT / "src")}
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120, cwd=_REPO_ROOT, env=env)
    assert result.returncode == 0, f"core/web boundary violated:\n{result.stderr}"
