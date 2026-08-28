"""Lost-device finder — BLE proximity tracking for something you already
own and paired (earbuds, a tracker tag, headphones), not a lookup tool
for finding anyone else's device.

RSSI-to-distance is notoriously environment-dependent — walls, orientation,
and interference all shift it by many dB — so this reports qualitative
proximity bands and a getting-warmer/colder trend from a rolling window of
samples, and deliberately never claims a distance in meters. Label the
heuristic honestly rather than pretend more precision than a BLE signal
strength number can actually provide.

Needs a BLE radio and a working backend (BlueZ on Linux, CoreBluetooth on
macOS) — on a machine with neither, scanning fails cleanly instead of
hanging.
"""
from __future__ import annotations

import asyncio
import time
from collections import deque
from dataclasses import dataclass, field

try:
    from bleak import BleakScanner
except ImportError:  # pragma: no cover - exercised via the ok=False path
    BleakScanner = None

# (rssi floor, label) — most-generous band first. A typical BLE radio at
# 0 dBm reads roughly: <1m ~ -40 to -55, same room ~ -55 to -70,
# adjoining room ~ -70 to -85, beyond that ~ unreliable. These are rough
# bands, not a distance measurement.
_PROXIMITY_BANDS: list[tuple[float, str]] = [
    (-55, "very close"),
    (-70, "nearby"),
    (-85, "far"),
]
_TREND_THRESHOLD_DB = 3.0


def _proximity_label(rssi: float) -> str:
    for floor, label in _PROXIMITY_BANDS:
        if rssi >= floor:
            return label
    return "very far"


@dataclass
class ScanResult:
    ok: bool
    error: str = ""
    devices: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return dict(self.__dict__)


@dataclass
class FinderStatus:
    ok: bool
    error: str = ""
    tracking: bool = False
    address: str = ""
    name: str = ""
    rssi: float | None = None
    proximity: str = ""
    trend: str = ""
    last_seen_s_ago: float | None = None

    def to_dict(self) -> dict:
        return dict(self.__dict__)


def _compute_trend(samples: list[tuple[float, float]]) -> str:
    """samples: [(timestamp, rssi), ...] oldest first."""
    if len(samples) < 4:
        return "reading…"
    values = [rssi for _, rssi in samples]
    half = len(values) // 2
    older_avg = sum(values[:half]) / half
    newer_avg = sum(values[half:]) / (len(values) - half)
    delta = newer_avg - older_avg
    if delta > _TREND_THRESHOLD_DB:
        return "getting warmer"
    if delta < -_TREND_THRESHOLD_DB:
        return "getting colder"
    return "steady"


class DeviceFinder:
    """Tracks one device at a time — a personal-belongings finder, not a
    fleet tracker."""

    def __init__(self, sample_window: int = 30):
        self._scanner = None
        self._address: str | None = None
        self._name: str = ""
        self._samples: deque[tuple[float, float]] = deque(maxlen=sample_window)

    async def scan(self, seconds: float = 4.0) -> ScanResult:
        if BleakScanner is None:
            return ScanResult(ok=False, error="bleak not installed (pip install 'boddos[finder]')")
        try:
            found = await BleakScanner.discover(timeout=seconds, return_adv=True)
        except Exception as e:
            return ScanResult(ok=False, error=f"BLE scan unavailable: {e}")
        devices = [
            {"address": addr, "name": dev.name or "(unnamed)", "rssi": adv.rssi}
            for addr, (dev, adv) in found.items()
        ]
        devices.sort(key=lambda d: d["rssi"], reverse=True)
        return ScanResult(ok=True, devices=devices)

    def _on_detection(self, device, advertisement_data) -> None:
        if device.address != self._address:
            return
        self._samples.append((time.time(), advertisement_data.rssi))
        if not self._name and device.name:
            self._name = device.name

    async def start(self, address: str, name: str = "") -> FinderStatus:
        if BleakScanner is None:
            return FinderStatus(ok=False, error="bleak not installed (pip install 'boddos[finder]')")
        await self.stop()
        self._address = address
        self._name = name
        self._samples.clear()
        try:
            self._scanner = BleakScanner(detection_callback=self._on_detection)
            await self._scanner.start()
        except Exception as e:
            self._scanner = None
            self._address = None
            return FinderStatus(ok=False, error=f"couldn't start BLE scan: {e}")
        return self.status()

    async def stop(self) -> FinderStatus:
        if self._scanner is not None:
            try:
                await self._scanner.stop()
            except Exception:
                pass
            self._scanner = None
        self._address = None
        self._samples.clear()
        return FinderStatus(ok=True, tracking=False)

    def status(self) -> FinderStatus:
        if self._address is None:
            return FinderStatus(ok=True, tracking=False)
        if not self._samples:
            return FinderStatus(ok=True, tracking=True, address=self._address, name=self._name,
                                trend="reading…")
        latest_ts, latest_rssi = self._samples[-1]
        return FinderStatus(
            ok=True, tracking=True, address=self._address, name=self._name,
            rssi=latest_rssi, proximity=_proximity_label(latest_rssi),
            trend=_compute_trend(list(self._samples)),
            last_seen_s_ago=round(time.time() - latest_ts, 1),
        )
