"""Defensive personal-safety modules.

These protect the operator: panic/duress alerting, detecting whether YOU are
being followed by a rogue tracker, and auditing YOUR OWN public exposure.
They are not tools for surveilling other people.
"""
from .duress import DuressManager
from .trackers import TrackerDetector
from .exposure import ExposureAudit

__all__ = ["DuressManager", "TrackerDetector", "ExposureAudit"]
