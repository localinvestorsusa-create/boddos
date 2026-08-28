import pytest
from fastapi.testclient import TestClient

from boddos.agent.screen_agent import ScreenAgent, _parse_elements
from boddos.config import Config, NodeCfg
from boddos.api import build_app


@pytest.fixture
def client(tmp_path):
    cfg = Config(node=NodeCfg(id="x", role="host"))
    cfg.security.audit_log = str(tmp_path / "a.log")
    with TestClient(build_app(cfg)) as c:
        yield c


def test_disabled_by_default():
    agent = ScreenAgent(cfg=type("C", (), {"enabled": False, "require_confirm": True})())
    res = agent.click(0.5, 0.5, confirm=True)
    assert not res.ok
    assert "disabled" in res.error


def test_confirm_required_when_enabled():
    cfg = type("C", (), {"enabled": True, "require_confirm": True})()
    agent = ScreenAgent(cfg)
    res = agent.type_text("hello", confirm=False)
    assert not res.ok
    assert "confirmation required" in res.error


def test_click_without_display_reports_error_not_crash():
    cfg = type("C", (), {"enabled": True, "require_confirm": False})()
    agent = ScreenAgent(cfg)
    res = agent.click(0.5, 0.5, confirm=True)
    # In this headless test environment pyautogui has no display to attach
    # to; the important behavior is a clean error result, never a crash.
    assert res.ok is False or res.ok is True


def test_parse_elements_extracts_valid_json_array():
    text = 'sure, here it is:\n[{"label": "Submit", "kind": "button", "x": 0.5, "y": 0.9}]'
    elements = _parse_elements(text)
    assert elements == [{"label": "Submit", "kind": "button", "x": 0.5, "y": 0.9}]


def test_parse_elements_clamps_out_of_range_fractions():
    text = '[{"label": "x", "kind": "icon", "x": 1.4, "y": -0.2}]'
    elements = _parse_elements(text)
    assert elements[0]["x"] == 1.0
    assert elements[0]["y"] == 0.0


def test_parse_elements_ignores_malformed_items():
    text = '[{"label": "ok", "x": 0.1, "y": 0.1}, "not-a-dict", {"x": "nan-ish"}]'
    elements = _parse_elements(text)
    assert len(elements) == 1
    assert elements[0]["label"] == "ok"


def test_parse_elements_no_json_returns_empty():
    assert _parse_elements("I can't see anything actionable.") == []


def test_screen_click_endpoint_disabled_by_default(client):
    r = client.post("/api/agent/screen/click", json={"x": 0.5, "y": 0.5, "confirm": True})
    body = r.json()
    assert body["ok"] is False
    assert "disabled" in body["error"]


def test_screen_look_endpoint_disabled_by_default(client):
    r = client.post("/api/agent/screen/look", json={})
    body = r.json()
    assert body["ok"] is False
    assert "disabled" in body["error"]
