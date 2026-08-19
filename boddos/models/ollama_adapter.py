"""Ollama-backed model provider.

Ollama is the pragmatic default for running local models on macOS (Metal) and
Linux/Windows. If Ollama isn't running, calls degrade gracefully so the rest of
the system still boots.
"""
from __future__ import annotations

import httpx

from .base import ChatMessage


class OllamaProvider:
    def __init__(self, base_url: str = "http://127.0.0.1:11434", timeout: float = 120.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def available(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=3.0) as c:
                r = await c.get(f"{self.base_url}/api/tags")
                return r.status_code == 200
        except Exception:
            return False

    async def list_models(self) -> list[str]:
        try:
            async with httpx.AsyncClient(timeout=5.0) as c:
                r = await c.get(f"{self.base_url}/api/tags")
                r.raise_for_status()
                return [m["name"] for m in r.json().get("models", [])]
        except Exception:
            return []

    async def chat(self, model: str, messages: list[ChatMessage]) -> str:
        payload = {
            "model": model,
            "messages": [m.to_dict() for m in messages],
            "stream": False,
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as c:
                r = await c.post(f"{self.base_url}/api/chat", json=payload)
                r.raise_for_status()
                return r.json().get("message", {}).get("content", "").strip()
        except httpx.HTTPStatusError as e:
            return f"[model error: {e.response.status_code} — is '{model}' pulled?]"
        except Exception as e:
            return f"[model unavailable: {e}. Is Ollama running at {self.base_url}?]"
