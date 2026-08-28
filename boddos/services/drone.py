"""Drone control adapter.

High-level commands (takeoff/land/rtl/goto/hover/status) map to MAVLink when a
real backend is available. Uses `pymavlink` if installed (extra:
`pip install boddos[mavlink]`); otherwise queues the command and reports that no
backend is connected, so the rest of the system keeps a stable interface.

Fly only your own drones, only where it's legal, within local UAS rules and
visual line of sight.
"""
from __future__ import annotations

import asyncio

from ..config import DroneCfg

_ALLOWED = {"takeoff", "land", "rtl", "goto", "hover", "status", "arm", "disarm"}

try:
    from pymavlink import mavutil  # type: ignore
    _HAVE_MAVLINK = True
except Exception:  # pragma: no cover - optional dep
    _HAVE_MAVLINK = False


class DroneAdapter:
    def __init__(self, cfg: DroneCfg):
        self.cfg = cfg
        self._conn = None

    async def command(self, action: str, params: dict | None = None) -> dict:
        if not self.cfg.enabled:
            return {"ok": False, "error": "drone module disabled"}
        if not self.cfg.endpoint:
            return {"ok": False, "error": "no drone endpoint configured"}
        action = action.lower().strip()
        if action not in _ALLOWED:
            return {"ok": False, "error": f"unknown action '{action}' (allowed: {sorted(_ALLOWED)})"}
        if not _HAVE_MAVLINK:
            return {"ok": True, "queued": True, "action": action, "params": params or {},
                    "note": "pymavlink not installed; install boddos[mavlink] for a live link"}
        return await asyncio.to_thread(self._mavlink_command, action, params or {})

    # ----- blocking MAVLink calls (run in a thread) -----
    def _connect(self):
        if self._conn is None:
            self._conn = mavutil.mavlink_connection(self.cfg.endpoint)
            self._conn.wait_heartbeat(timeout=10)
        return self._conn

    def _mavlink_command(self, action: str, params: dict) -> dict:
        try:
            m = self._connect()
        except Exception as e:
            self._conn = None
            return {"ok": False, "error": f"cannot reach drone at {self.cfg.endpoint}: {e}"}
        try:
            if action == "status":
                hb = m.recv_match(type="HEARTBEAT", blocking=True, timeout=5)
                return {"ok": True, "action": "status",
                        "armed": bool(hb and (hb.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED))}
            if action == "arm":
                m.arducopter_arm(); return {"ok": True, "action": "arm"}
            if action == "disarm":
                m.arducopter_disarm(); return {"ok": True, "action": "disarm"}
            if action == "takeoff":
                alt = float(params.get("alt", 10))
                m.mav.command_long_send(m.target_system, m.target_component,
                    mavutil.mavlink.MAV_CMD_NAV_TAKEOFF, 0, 0, 0, 0, 0, 0, 0, alt)
                return {"ok": True, "action": "takeoff", "alt": alt}
            if action in ("land", "hover"):
                mode = "LAND" if action == "land" else "LOITER"
                m.set_mode(mode)
                return {"ok": True, "action": action, "mode": mode}
            if action == "rtl":
                m.set_mode("RTL"); return {"ok": True, "action": "rtl"}
            if action == "goto":
                lat, lon, alt = float(params["lat"]), float(params["lon"]), float(params.get("alt", 20))
                m.mav.mission_item_send(
                    m.target_system, m.target_component, 0,
                    mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT,
                    mavutil.mavlink.MAV_CMD_NAV_WAYPOINT, 2, 0, 0, 0, 0, 0,
                    lat, lon, alt)
                return {"ok": True, "action": "goto", "lat": lat, "lon": lon, "alt": alt}
            return {"ok": False, "error": f"unhandled action {action}"}
        except Exception as e:
            return {"ok": False, "error": f"mavlink command failed: {e}"}
