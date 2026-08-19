"""Geofenced safe zones.

Define circular safe zones (home, work). BODDOS can alert when you leave all safe
zones (useful with the dead-man's switch) or when you enter a zone you marked as
a danger area. Pure local geometry — your location never leaves your nodes.
"""
from __future__ import annotations

import math
from dataclasses import dataclass


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


@dataclass
class Zone:
    name: str
    lat: float
    lon: float
    radius_m: float
    kind: str = "safe"   # "safe" | "danger"


class GeoFence:
    def __init__(self, zones: list[Zone] | None = None):
        self.zones = zones or []

    def add(self, zone: Zone) -> None:
        self.zones = [z for z in self.zones if z.name != zone.name]
        self.zones.append(zone)

    def evaluate(self, lat: float, lon: float) -> dict:
        inside = []
        for z in self.zones:
            if haversine_m(lat, lon, z.lat, z.lon) <= z.radius_m:
                inside.append(z)
        safe_zones = [z for z in self.zones if z.kind == "safe"]
        in_safe = any(z.kind == "safe" for z in inside)
        in_danger = [z.name for z in inside if z.kind == "danger"]
        alerts = []
        if safe_zones and not in_safe:
            alerts.append("outside all safe zones")
        for name in in_danger:
            alerts.append(f"entered danger zone: {name}")
        return {
            "inside": [z.name for z in inside],
            "in_safe_zone": in_safe,
            "alerts": alerts,
        }
