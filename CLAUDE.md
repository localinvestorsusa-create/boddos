# CLAUDE.md — working in the BODDOS repo

BODDOS is currently a minimal skeleton: a bare FastAPI backend and a bare
Vite/React frontend, connected to each other, with everything previously
built on top of them removed. Read `README.md` first — it documents the
whole (small) layout.

## Conventions

- Python 3.10+, FastAPI, async. Type hints, `from __future__ import annotations`.
- Keep the backend/frontend connection (the `/health` round trip, and
  `frontend/vite.config.ts`'s proxy) working as new features get added —
  it's the one thing this skeleton exists to preserve.

## Dev commands

```bash
python3 -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"
python -m pytest -q            # test suite
python -m boddos --config config/boddos.yaml --port 8000   # backend

cd frontend && npm install && npm run dev   # frontend, http://localhost:5173
```

CI runs `pytest` on 3.10 and 3.12 (`.github/workflows/ci.yml`). Keep it green.
