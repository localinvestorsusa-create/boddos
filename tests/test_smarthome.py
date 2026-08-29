import pytest
from fastapi.testclient import TestClient

from boddos.api import build_app
from boddos.config import Config, NodeCfg
from boddos.services.smarthome import SmartHomeManager


def cfg_with(**overrides):
    cfg = Config(node=NodeCfg(id="x", role="host"))
    for k, v in overrides.items():
        setattr(cfg.services.smarthome, k, v)
    return cfg


async def test_disabled_reports_disabled():
    mgr = SmartHomeManager(cfg_with(enabled=False).services.smarthome)
    res = await mgr.discover()
    assert not res.ok
    assert "disabled" in res.error


async def test_discover_reports_ok_with_no_devices_on_this_sandbox():
    # No real Kasa hardware in CI/sandbox — discovery should still complete
    # cleanly (an empty network scan), never raise.
    mgr = SmartHomeManager(cfg_with(discovery_timeout_s=0.5).services.smarthome)
    res = await mgr.discover()
    assert res.ok
    assert res.devices == []


async def test_control_unreachable_device_fails_cleanly():
    mgr = SmartHomeManager(cfg_with().services.smarthome)
    res = await mgr.turn_on("192.0.2.1")  # TEST-NET-1, guaranteed unreachable
    assert not res.ok
    assert res.error


@pytest.fixture
def client(tmp_path):
    cfg = Config(node=NodeCfg(id="test", role="host"))
    cfg.security.audit_log = str(tmp_path / "audit.log")
    with TestClient(build_app(cfg)) as c:
        yield c


def test_discover_endpoint(client):
    r = client.get("/api/smarthome/discover")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["devices"] == []


def test_control_endpoint_rejects_unknown_action(client):
    r = client.post("/api/smarthome/control", json={"ip": "192.0.2.1", "action": "explode"})
    assert r.status_code == 200
    assert r.json()["ok"] is False
