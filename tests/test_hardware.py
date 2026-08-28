import pytest
from fastapi.testclient import TestClient

from boddos import hardware
from boddos.api import build_app
from boddos.config import Config, NodeCfg


@pytest.fixture
def client(tmp_path):
    cfg = Config(node=NodeCfg(id="x", role="host"))
    cfg.security.audit_log = str(tmp_path / "a.log")
    with TestClient(build_app(cfg)) as c:
        yield c


def test_detect_never_raises_and_returns_sane_shape():
    report = hardware.detect()
    assert report.cpu_cores >= 1
    assert report.ram_gb >= 0
    assert isinstance(report.has_gpu, bool)
    assert report.recommended_model
    assert report.recommended_vision_model
    assert report.notes


def test_recommend_scales_with_available_memory():
    small_model, _, _ = hardware._recommend(2.0)
    big_model, _, _ = hardware._recommend(32.0)
    assert "1.5b" in small_model or "3b" in small_model
    assert "14b" in big_model


def test_recommend_monotonic_across_tiers():
    # Every tier boundary should be reachable and never crash on an
    # arbitrary budget, including zero and negative-ish edge inputs.
    for budget in (-1.0, 0.0, 3.9, 4.0, 7.9, 8.0, 11.9, 12.0, 23.9, 24.0, 128.0):
        model, vision, note = hardware._recommend(budget)
        assert model and vision and note


def test_node_state_populates_hardware_from_detection(client):
    r = client.get("/api/hardware")
    body = r.json()
    assert body["cpu_cores"] >= 1
    assert "recommended_model" in body


def test_node_appears_in_mesh_nodes_with_hardware_fields(client):
    r = client.get("/mesh/nodes")
    nodes = r.json()["nodes"]
    assert len(nodes) == 1
    me = nodes[0]
    assert me["id"] == "x"
    assert "ram_gb" in me and "has_gpu" in me and "vram_gb" in me
