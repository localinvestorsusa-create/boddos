"""Panic / duress mode — the buildable core of an emergency 'boost'.

On trigger it:
  * flips the node into a heightened-alert state,
  * builds an alert payload (location, timestamp, note) for trusted contacts,
  * emits a mesh bus event so every node/phone in your mesh knows,
  * returns the actions taken so the UI can confirm.

Actual delivery to contacts goes through the CallingAdapter / a webhook you
configure. Contacts are YOUR consenting people.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from ..config import SafetyCfg


@dataclass
class DuressState:
    active: bool = False
    since: float | None = None
    last_note: str = ""
    last_location: dict | None = None
    history: list[dict] = field(default_factory=list)


class DuressManager:
    def __init__(self, cfg: SafetyCfg):
        self.cfg = cfg
        self.state = DuressState()

    def trigger(self, note: str = "", location: dict | None = None) -> dict:
        now = time.time()
        self.state.active = True
        self.state.since = now
        self.state.last_note = note
        self.state.last_location = location

        alerts = [
            {
                "to": c.name,
                "channel": c.channel,
                "target": c.target,
                "body": self._contact_body(note, location),
            }
            for c in self.cfg.trusted_contacts
        ]
        event = {
            "type": "safety.duress",
            "ts": now,
            "note": note,
            "location": location,
            "alerts_queued": len(alerts),
        }
        self.state.history.append(event)
        return {
            "ok": True,
            "state": "duress",
            "alerts": alerts,
            "broadcast": self.cfg.broadcast,
            "event": event,
        }

    def clear(self) -> dict:
        self.state.active = False
        self.state.since = None
        return {"ok": True, "state": "clear"}

    def _contact_body(self, note: str, location: dict | None) -> str:
        loc = ""
        if location and location.get("lat") is not None:
            loc = f" Location: https://maps.google.com/?q={location['lat']},{location['lon']}"
        extra = f" Note: {note}" if note else ""
        return f"BODDOS duress alert — I may need help.{loc}{extra}".strip()

    def snapshot(self) -> dict:
        return {
            "active": self.state.active,
            "since": self.state.since,
            "note": self.state.last_note,
            "location": self.state.last_location,
            "events": len(self.state.history),
        }
