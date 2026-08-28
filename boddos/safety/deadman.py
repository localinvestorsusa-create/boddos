"""Dead-man's switch / safety check-in timer.

You arm it before a risky activity ("walking home, check on me in 30 min"). If
you don't check in before the deadline, it auto-triggers a duress alert. Also
supports a recurring check-in cadence for ongoing situations.
"""
from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass
class CheckIn:
    label: str
    deadline: float
    interval_s: float | None  # if set, re-arms on each check-in
    fired: bool = False


class DeadMansSwitch:
    def __init__(self):
        self._active: dict[str, CheckIn] = {}

    def arm(self, label: str, minutes: float, recurring: bool = False) -> dict:
        interval = minutes * 60
        self._active[label] = CheckIn(
            label=label,
            deadline=time.time() + interval,
            interval_s=interval if recurring else None,
        )
        return {"ok": True, "label": label, "due_in_s": interval, "recurring": recurring}

    def check_in(self, label: str) -> dict:
        c = self._active.get(label)
        if not c:
            return {"ok": False, "error": "no such check-in"}
        if c.interval_s:
            c.deadline = time.time() + c.interval_s
            c.fired = False
            return {"ok": True, "rearmed_for_s": c.interval_s}
        del self._active[label]
        return {"ok": True, "cleared": True}

    def cancel(self, label: str) -> dict:
        return {"ok": self._active.pop(label, None) is not None}

    def due(self) -> list[CheckIn]:
        """Check-ins whose deadline has passed and haven't fired yet."""
        now = time.time()
        out = []
        for c in self._active.values():
            if not c.fired and now >= c.deadline:
                c.fired = True
                out.append(c)
        return out

    def status(self) -> list[dict]:
        now = time.time()
        return [
            {"label": c.label, "due_in_s": round(c.deadline - now, 1),
             "recurring": c.interval_s is not None, "overdue": now >= c.deadline}
            for c in self._active.values()
        ]
