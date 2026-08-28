"""Provider-agnostic interface for a locally hosted model."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class ChatMessage:
    role: str   # "system" | "user" | "assistant"
    content: str

    def to_dict(self) -> dict:
        return {"role": self.role, "content": self.content}


class ModelProvider(Protocol):
    """Any local model backend (Ollama, llama.cpp server, MLX, ...)."""

    async def list_models(self) -> list[str]:
        ...

    async def chat(self, model: str, messages: list[ChatMessage],
                   images: list[str] | None = None) -> str:
        ...

    async def available(self) -> bool:
        ...

    async def chat_with_tools(self, model: str, messages: list[dict],
                              tools: list[dict]) -> dict:
        """One non-streaming round of tool-calling chat. `messages` and the
        return value are raw dicts (OpenAI/Ollama message shape — including
        `tool_calls` and `tool` role) rather than plain ChatMessage, since a
        tool round-trip needs richer fields than role/content."""
        ...
