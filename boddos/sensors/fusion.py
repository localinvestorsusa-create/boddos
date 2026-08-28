"""Fuse raw sensor readings into a live situational-awareness snapshot.

Inputs come from the ESP32 (Wi-Fi/BLE scans, magnetometer, mic level, motion)
and optionally the phone. We keep a short rolling history per source and derive
honest, real-physics observations:

  * nearby device count + rough proximity (from RSSI, coarse only)
  * magnetic-field anomalies (possible metal / strong fields nearby)
  * ambient sound level trend
  * motion / vibration events

What we deliberately DON'T claim: no see-through-wall imaging, no reading of
other people's heartbeats or emotions. RSSI gives coarse "closer/farther", not
precise distance, and never identity of a person.
"""
from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field


@dataclass
class Reading:
    source: str                       # node/sensor id, e.g. "esp32-pocket"
    ts: float = field(default_factory=time.time)
    wifi: list[dict] = field(default_factory=list)   # [{bssid,ssid,rssi}]
    ble: list[dict] = field(default_factory=list)     # [{mac,name,rssi}]
    mag_uT: float | None = None       # magnetometer magnitude (microtesla)
    sound_db: float | None = None     # relative sound level
    motion: float | None = None       # accel magnitude / vibration
    lat: float | None = None
    lon: float | None = None


def _rssi_bucket(rssi: int) -> str:
    if rssi >= -55:
        return "very close"
    if rssi >= -70:
        return "near"
    if rssi >= -85:
        return "in range"
    return "far"


class SensorFusion:
    def __init__(self, window: int = 60):
        self._readings: dict[str, deque[Reading]] = {}
        self.window = window

    def ingest(self, r: Reading) -> None:
        buf = self._readings.setdefault(r.source, deque(maxlen=self.window))
        buf.append(r)

    def _mag_baseline(self, source: str) -> float | None:
        buf = self._readings.get(source)
        vals = [x.mag_uT for x in buf if x.mag_uT is not None] if buf else []
        if len(vals) < 5:
            return None
        return sum(vals) / len(vals)

    def snapshot(self) -> dict:
        sources = {}
        for src, buf in self._readings.items():
            if not buf:
                continue
            latest = buf[-1]

            devices = []
            for d in latest.wifi:
                devices.append({"kind": "wifi", "id": d.get("bssid"),
                                "label": d.get("ssid", ""), "proximity": _rssi_bucket(int(d.get("rssi", -99)))})
            for d in latest.ble:
                devices.append({"kind": "ble", "id": d.get("mac"),
                                "label": d.get("name", ""), "proximity": _rssi_bucket(int(d.get("rssi", -99)))})

            observations = []
            baseline = self._mag_baseline(src)
            if baseline and latest.mag_uT is not None:
                delta = latest.mag_uT - baseline
                if abs(delta) > 20:
                    observations.append(
                        f"magnetic anomaly: {delta:+.0f} µT vs baseline "
                        "(possible large metal object or strong field nearby)"
                    )
            if latest.sound_db is not None and latest.sound_db > 85:
                observations.append("elevated ambient noise level")
            if latest.motion is not None and latest.motion > 2.0:
                observations.append("motion/vibration detected")

            sources[src] = {
                "age_s": round(time.time() - latest.ts, 1),
                "device_count": len(devices),
                "closest": min((d["proximity"] for d in devices), default=None,
                               key=lambda p: ["very close", "near", "in range", "far"].index(p))
                          if devices else None,
                "devices": devices[:40],
                "mag_uT": latest.mag_uT,
                "sound_db": latest.sound_db,
                "observations": observations,
                "location": ({"lat": latest.lat, "lon": latest.lon}
                             if latest.lat is not None else None),
            }
        return {"ts": time.time(), "sources": sources}

    def recent(self, source: str) -> list[Reading]:
        return list(self._readings.get(source, []))
