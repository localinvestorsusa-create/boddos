"""Defensive personal-safety modules.

These protect the operator: panic/duress alerting, detecting whether YOU are
being followed by a rogue tracker, and auditing YOUR OWN public exposure.
They are not tools for surveilling other people.
"""
from .duress import DuressManager
from .trackers import TrackerDetector
from .exposure import ExposureAudit
from .deadman import DeadMansSwitch, CheckIn
from .surveillance import scan_report
from .breach import check_password
from .geofence import GeoFence, Zone

__all__ = [
    "DuressManager",
    "TrackerDetector",
    "ExposureAudit",
    "DeadMansSwitch",
    "CheckIn",
    "scan_report",
    "check_password",
    "GeoFence",
    "Zone",
]
