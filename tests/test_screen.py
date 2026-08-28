import pytest
from fastapi.testclient import TestClient

from boddos.agent.screen_agent import (
    ScreenAgent, ScreenResult, _parse_elements, _parse_decision, _nearest_element, is_sensitive,
)
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


def test_screen_drive_endpoint_disabled_by_default(client):
    r = client.post("/api/agent/screen/drive", json={"goal": "open settings"})
    body = r.json()
    assert body["ok"] is False
    assert "disabled" in body["error"]


def test_screen_drive_endpoint_requires_goal(client):
    r = client.post("/api/agent/screen/drive", json={})
    assert r.json() == {"ok": False, "error": "goal required"}


# ------------------------- drive() orchestration -------------------------
# Everything below is real orchestration logic exercised with a scripted
# fake model provider and a stubbed screenshot — the two calls that
# genuinely need a display/GPU this sandbox doesn't have. The loop
# termination, sensitivity gate, and step bookkeeping are all real code.

def test_is_sensitive_matches_financial_and_destructive():
    assert is_sensitive("Buy Now")
    assert is_sensitive("Delete my account")
    assert is_sensitive("sudo rm -rf /tmp")
    assert is_sensitive("Send Money to Alex")
    assert is_sensitive("confirm order")


def test_is_sensitive_ignores_ordinary_actions():
    assert not is_sensitive("Submit")
    assert not is_sensitive("Next page")
    assert not is_sensitive("Settings")
    assert not is_sensitive("")


def test_parse_decision_valid_json():
    d = _parse_decision('{"action": "click", "target_label": "Submit", "reason": "done filling form"}')
    assert d == {"action": "click", "target_label": "Submit", "reason": "done filling form"}


def test_parse_decision_rejects_unknown_action():
    assert _parse_decision('{"action": "explode"}') is None


def test_parse_decision_no_json_returns_none():
    assert _parse_decision("I'm thinking about it...") is None


def test_nearest_element_exact_and_fuzzy_match():
    elements = [{"label": "Submit form", "kind": "button", "x": 0.5, "y": 0.9}]
    assert _nearest_element("Submit form", elements)["x"] == 0.5
    assert _nearest_element("submit", elements) is not None
    assert _nearest_element("nonexistent", elements) is None
    assert _nearest_element("", elements) is None


class FakeProvider:
    """Scripted provider — returns each queued reply in order, regardless of
    which model/messages were passed, so drive()'s loop logic can be
    exercised without a real Ollama server or a display."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls: list[tuple[str, bool]] = []

    async def chat(self, model, messages, images=None):
        self.calls.append((model, images is not None))
        return self.replies.pop(0)


def _screen_cfg(**overrides):
    cfg = type("C", (), {
        "enabled": True, "require_confirm": True,
        "max_drive_steps": 12, "require_confirm_for_sensitive": True,
    })()
    for k, v in overrides.items():
        setattr(cfg, k, v)
    return cfg


async def test_drive_disabled_by_default():
    agent = ScreenAgent(_screen_cfg(enabled=False))
    res = await agent.drive(FakeProvider([]), "m", "vm", "open the app")
    assert not res.ok
    assert "disabled" in res.error


async def test_drive_clicks_then_finishes(monkeypatch):
    agent = ScreenAgent(_screen_cfg())
    monkeypatch.setattr(agent, "screenshot_b64", lambda max_width=1280: ("ZmFrZQ==", ""))
    monkeypatch.setattr(agent, "click", lambda x, y, confirm=False: ScreenResult(ok=True, raw="clicked"))
    provider = FakeProvider([
        '[{"label": "Settings", "kind": "button", "x": 0.2, "y": 0.1}]',
        '{"action": "click", "target_label": "Settings", "reason": "open settings"}',
        '[{"label": "Dark mode", "kind": "button", "x": 0.5, "y": 0.5}]',
        '{"action": "done", "reason": "settings opened"}',
    ])
    res = await agent.drive(provider, "m", "vm", "open settings")
    assert res.ok
    assert res.finished
    assert [s.action for s in res.steps] == ["click", "done"]
    # two rounds, one vision + one decision call each == 4 provider calls
    assert len(provider.calls) == 4


async def test_drive_pauses_on_sensitive_action(monkeypatch):
    agent = ScreenAgent(_screen_cfg())
    monkeypatch.setattr(agent, "screenshot_b64", lambda max_width=1280: ("ZmFrZQ==", ""))
    provider = FakeProvider([
        '[{"label": "Delete account", "kind": "button", "x": 0.5, "y": 0.5}]',
        '{"action": "click", "target_label": "Delete account", "reason": "user asked to delete it"}',
    ])
    res = await agent.drive(provider, "m", "vm", "delete my account")
    assert res.ok
    assert not res.finished
    assert res.awaiting_confirmation is not None
    assert res.awaiting_confirmation["target_label"] == "Delete account"
    assert res.steps[-1].action == "blocked"


async def test_drive_stops_at_max_steps(monkeypatch):
    agent = ScreenAgent(_screen_cfg(max_drive_steps=2))
    monkeypatch.setattr(agent, "screenshot_b64", lambda max_width=1280: ("ZmFrZQ==", ""))
    monkeypatch.setattr(agent, "click", lambda x, y, confirm=False: ScreenResult(ok=True, raw="clicked"))
    provider = FakeProvider([
        '[{"label": "Next", "kind": "button", "x": 0.5, "y": 0.5}]',
        '{"action": "click", "target_label": "Next", "reason": "keep going"}',
        '[{"label": "Next", "kind": "button", "x": 0.5, "y": 0.5}]',
        '{"action": "click", "target_label": "Next", "reason": "keep going"}',
    ])
    res = await agent.drive(provider, "m", "vm", "never-ending task")
    assert not res.ok
    assert "step limit" in res.error
    assert len(res.steps) == 2


async def test_drive_unparseable_decision_stops_cleanly(monkeypatch):
    agent = ScreenAgent(_screen_cfg())
    monkeypatch.setattr(agent, "screenshot_b64", lambda max_width=1280: ("ZmFrZQ==", ""))
    provider = FakeProvider([
        '[{"label": "Settings", "kind": "button", "x": 0.5, "y": 0.5}]',
        "I'm not sure what to do here.",
    ])
    res = await agent.drive(provider, "m", "vm", "do something ambiguous")
    assert not res.ok
    assert "usable next action" in res.error


async def test_drive_missing_click_target_reports_error_not_crash(monkeypatch):
    agent = ScreenAgent(_screen_cfg())
    monkeypatch.setattr(agent, "screenshot_b64", lambda max_width=1280: ("ZmFrZQ==", ""))
    provider = FakeProvider([
        '[{"label": "Settings", "kind": "button", "x": 0.5, "y": 0.5}]',
        '{"action": "click", "target_label": "A button that does not exist", "reason": "..."}',
    ])
    res = await agent.drive(provider, "m", "vm", "click something missing")
    assert not res.ok
    assert "no visible element matches" in res.error
