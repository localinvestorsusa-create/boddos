"""Detect whether YOU are being followed by a rogue BLE tracker.

Threat model: someone slips an AirTag / Tile / generic BLE beacon into your bag
or car. Such a tracker travels with you, so it appears in your ESP32/phone BLE
scans across *different locations and time windows* — unlike a device that
belongs to one place you visited.

Heuristic: a BLE MAC that
  * shows up in scans across >= `follow_threshold` distinct location bins, and
  * persists over a meaningful time span,
is flagged as a possible follower. We surface it for the human to investigate;
we never phone home or identify the tracker's owner.

Note: many trackers rotate their MAC address for privacy, which limits pure-MAC
tracking — this catches the naive/persistent case and complements the phone OS's
own unknown-tracker alerts (iOS/Android). It is not a guarantee.
"""
from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field


def _loc_bin(lat: float | None, lon: float | None) -> str:
    if lat is None or lon is None:
        return "unknown"
    # ~1.1 km grid — coarse "distinct place" bucket.
    return f"{round(lat, 2)},{round(lon, 2)}"


@dataclass
class _Track:
    mac: str
    name: str = ""
    locations: set[str] = field(default_factory=set)
    first_seen: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    count: int = 0


class TrackerDetector:
    def __init__(self, follow_threshold: int = 3, min_span_s: float = 600.0):
        self.follow_threshold = follow_threshold
        self.min_span_s = min_span_s
        self._tracks: dict[str, _Track] = defaultdict(lambda: _Track(mac=""))

    def observe(self, ble: list[dict], lat: float | None, lon: float | None) -> None:
        loc = _loc_bin(lat, lon)
        now = time.time()
        for d in ble:
            mac = d.get("mac")
            if not mac:
                continue
            t = self._tracks[mac]
            t.mac = mac
            t.name = d.get("name") or t.name
            if loc != "unknown":
                t.locations.add(loc)
            t.last_seen = now
            t.count += 1

    def suspects(self) -> list[dict]:
        out = []
        for t in self._tracks.values():
            span = t.last_seen - t.first_seen
            if len(t.locations) >= self.follow_threshold and span >= self.min_span_s:
                out.append({
                    "mac": t.mac,
                    "name": t.name,
                    "distinct_locations": len(t.locations),
                    "span_minutes": round(span / 60, 1),
                    "sightings": t.count,
                    "advice": ("Seen following you across multiple places. "
                               "Check your bag/vehicle; use your phone's built-in "
                               "unknown-tracker scan; contact authorities if you "
                               "feel unsafe."),
                })
        out.sort(key=lambda x: (x["distinct_locations"], x["sightings"]), reverse=True)
        return out
