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

import asyncio
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

# A drive step whose target label or typed text matches one of these always
# pauses for an explicit human "yes", no matter how fast the rest of the
# loop is allowed to run — financial and destructive actions are the one
# place speed is the wrong trade.
_SENSITIVE_RE = re.compile(
    r"\b("
    r"pay|payment|purchase|buy\s*now|checkout|place\s*order|confirm\s*order|"
    r"add\s*to\s*cart\s*&?\s*buy|"
    r"delete|remove|uninstall|format|erase|wipe|factory\s*reset|"
    r"send\s*money|transfer\s*funds?|wire|withdraw|donate|"
    r"log\s*out\s*(all|everywhere)|deactivate|delete\s*account|close\s*account|"
    r"unsubscribe|cancel\s*subscription|"
    r"sudo|rm\s+-rf|shutdown|restart|reboot"
    r")\b",
    re.IGNORECASE,
)


def is_sensitive(text: str) -> bool:
    """True if `text` (a candidate click's label, or typed text) looks
    financial or destructive enough to warrant a human's explicit go-ahead
    even when the drive loop is otherwise running at full speed."""
    return bool(_SENSITIVE_RE.search(text or ""))


DECIDE_PROMPT = (
    "You are driving a computer toward a goal, one UI action at a time. "
    "Goal: {goal}\n\n"
    "Visible elements on the current screenshot (label, kind, position as a "
    "fraction of the screen): {elements}\n\n"
    "Steps already taken this turn: {history}\n\n"
    "Reply with ONLY one JSON object, no prose, no markdown fences, choosing "
    "the single next action:\n"
    '{{"action": "click", "target_label": "<one of the labels above>", "reason": "..."}}\n'
    '{{"action": "type", "text": "<text to type>", "reason": "..."}}\n'
    '{{"action": "press", "key": "<a key name, e.g. enter, tab, escape>", "reason": "..."}}\n'
    '{{"action": "done", "reason": "why the goal is now met"}}\n'
    "Choose \"done\" as soon as the goal is met or nothing useful remains to do."
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


@dataclass
class DriveStep:
    action: str  # "click" | "type" | "press" | "done" | "blocked" | "error"
    detail: str = ""
    label: str = ""

    def to_dict(self) -> dict:
        return dict(self.__dict__)


@dataclass
class DriveResult:
    ok: bool
    error: str = ""
    steps: list[DriveStep] = field(default_factory=list)
    finished: bool = False
    awaiting_confirmation: dict | None = None
    final_image_b64: str | None = None

    def to_dict(self) -> dict:
        d = dict(self.__dict__)
        d["steps"] = [s.to_dict() for s in self.steps]
        return d


def _parse_decision(text: str) -> dict | None:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("action") not in ("click", "type", "press", "done"):
        return None
    return data


def _nearest_element(label: str, elements: list[dict]) -> dict | None:
    """The decision step names a target by label; match it back to the
    (x, y) an earlier vision pass found for it. Exact match first, then a
    loose substring match either direction so small rewording by the model
    doesn't strand a perfectly good click."""
    if not label:
        return None
    low = label.strip().lower()
    for el in elements:
        if el.get("label", "").strip().lower() == low:
            return el
    for el in elements:
        el_label = el.get("label", "").strip().lower()
        if el_label and (el_label in low or low in el_label):
            return el
    return None


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

    def _execute_decision(self, decision: dict, elements: list[dict]) -> ScreenResult:
        action = decision["action"]
        if action == "click":
            el = _nearest_element(decision.get("target_label", ""), elements)
            if el is None:
                return ScreenResult(ok=False, error=f"no visible element matches \"{decision.get('target_label', '')}\"")
            return self.click(el["x"], el["y"], confirm=True)
        if action == "type":
            return self.type_text(decision.get("text", ""), confirm=True)
        if action == "press":
            return self.press(decision.get("key", ""), confirm=True)
        return ScreenResult(ok=False, error=f"unknown drive action: {action}")

    async def drive(self, provider, model: str, vision_model: str, goal: str,
                    max_steps: int | None = None, slow: bool = False) -> DriveResult:
        """The fast perceive-decide-act loop: screenshot, ask the vision
        model what's on screen, ask the text model which single action gets
        closer to `goal`, and either execute it immediately or — for
        anything that looks financial/destructive — stop and hand back
        `awaiting_confirmation` for the caller to confirm explicitly.

        Runs at the natural speed of a screenshot + two model calls with no
        added delay, unless `slow=True` (the user explicitly asked to watch
        it work), which inserts a short pause between steps so each one is
        visible.
        """
        if not self.cfg.enabled:
            return DriveResult(ok=False, error="screen agent disabled on this node (set screen.enabled: true)")
        steps: list[DriveStep] = []
        limit = max_steps or self.cfg.max_drive_steps
        history_summary = "(none yet)"
        last_image_b64: str | None = None
        for _ in range(max(1, limit)):
            image_b64, err = self.screenshot_b64()
            if not image_b64:
                return DriveResult(ok=False, error=err or "screenshot failed", steps=steps)
            last_image_b64 = image_b64

            vision_reply = await provider.chat(vision_model, [ChatMessage("user", DESCRIBE_PROMPT)], images=[image_b64])
            elements = _parse_elements(vision_reply)

            prompt = DECIDE_PROMPT.format(
                goal=goal,
                elements=json.dumps([{"label": e["label"], "kind": e["kind"]} for e in elements]),
                history=history_summary,
            )
            decision_reply = await provider.chat(model, [ChatMessage("user", prompt)])
            decision = _parse_decision(decision_reply)
            if decision is None:
                steps.append(DriveStep("error", f"couldn't parse a next action from the model's reply: {decision_reply[:200]}"))
                return DriveResult(ok=False, error="model didn't return a usable next action", steps=steps, final_image_b64=last_image_b64)

            if decision["action"] == "done":
                steps.append(DriveStep("done", decision.get("reason", "")))
                return DriveResult(ok=True, steps=steps, finished=True, final_image_b64=last_image_b64)

            target_text = " ".join(str(decision.get(k, "")) for k in ("target_label", "text", "key"))
            if is_sensitive(target_text) and self.cfg.require_confirm_for_sensitive:
                steps.append(DriveStep("blocked", "looks financial/destructive — needs your explicit yes", decision.get("target_label", "")))
                return DriveResult(ok=True, steps=steps, finished=False,
                                   awaiting_confirmation=decision, final_image_b64=last_image_b64)

            result = self._execute_decision(decision, elements)
            steps.append(DriveStep(decision["action"], result.raw or result.error, decision.get("target_label", "")))
            if not result.ok:
                return DriveResult(ok=False, error=result.error, steps=steps, final_image_b64=last_image_b64)

            history_summary = "; ".join(f"{s.action}({s.label or s.detail})" for s in steps[-5:])
            if slow:
                await asyncio.sleep(0.6)

        return DriveResult(ok=False, steps=steps, finished=False,
                           error=f"reached the {limit}-step limit for this turn without finishing",
                           final_image_b64=last_image_b64)
