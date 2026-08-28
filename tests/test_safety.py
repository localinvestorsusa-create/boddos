import time

from boddos.config import SafetyCfg, TrustedContact
from boddos.safety.trackers import TrackerDetector
from boddos.safety.duress import DuressManager
from boddos.safety.exposure import classify_identifier


def test_tracker_flags_follower_across_locations():
    det = TrackerDetector(follow_threshold=3, min_span_s=0)
    for lat in (40.71, 40.75, 40.80):
        det.observe([{"mac": "AA:BB", "name": "Tag"}], lat=lat, lon=-74.0)
    sus = det.suspects()
    assert len(sus) == 1
    assert sus[0]["mac"] == "AA:BB"
    assert sus[0]["distinct_locations"] == 3


def test_tracker_ignores_single_place_device():
    det = TrackerDetector(follow_threshold=3, min_span_s=0)
    for _ in range(5):
        det.observe([{"mac": "CC:DD"}], lat=40.71, lon=-74.0)
    assert det.suspects() == []


def test_duress_queues_contacts_and_event():
    cfg = SafetyCfg(trusted_contacts=[TrustedContact(name="Alex", channel="sms", target="+1")])
    dm = DuressManager(cfg)
    res = dm.trigger(note="help", location={"lat": 1.0, "lon": 2.0})
    assert res["ok"] and res["state"] == "duress"
    assert len(res["alerts"]) == 1
    assert "maps.google.com" in res["alerts"][0]["body"]
    assert dm.snapshot()["active"] is True
    dm.clear()
    assert dm.snapshot()["active"] is False


def test_classify_identifier():
    assert classify_identifier("me@example.com") == "email"
    assert classify_identifier("+1 555 123 4567") == "phone"
    assert classify_identifier("https://site.tld/me") == "url"
    assert classify_identifier("John Q Public") == "name"
    assert classify_identifier("handle123") == "username"
