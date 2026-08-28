"""Ollama-backed model provider.

Ollama is the pragmatic default for running local models on macOS (Metal) and
Linux/Windows. If Ollama isn't running, calls degrade gracefully so the rest of
the system still boots.
"""
from __future__ import annotations

import json
from typing import AsyncIterator

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

    @staticmethod
    def _to_payload(messages: list[ChatMessage], images: list[str] | None) -> list[dict]:
        out = [m.to_dict() for m in messages]
        if images and out:
            # Attach images (base64, no data: prefix) to the last user message
            # for a multimodal model like llava/llama3.2-vision.
            out[-1]["images"] = images
        return out

    async def chat(self, model: str, messages: list[ChatMessage],
                   images: list[str] | None = None) -> str:
        payload = {
            "model": model,
            "messages": self._to_payload(messages, images),
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

    async def chat_stream(self, model: str, messages: list[ChatMessage],
                          images: list[str] | None = None) -> AsyncIterator[str]:
        """Yield response text chunks as the model generates them."""
        payload = {
            "model": model,
            "messages": self._to_payload(messages, images),
            "stream": True,
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as c:
                async with c.stream("POST", f"{self.base_url}/api/chat", json=payload) as r:
                    if r.status_code >= 400:
                        yield f"[model error {r.status_code} — is '{model}' pulled?]"
                        return
                    async for line in r.aiter_lines():
                        if not line.strip():
                            continue
                        try:
                            obj = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        chunk = obj.get("message", {}).get("content", "")
                        if chunk:
                            yield chunk
                        if obj.get("done"):
                            break
        except Exception as e:
            yield f"[model unavailable: {e}. Is Ollama running at {self.base_url}?]"

    async def chat_with_tools(self, model: str, messages: list[dict],
                              tools: list[dict]) -> dict:
        """One non-streaming tool-calling round. Ollama's /api/chat accepts an
        OpenAI-style `tools` array and, for a tool-capable model, returns
        `message.tool_calls` (already-parsed argument dicts, not a JSON
        string) instead of/alongside `content` when it wants to call one."""
        payload = {"model": model, "messages": messages, "tools": tools, "stream": False}
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as c:
                r = await c.post(f"{self.base_url}/api/chat", json=payload)
                r.raise_for_status()
                return r.json().get("message", {"role": "assistant", "content": ""})
        except httpx.HTTPStatusError as e:
            return {"role": "assistant", "content": f"[model error: {e.response.status_code} — is '{model}' pulled?]"}
        except Exception as e:
            return {"role": "assistant", "content": f"[model unavailable: {e}. Is Ollama running at {self.base_url}?]"}

    async def pull(self, model: str) -> AsyncIterator[dict]:
        """Pull a model, yielding {status, completed, total} progress dicts."""
        try:
            async with httpx.AsyncClient(timeout=None) as c:
                async with c.stream("POST", f"{self.base_url}/api/pull",
                                    json={"model": model, "stream": True}) as r:
                    if r.status_code >= 400:
                        yield {"status": f"error {r.status_code}", "done": True}
                        return
                    async for line in r.aiter_lines():
                        if not line.strip():
                            continue
                        try:
                            yield json.loads(line)
                        except json.JSONDecodeError:
                            continue
        except Exception as e:
            yield {"status": f"pull failed: {e}", "done": True}
