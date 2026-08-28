"""Translate any language to English using the local advisor model.

Keeping translation on-device (via your local LLM) means conversations never
leave your machines. Speech-to-text on the phone feeds text here.
"""
from __future__ import annotations

from ..models.base import ChatMessage, ModelProvider

_SYSTEM = (
    "You are a translation engine. Detect the source language and translate the "
    "user's text into clear, natural English. Preserve meaning and tone. "
    "Respond with ONLY the English translation — no notes, no quotes."
)


async def translate_to_english(provider: ModelProvider, model: str, text: str) -> dict:
    text = (text or "").strip()
    if not text:
        return {"ok": False, "error": "empty text"}
    out = await provider.chat(
        model,
        [ChatMessage("system", _SYSTEM), ChatMessage("user", text)],
    )
    return {"ok": True, "source_text": text, "english": out}
