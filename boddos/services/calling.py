"""Calling adapter (stub).

Plug in a provider you control (e.g. a SIP/VoIP gateway on your LAN, or a
programmable-telephony account). Kept as a thin interface so the UI and safety
modules can 'place a call' without knowing the backend.
"""
from __future__ import annotations

from ..config import CallingCfg


class CallingAdapter:
    def __init__(self, cfg: CallingCfg):
        self.cfg = cfg

    async def place_call(self, number: str, message: str = "") -> dict:
        if not self.cfg.enabled:
            return {"ok": False, "error": "calling module disabled"}
        # TODO: dispatch to your SIP/VoIP/telephony provider here.
        return {
            "ok": True,
            "queued": True,
            "provider": self.cfg.provider,
            "number": number,
            "message": message,
            "note": "stub — wire a telephony backend in CallingAdapter.place_call",
        }
