"""The "click connect on both machines" pairing flow: a short one-time
code issued by the host node, redeemed by the joining node's own backend
against a REAL second node over a real socket — not two TestClients
talking to themselves, since the whole point is proving two independent
processes can actually reach and trust each other this way."""
import asyncio
import socket
import threading
import time

import httpx
import pytest
import uvicorn
from fastapi.testclient import TestClient

from boddos.api import build_app
from boddos.config import Config, NodeCfg


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _LiveServer(threading.Thread):
    """A real uvicorn server on a real port, running in a background
    thread — what a second physical machine would actually be."""

    def __init__(self, app, port: int):
        super().__init__(daemon=True)
        self.port = port
        # 0.0.0.0, matching this project's own default bind_host — a real
        # node is reachable at its LAN IP, not just localhost, and the
        # pairing flow returns that LAN IP as peer_url.
        self._config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="error")
        self.server = uvicorn.Server(self._config)

    def run(self):
        asyncio.run(self.server.serve())

    def wait_ready(self, timeout_s: float = 5.0) -> None:
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            try:
                httpx.get(f"http://127.0.0.1:{self.port}/health", timeout=0.3)
                return
            except Exception:
                time.sleep(0.05)
        raise RuntimeError("live server never came up")

    def stop(self) -> None:
        self.server.should_exit = True
        self.join(timeout=3)


@pytest.fixture
def live_host(tmp_path):
    """A real second node, reachable over a real socket — plays the role
    of "the other machine" in the pairing flow."""
    port = _free_port()
    cfg = Config(node=NodeCfg(id="host-node", name="Host", role="host", bind_port=port))
    cfg.mesh.psk = "host-original-psk"
    cfg.security.audit_log = str(tmp_path / "host_audit.log")
    app = build_app(cfg)
    server = _LiveServer(app, port)
    server.start()
    server.wait_ready()
    yield app.state.node, f"http://127.0.0.1:{port}"
    server.stop()


@pytest.fixture
def joiner_client(tmp_path):
    cfg = Config(node=NodeCfg(id="joiner-node", name="Joiner", role="edge"))
    cfg.mesh.psk = "joiner-original-psk"
    cfg.security.audit_log = str(tmp_path / "joiner_audit.log")
    app = build_app(cfg)
    with TestClient(app) as c:
        yield c, app.state.node


def test_pair_start_returns_code_and_address(joiner_client):
    client, _ = joiner_client
    r = client.post("/api/mesh/pair/start")
    body = r.json()
    assert r.status_code == 200
    assert len(body["code"]) == 6 and body["code"].isdigit()
    assert body["my_url"]
    assert body["my_name"] == "Joiner"
    assert body["expires_in_s"] > 0


def test_pair_claim_rejects_unknown_code(joiner_client):
    client, _ = joiner_client
    r = client.post("/api/mesh/pair/claim", json={"code": "000000"})
    assert r.status_code == 404
    assert r.json()["ok"] is False


def test_pair_claim_is_one_time_use(joiner_client):
    client, _ = joiner_client
    code = client.post("/api/mesh/pair/start").json()["code"]
    first = client.post("/api/mesh/pair/claim", json={"code": code})
    assert first.json()["ok"] is True
    second = client.post("/api/mesh/pair/claim", json={"code": code})
    assert second.status_code == 404


def test_pair_redeem_end_to_end_between_two_real_nodes(live_host, joiner_client):
    """The real flow: host generates a code, joiner enters the host's
    address + code and clicks connect, both nodes end up sharing a PSK and
    knowing about each other — no manual YAML editing."""
    host_state, host_url = live_host
    client, joiner_state = joiner_client

    start = httpx.post(f"{host_url}/api/mesh/pair/start", timeout=5.0)
    code = start.json()["code"]

    r = client.post("/api/mesh/pair/redeem", json={"host_url": host_url, "code": code})
    body = r.json()
    assert body["ok"] is True, body
    assert body["connected_to"] == "Host"

    # the joiner adopted the host's PSK and added it as a peer — using the
    # host's own self-reported (LAN IP) address, not necessarily the exact
    # host_url string the joiner dialed to get there
    assert joiner_state.cfg.mesh.psk == "host-original-psk"
    reported_peer_url = body["peer_url"]
    assert reported_peer_url in joiner_state.cfg.mesh.peers

    # _greet fired immediately — the host's registry already knows the
    # joiner, without waiting for a heartbeat cycle
    nodes = httpx.get(f"{host_url}/mesh/nodes", timeout=5.0).json()["nodes"]
    assert any(n["id"] == "joiner-node" for n in nodes)


def test_pair_redeem_rejects_wrong_code(live_host, joiner_client):
    _, host_url = live_host
    client, joiner_state = joiner_client
    original_psk = joiner_state.cfg.mesh.psk

    r = client.post("/api/mesh/pair/redeem", json={"host_url": host_url, "code": "999999"})
    body = r.json()
    assert body["ok"] is False
    assert "rejected the code" in body["error"]
    # a failed redeem must never mutate this node's mesh config
    assert joiner_state.cfg.mesh.psk == original_psk


def test_pair_redeem_reports_unreachable_host_cleanly(joiner_client):
    client, _ = joiner_client
    r = client.post("/api/mesh/pair/redeem", json={"host_url": "http://127.0.0.1:1", "code": "123456"})
    body = r.json()
    assert body["ok"] is False
    assert "couldn't reach" in body["error"]


def test_pair_redeem_requires_both_fields(joiner_client):
    client, _ = joiner_client
    assert client.post("/api/mesh/pair/redeem", json={}).json()["ok"] is False
    assert client.post("/api/mesh/pair/redeem", json={"code": "123456"}).json()["ok"] is False
