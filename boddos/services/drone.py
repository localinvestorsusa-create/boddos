"""Drone control adapter (stub).

Real integration: connect to a MAVLink endpoint you control (e.g. via pymavlink
or MAVSDK) over your local link. Fly only your own drones, only where it's legal,
within visual line of sight and local UAS regulations.

This stub validates/queues high-level commands so the rest of the system (phone
UI, advisor) has a stable interface; wire a real backend in `_dispatch`.
"""
from __future__ import annotations

from ..config import DroneCfg

_ALLOWED = {"takeoff", "land", "rtl", "goto", "hover", "status"}


class DroneAdapter:
    def __init__(self, cfg: DroneCfg):
        self.cfg = cfg

    async def command(self, action: str, params: dict | None = None) -> dict:
        if not self.cfg.enabled:
            return {"ok": False, "error": "drone module disabled"}
        if not self.cfg.endpoint:
            return {"ok": False, "error": "no drone endpoint configured"}
        action = action.lower().strip()
        if action not in _ALLOWED:
            return {"ok": False, "error": f"unknown action '{action}' (allowed: {sorted(_ALLOWED)})"}
        return await self._dispatch(action, params or {})

    async def _dispatch(self, action: str, params: dict) -> dict:
        # TODO: replace with a real MAVLink/MAVSDK call to self.cfg.endpoint.
        return {
            "ok": True,
            "queued": True,
            "endpoint": self.cfg.endpoint,
            "action": action,
            "params": params,
            "note": "stub — connect a MAVLink backend in DroneAdapter._dispatch",
        }
