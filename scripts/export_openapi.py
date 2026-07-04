"""Dump the FastAPI OpenAPI schema to ``frontend/openapi.json`` without starting a server.

The frontend's ``npm run gen:api`` consumes this file via ``openapi-typescript`` to regenerate ``src/api/types.gen.ts``.
Run whenever ``spotify_project/web/schemas.py`` or any route signature changes:

    .venv/Scripts/python.exe scripts/export_openapi.py
"""

from __future__ import annotations

import json
from pathlib import Path

from spotify_project.web.app import create_app


def main() -> None:
    """Write the schema and report the output path."""
    out_path = Path(__file__).resolve().parents[1] / "frontend" / "openapi.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    schema = create_app().openapi()
    out_path.write_text(json.dumps(schema, indent=2), encoding="utf-8")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
