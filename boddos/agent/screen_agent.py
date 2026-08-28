"""Screen perception + control of THIS machine's own display — the "Ori can
see and click your screen" capability described in the Ori/OS-control brief.

Same conservative safety model as OSAgent: disabled by default, and every
click/type/press requires an explicit per-call confirm (the "quick
confirmation prompt" the brief asks for), independent of the server's
optional TOTP 2FA layered on top at the API level. Looking (screenshot +
description) is opt-in via `enabled` but doesn't require confirm — it's
read-only.

Needs a real display. On a headless node (CI, a server, a dev container)
pyautogui's platform backend has nothing to attach to, so the import is
deferred and a missing display is reported as an ordinary error result
instead of crashing the node at import time.
"""
from __future__ import annotations

import base64
import io
import json
import re
from dataclasses import dataclass, field

from ..config import ScreenCfg
from ..models.base import ChatMessage

DESCRIBE_PROMPT = (
    "You are looking at a screenshot of a computer desktop. List the clickable "
    "UI elements a user would plausibly want to act on next (buttons, links, "
    "menu items, text fields, icons) — at most 20, most relevant first. Reply "
    "with ONLY a JSON array, no prose, no markdown fences. Each item: "
    '{"label": short description, "kind": "button|field|link|icon|text", '
    '"x": fraction of image width 0-1, "y": fraction of image height 0-1}.'
)


@dataclass
class ScreenResult:
    ok: bool
    error: str = ""
    image_b64: str | None = None
    elements: list[dict] = field(default_factory=list)
    raw: str = ""

    def to_dict(self) -> dict:
        return dict(self.__dict__)


def _parse_elements(text: str) -> list[dict]:
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if not match:
        return []
    try:
        data = json.loads(match.group(0))
    except (json.JSONDecodeError, ValueError):
        return []
    out: list[dict] = []
    if not isinstance(data, list):
        return out
    for item in data:
        if not isinstance(item, dict):
            continue
        try:
            out.append({
                "label": str(item.get("label", ""))[:200],
                "kind": str(item.get("kind", "element"))[:40],
                "x": max(0.0, min(1.0, float(item.get("x", 0)))),
                "y": max(0.0, min(1.0, float(item.get("y", 0)))),
            })
        except (TypeError, ValueError):
            continue
    return out


class ScreenAgent:
    def __init__(self, cfg: ScreenCfg):
        self.cfg = cfg

    @staticmethod
    def _pyautogui():
        try:
            import pyautogui
        except Exception as e:  # ImportError, or a platform backend with no display
            raise RuntimeError(f"screen control unavailable: {e}") from e
        return pyautogui

    def _guard(self, confirm: bool) -> str | None:
        if not self.cfg.enabled:
            return "screen agent disabled on this node (set screen.enabled: true)"
        if self.cfg.require_confirm and not confirm:
            return "confirmation required (pass confirm=true)"
        return None

    def screenshot_b64(self, max_width: int = 1280) -> tuple[str | None, str]:
        try:
            pyautogui = self._pyautogui()
            img = pyautogui.screenshot()
        except Exception as e:
            return None, str(e)
        if img.width > max_width:
            ratio = max_width / img.width
            img = img.resize((max_width, max(1, int(img.height * ratio))))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode(), ""

    async def look(self, provider, vision_model: str, prompt: str | None = None) -> ScreenResult:
        if not self.cfg.enabled:
            return ScreenResult(ok=False, error="screen agent disabled on this node (set screen.enabled: true)")
        image_b64, err = self.screenshot_b64()
        if not image_b64:
            return ScreenResult(ok=False, error=err or "screenshot failed")
        reply = await provider.chat(
            vision_model,
            [ChatMessage("user", prompt or DESCRIBE_PROMPT)],
            images=[image_b64],
        )
        return ScreenResult(ok=True, image_b64=image_b64, elements=_parse_elements(reply), raw=reply)

    def click(self, x: float, y: float, confirm: bool = False) -> ScreenResult:
        reason = self._guard(confirm)
        if reason:
            return ScreenResult(ok=False, error=reason)
        try:
            pyautogui = self._pyautogui()
            size = pyautogui.size()
            px = max(0, min(size.width - 1, round(x * size.width)))
            py = max(0, min(size.height - 1, round(y * size.height)))
            pyautogui.click(px, py)
            return ScreenResult(ok=True, raw=f"clicked ({px}, {py})")
        except Exception as e:
            return ScreenResult(ok=False, error=str(e))

    def type_text(self, text: str, confirm: bool = False) -> ScreenResult:
        reason = self._guard(confirm)
        if reason:
            return ScreenResult(ok=False, error=reason)
        try:
            pyautogui = self._pyautogui()
            pyautogui.write(text, interval=0.02)
            return ScreenResult(ok=True, raw=f"typed {len(text)} chars")
        except Exception as e:
            return ScreenResult(ok=False, error=str(e))

    def press(self, key: str, confirm: bool = False) -> ScreenResult:
        reason = self._guard(confirm)
        if reason:
            return ScreenResult(ok=False, error=reason)
        try:
            pyautogui = self._pyautogui()
            pyautogui.press(key)
            return ScreenResult(ok=True, raw=f"pressed {key}")
        except Exception as e:
            return ScreenResult(ok=False, error=str(e))
