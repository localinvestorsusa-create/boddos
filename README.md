# BODDOS

A minimal skeleton: a bare FastAPI backend and a bare Vite/React frontend,
connected to each other and ready for new instructions. Everything that
used to be built on top of this — the mesh, local-model chat, voice, Ogun
labs, safety/security systems, smart home, planner, news, and all the
frontend design — has been removed.

## Layout

```
boddos/
  __main__.py     node entrypoint: `python -m boddos --config config/boddos.yaml`
  config.py       NodeCfg + Config (id, bind_host, bind_port — nothing else)
  api/server.py   FastAPI app factory — a single GET /health route
config/
  boddos.example.yaml   copy to boddos.yaml and edit per-node
frontend/
  src/App.tsx     pings /health on load, shows connection status
  src/api.ts      the one fetch call (checkHealth)
  vite.config.ts  dev-server proxy for /api and /health -> the backend
```

## Run it

```bash
python3 -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"
python -m pytest -q            # test suite
python -m boddos --config config/boddos.yaml --port 8000   # backend

cd frontend
npm install
npm run dev                    # http://localhost:5173, proxies to :8000
```

The backend's default port is 8787; the frontend dev proxy expects it on
8000, so pass `--port 8000` (as above) or edit `frontend/vite.config.ts`
to match.
