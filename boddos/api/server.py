"""Bare BODDOS API — a minimal FastAPI app with just a health check.

Everything that used to live here (mesh, models, agent, ogun, safety,
security, sensors, services, skills, tools, voice) has been intentionally
removed. This is the connection point for whatever gets built next: the
frontend dev server proxies /api and /health here (see
frontend/vite.config.ts), so the gateway between the two stays live.
"""
from __future__ import annotations

from fastapi import FastAPI

from ..config import Config


def build_app(cfg: Config) -> FastAPI:
    app = FastAPI(title="BODDOS", version="0.1.0")

    @app.get("/health")
    async def health():
        return {"ok": True, "node": cfg.node.id}

    return app
