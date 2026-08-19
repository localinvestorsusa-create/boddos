import json

import pytest
from fastapi.testclient import TestClient

from boddos.config import Config, NodeCfg
from boddos.api import build_app
from boddos.security import MeshAuth


@pytest.fixture
def client(tmp_path):
    cfg = Config(node=NodeCfg(id="test", role="host", bind_port=8790))
    cfg.mesh.psk = "secret"
    cfg.agent.enabled = True
    cfg.agent.allowed_commands = ["echo"]
    cfg.agent.require_confirm = False
    cfg.security.audit_log = str(tmp_path / "audit.log")
    app = build_app(cfg)
    with TestClient(app) as c:
        yield c


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["node"] == "test"


def test_mesh_rejects_unsigned(client):
    assert client.post("/mesh/hello", json={"id": "x"}).status_code == 401


def test_mesh_accepts_signed(client):
    auth = MeshAuth("secret")
    payload = {"id": "peer", "role": "host", "url": "http://p"}
    body = json.dumps(payload).encode()
    r = client.post("/mesh/hello", content=body, headers=auth.sign(body))
    assert r.status_code == 200


def test_mesh_rejects_replay(client):
    auth = MeshAuth("secret")
    body = json.dumps({"id": "peer", "role": "host", "url": "http://p"}).encode()
    headers = auth.sign(body)
    assert client.post("/mesh/hello", content=body, headers=headers).status_code == 200
    # Same nonce/signature again -> replay rejected.
    assert client.post("/mesh/hello", content=body, headers=headers).status_code == 401


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


def test_deadman_arm_and_checkin(client):
    a = client.post("/api/safety/deadman/arm",
                    json={"label": "walk", "minutes": 30}).json()
    assert a["ok"] and a["label"] == "walk"
    st = client.get("/api/safety/deadman").json()
    assert any(c["label"] == "walk" for c in st["checkins"])
    assert client.post("/api/safety/deadman/checkin", json={"label": "walk"}).json()["ok"]


def test_surveillance_report_from_ingest(client):
    client.post("/api/sensors/ingest", json={
        "source": "esp32",
        "wifi": [{"bssid": "AA:AA:AA:00:00:01", "ssid": "CoffeeWiFi", "rssi": -40},
                 {"bssid": "BB:BB:BB:00:00:02", "ssid": "CoffeeWiFi", "rssi": -55}],
        "ble": [],
    })
    rep = client.get("/api/safety/surveillance").json()
    assert rep["clear"] is False
    assert rep["evil_twin_candidates"][0]["ssid"] == "CoffeeWiFi"


def test_security_status_and_audit_chain(client):
    # generate an auditable action
    client.post("/api/agent/run", json={"command": "echo hi"})
    s = client.get("/api/security/status").json()
    assert s["mesh_signing"] is True
    assert s["audit"]["intact"] is True
    assert s["audit"]["entries"] >= 1


def test_client_auth_enforced(tmp_path):
    cfg = Config(node=NodeCfg(id="auth", role="host"))
    cfg.security.require_auth = True
    cfg.security.api_token = "tok123"
    cfg.security.audit_log = str(tmp_path / "a.log")
    app = build_app(cfg)
    with TestClient(app) as c:
        assert c.get("/api/models").status_code == 401
        ok = c.get("/api/models", headers={"Authorization": "Bearer tok123"})
        assert ok.status_code == 200
        # health stays open so the UI can boot and prompt for the token
        assert c.get("/health").status_code == 200
