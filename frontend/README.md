# Workbench frontend

Vite + React + TypeScript UI for the Phase 2 workbench. Talks to the FastAPI backend (`uvicorn spotify_project.web.app:create_app --factory`, port 8000); the dev server proxies `/api` there.

```bash
npm install        # once
npm run dev        # localhost:5173
npm test           # vitest
npm run build      # tsc + vite production build
npm run gen:api    # regenerate src/api/types.gen.ts from openapi.json
```

`openapi.json` is produced by `python scripts/export_openapi.py` at the repo root — regenerate both whenever backend schemas or routes change. TypeScript is pinned to `~5.9` because `openapi-typescript` requires TS `^5.x`.
