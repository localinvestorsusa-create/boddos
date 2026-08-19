import json

import pytest
from fastapi.testclient import TestClient

from boddos.config import Config, NodeCfg
from boddos.api import build_app
from boddos.sensors.cameras import CameraRegistry
from boddos.services.push import PushManager


@pytest.fixture
def client(tmp_path):
    cfg = Config(node=NodeCfg(id="x", role="host"))
    cfg.security.audit_log = str(tmp_path / "a.log")
    with TestClient(build_app(cfg)) as c:
        yield c


def test_camera_registry_crud():
    reg = CameraRegistry()
    reg.add("front", "http://cam/snap.jpg", "snapshot")
    assert [c["name"] for c in reg.list()] == ["front"]
    assert reg.get("front").url == "http://cam/snap.jpg"
    assert reg.remove("front") and reg.list() == []


def test_camera_endpoints(client):
    r = client.post("/api/cameras", json={"name": "door", "url": "http://c/s.jpg"}).json()
    assert r["ok"] and r["camera"]["kind"] == "snapshot"
    assert any(c["name"] == "door" for c in client.get("/api/cameras").json()["cameras"])
    assert client.delete("/api/cameras/door").json()["ok"] is True


def test_camera_add_requires_fields(client):
    assert client.post("/api/cameras", json={"name": "x"}).json()["ok"] is False


def test_push_store_roundtrip(tmp_path):
    pm = PushManager("", "", "mailto:a@b", str(tmp_path / "subs.json"))
    assert pm.subscribe({"endpoint": "https://push/1"})["ok"] is True
    assert pm.count() == 1
    # Persisted to disk.
    pm2 = PushManager("", "", "mailto:a@b", str(tmp_path / "subs.json"))
    assert pm2.count() == 1
    assert pm2.unsubscribe("https://push/1")["ok"] is True
    assert pm2.count() == 0


def test_push_disabled_without_keys(tmp_path):
    pm = PushManager("", "", "", str(tmp_path / "s.json"))
    assert pm.enabled is False
    assert pm.notify_all("t", "b")[0]["ok"] is False


def test_vision_endpoint(client):
    # No Ollama in CI: provider returns a graceful string, endpoint still ok.
    r = client.post("/api/vision", json={"image_b64": "AAAA", "prompt": "what?"}).json()
    assert r["ok"] is True and isinstance(r["analysis"], str)


def test_vision_requires_image(client):
    assert client.post("/api/vision", json={"prompt": "x"}).json()["ok"] is False


def test_chat_stream_emits_done(client):
    r = client.post("/api/chat/stream", json={"prompt": "hi"})
    assert r.status_code == 200
    assert '"done"' in r.text


def test_models_pull_streams(client):
    r = client.post("/api/models/pull", json={"model": "tinyllama"})
    assert r.status_code == 200 and '"done"' in r.text


def test_push_endpoints_when_disabled(client):
    assert client.get("/api/push/publickey").json()["enabled"] is False
    assert client.post("/api/push/subscribe", json={"subscription": {}}).json()["ok"] is False
