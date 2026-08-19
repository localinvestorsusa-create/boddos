import pytest
from fastapi.testclient import TestClient

from boddos.config import Config, NodeCfg
from boddos.api import build_app


@pytest.fixture
def client():
    cfg = Config(node=NodeCfg(id="test", role="host", bind_port=8790))
    cfg.mesh.psk = "secret"
    cfg.agent.enabled = True
    cfg.agent.allowed_commands = ["echo"]
    cfg.agent.require_confirm = False
    app = build_app(cfg)
    with TestClient(app) as c:
        yield c


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["node"] == "test"


def test_mesh_requires_psk(client):
    assert client.post("/mesh/hello", json={"id": "x"}).status_code == 401
    ok = client.post("/mesh/hello", json={"id": "peer", "role": "host", "url": "http://p"},
                     headers={"X-Boddos-PSK": "secret"})
    assert ok.status_code == 200


def test_sensors_ingest_and_snapshot(client):
    client.post("/api/sensors/ingest", json={
        "source": "esp32", "wifi": [{"bssid": "A", "rssi": -50}],
        "ble": [{"mac": "M", "rssi": -60}],
    })
    snap = client.get("/api/sensors").json()
    assert snap["sources"]["esp32"]["device_count"] == 2


def test_agent_allowlist_blocks_unlisted(client):
    r = client.post("/api/agent/run", json={"command": "rm -rf /"}).json()
    assert r["ok"] is False


def test_agent_runs_allowlisted(client):
    r = client.post("/api/agent/run", json={"command": "echo hello"}).json()
    assert r["ok"] is True and "hello" in r["stdout"]


def test_safety_duress_flow(client):
    r = client.post("/api/safety/duress", json={"note": "test"}).json()
    assert r["ok"] and r["state"] == "duress"
    assert client.post("/api/safety/clear").json()["state"] == "clear"
