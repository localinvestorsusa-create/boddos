"""Detect surveillance risks around YOU from Wi-Fi/BLE scan data.

Two honest, defensive heuristics:

1. Evil-twin / rogue AP detection: the same SSID advertised by multiple
   different BSSIDs (MAC addresses), especially one that suddenly appears with a
   strong signal, can indicate a spoofed hotspot trying to get you to connect.

2. Device fingerprinting by OUI (MAC vendor prefix): flags nearby devices whose
   vendor prefix belongs to known IP-camera / tracker makers, so you can notice a
   hidden camera or beacon. This is a heuristic hint, not proof — vendors and
   randomized MACs limit it.

Everything here analyzes signals in the air around you. It does not attempt to
break into, deanonymize, or identify the *people* who own those devices.
"""
from __future__ import annotations

from collections import defaultdict

# Small illustrative OUI -> vendor map for commonly-hidden camera/tracker gear.
# Extend from the public IEEE OUI registry as needed.
CAMERA_TRACKER_OUI = {
    "00:12:FB": "Wyze/► camera",
    "2C:AA:8E": "Hikvision camera",
    "44:19:B6": "Hangzhou/► camera",
    "C0:56:E3": "Ring/► doorbell cam",
    "B0:C5:54": "D-Link camera",
    "10:5A:17": "TP-Link camera",
    "AC:CC:8E": "Axis camera",
    "50:C7:BF": "TP-Link/► IoT",
}


def _oui(mac: str) -> str:
    parts = mac.upper().replace("-", ":").split(":")
    return ":".join(parts[:3]) if len(parts) >= 3 else ""


def evil_twin_candidates(wifi: list[dict]) -> list[dict]:
    """SSIDs advertised by >1 distinct BSSID -> possible spoofing."""
    by_ssid: dict[str, list[dict]] = defaultdict(list)
    for ap in wifi:
        ssid = (ap.get("ssid") or "").strip()
        if ssid:
            by_ssid[ssid].append(ap)
    out = []
    for ssid, aps in by_ssid.items():
        bssids = {a.get("bssid") for a in aps if a.get("bssid")}
        if len(bssids) > 1:
            strongest = max(aps, key=lambda a: a.get("rssi", -999))
            out.append({
                "ssid": ssid,
                "bssid_count": len(bssids),
                "bssids": sorted(b for b in bssids if b),
                "strongest_rssi": strongest.get("rssi"),
                "risk": ("Multiple radios advertise this network name. If you did "
                         "not expect a mesh here, do not auto-connect — it may be "
                         "an evil-twin hotspot."),
            })
    return sorted(out, key=lambda x: x["bssid_count"], reverse=True)


def fingerprint_devices(wifi: list[dict], ble: list[dict]) -> list[dict]:
    """Flag nearby devices whose MAC vendor prefix looks like a camera/tracker."""
    hits = []
    for d in [*wifi, *ble]:
        mac = d.get("bssid") or d.get("mac") or ""
        vendor = CAMERA_TRACKER_OUI.get(_oui(mac))
        if vendor:
            hits.append({
                "mac": mac,
                "vendor_guess": vendor,
                "rssi": d.get("rssi"),
                "label": d.get("ssid") or d.get("name") or "",
                "note": "Possible camera/tracker nearby by vendor prefix (heuristic).",
            })
    return hits


def scan_report(wifi: list[dict], ble: list[dict]) -> dict:
    twins = evil_twin_candidates(wifi)
    devices = fingerprint_devices(wifi, ble)
    return {
        "evil_twin_candidates": twins,
        "flagged_devices": devices,
        "clear": not twins and not devices,
    }
