from fastapi.testclient import TestClient

from boddos.api import build_app
from boddos.config import Config, NodeCfg


def test_health():
    cfg = Config(node=NodeCfg(id="test"))
    with TestClient(build_app(cfg)) as c:
        r = c.get("/health")
    assert r.status_code == 200
    assert r.json() == {"ok": True, "node": "test"}
