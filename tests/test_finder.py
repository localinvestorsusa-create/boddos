from dataclasses import dataclass
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from boddos.api import build_app
from boddos.config import Config, NodeCfg
from boddos.services.finder import DeviceFinder, _compute_trend, _proximity_label


@pytest.fixture
def client(tmp_path):
    cfg = Config(node=NodeCfg(id="x", role="host"))
    cfg.security.audit_log = str(tmp_path / "a.log")
    with TestClient(build_app(cfg)) as c:
        yield c


# ------------------------- pure proximity logic -------------------------

def test_proximity_label_bands():
    assert _proximity_label(-40) == "very close"
    assert _proximity_label(-60) == "nearby"
    assert _proximity_label(-80) == "far"
    assert _proximity_label(-95) == "very far"


def test_trend_needs_enough_samples():
    assert _compute_trend([(0, -60), (1, -60)]) == "reading…"


def test_trend_detects_approach():
    # Signal strengthening over time (less negative) means getting closer.
    samples = [(0, -80), (1, -78), (2, -60), (3, -55)]
    assert _compute_trend(samples) == "getting warmer"


def test_trend_detects_retreat():
    samples = [(0, -50), (1, -52), (2, -70), (3, -75)]
    assert _compute_trend(samples) == "getting colder"


def test_trend_steady_signal():
    samples = [(0, -60), (1, -61), (2, -59), (3, -60)]
    assert _compute_trend(samples) == "steady"


# --------------------- scan/track against a fake Bleak ------------------
# Bleak's real API shape (verified against the installed version):
#   BleakScanner.discover(timeout, return_adv=True) ->
#       dict[address, tuple[BLEDevice(address, name), AdvertisementData(rssi, ...)]]
#   BleakScanner(detection_callback=...).start()/.stop()
#   detection_callback(device, advertisement_data)

@dataclass
class FakeDevice:
    address: str
    name: str | None


@dataclass
class FakeAdv:
    rssi: float


async def test_scan_parses_real_bleak_return_shape():
    finder = DeviceFinder()
    fake_result = {
        "AA:BB:CC:DD:EE:01": (FakeDevice("AA:BB:CC:DD:EE:01", "Earbuds"), FakeAdv(-52)),
        "AA:BB:CC:DD:EE:02": (FakeDevice("AA:BB:CC:DD:EE:02", None), FakeAdv(-88)),
    }
    with patch("boddos.services.finder.BleakScanner") as mock_scanner:
        mock_scanner.discover = AsyncMock(return_value=fake_result)
        result = await finder.scan(seconds=1.0)

    assert result.ok
    assert len(result.devices) == 2
    # Sorted strongest signal first.
    assert result.devices[0]["address"] == "AA:BB:CC:DD:EE:01"
    assert result.devices[0]["name"] == "Earbuds"
    assert result.devices[1]["name"] == "(unnamed)"


async def test_scan_reports_hardware_failure_cleanly():
    finder = DeviceFinder()
    with patch("boddos.services.finder.BleakScanner") as mock_scanner:
        mock_scanner.discover = AsyncMock(side_effect=FileNotFoundError("no bluetooth adapter"))
        result = await finder.scan()
    assert not result.ok
    assert "BLE scan unavailable" in result.error


async def test_track_accumulates_matching_detections_and_ignores_others():
    finder = DeviceFinder()
    with patch("boddos.services.finder.BleakScanner") as mock_scanner_cls:
        instance = mock_scanner_cls.return_value
        instance.start = AsyncMock()
        instance.stop = AsyncMock()
        status = await finder.start("AA:BB:CC:DD:EE:01", name="Earbuds")
        assert status.ok and status.tracking

        # Simulate detection callbacks the way Bleak would fire them.
        finder._on_detection(FakeDevice("AA:BB:CC:DD:EE:01", "Earbuds"), FakeAdv(-70))
        finder._on_detection(FakeDevice("some-other-device", "Speaker"), FakeAdv(-30))
        finder._on_detection(FakeDevice("AA:BB:CC:DD:EE:01", "Earbuds"), FakeAdv(-55))

        status = finder.status()
        assert status.tracking
        assert status.rssi == -55  # latest sample for the tracked device only
        assert status.proximity == "very close"

        stopped = await finder.stop()
        assert stopped.tracking is False


async def test_status_when_never_started():
    finder = DeviceFinder()
    status = finder.status()
    assert status.ok
    assert status.tracking is False


# ------------------------------ API layer --------------------------------

def test_finder_scan_endpoint_fails_cleanly_without_hardware(client):
    # Real call against this sandbox: no BlueZ/D-Bus, no adapter — must
    # fail cleanly, not crash the request.
    r = client.post("/api/finder/scan", json={"seconds": 1})
    body = r.json()
    assert body["ok"] is False
    assert body["devices"] == []


def test_finder_track_requires_address(client):
    r = client.post("/api/finder/track", json={})
    assert r.json()["ok"] is False


def test_finder_status_idle_by_default(client):
    r = client.get("/api/finder/status")
    body = r.json()
    assert body["ok"] is True
    assert body["tracking"] is False
