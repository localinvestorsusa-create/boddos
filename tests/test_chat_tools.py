"""The agentic tool-calling loop behind /api/chat/stream: the model can call
one or several registered tools, get results fed back, and keep going
before answering — this is what makes "everything voice-controlled" work
without a manual button for each action."""
import json

import pytest
from fastapi.testclient import TestClient

from boddos.api import build_app
from boddos.config import Config, NodeCfg


class FakeToolProvider:
    """Scripted stand-in for OllamaProvider — returns each queued message in
    order from chat_with_tools, and records every round's message list so
    tests can assert what the loop fed back after each tool result."""

    def __init__(self, rounds):
        self.rounds = list(rounds)
        self.seen_rounds: list[list[dict]] = []
        self.chat_stream_called = False

    async def chat_with_tools(self, model, messages, tools):
        self.seen_rounds.append([dict(m) for m in messages])
        return self.rounds.pop(0)

    async def chat_stream(self, model, messages, images=None):
        self.chat_stream_called = True
        yield "[fake plain-text reply, tools were skipped]"


def _tool_call_message(*calls: tuple[str, dict]) -> dict:
    return {
        "role": "assistant",
        "content": "",
        "tool_calls": [{"function": {"name": name, "arguments": args}} for name, args in calls],
    }


def _final_message(content: str) -> dict:
    return {"role": "assistant", "content": content}


def parse_sse(text: str) -> list[dict]:
    events = []
    for block in text.strip().split("\n\n"):
        block = block.strip()
        if not block:
            continue
        payload = block[len("data:"):].strip() if block.startswith("data:") else block
        if payload:
            events.append(json.loads(payload))
    return events


@pytest.fixture
def app(tmp_path):
    cfg = Config(node=NodeCfg(id="x", role="host"))
    cfg.security.audit_log = str(tmp_path / "a.log")
    cfg.skills.workdir = str(tmp_path / "workspace_skills")
    a = build_app(cfg)
    with TestClient(a):
        yield a


def test_single_tool_call_then_answer(app):
    app.state.node.provider = FakeToolProvider([
        _tool_call_message(("list_skills", {})),
        _final_message("You have no skills saved yet."),
    ])
    client = TestClient(app)
    r = client.post("/api/chat/stream", json={"messages": [{"role": "user", "content": "what skills do I have?"}]})
    events = parse_sse(r.text)

    tool_calls = [e["tool_call"] for e in events if "tool_call" in e]
    tool_results = [e["tool_result"] for e in events if "tool_result" in e]
    text = "".join(e["t"] for e in events if "t" in e)

    assert tool_calls == [{"name": "list_skills", "args": {}}]
    assert tool_results == [{"name": "list_skills", "ok": True}]
    assert text == "You have no skills saved yet."
    assert events[-1] == {"done": True, "served_by": "x"}


def test_multiple_tool_calls_in_one_round_run_together(app):
    """'One action leads to multiple reactions': the model can ask for two
    tools in a single round, and both should execute and report back before
    the next round runs — matching the app's chained/parallel tool-calling
    behavior."""
    app.state.node.provider = FakeToolProvider([
        _tool_call_message(("list_skills", {}), ("list_mesh_nodes", {})),
        _final_message("No skills yet, and this is the only node in the mesh."),
    ])
    client = TestClient(app)
    r = client.post("/api/chat/stream", json={"messages": [{"role": "user", "content": "status check"}]})
    events = parse_sse(r.text)

    tool_calls = {e["tool_call"]["name"] for e in events if "tool_call" in e}
    tool_results = {e["tool_result"]["name"] for e in events if "tool_result" in e}
    assert tool_calls == {"list_skills", "list_mesh_nodes"}
    assert tool_results == {"list_skills", "list_mesh_nodes"}

    # both tool results were fed back before the model's final round ran
    assert len(app.state.node.provider.seen_rounds) == 2
    final_round = app.state.node.provider.seen_rounds[1]
    tool_msgs = [m for m in final_round if m.get("role") == "tool"]
    assert {m["name"] for m in tool_msgs} == {"list_skills", "list_mesh_nodes"}


def test_unknown_tool_call_reports_error_without_crashing(app):
    app.state.node.provider = FakeToolProvider([
        _tool_call_message(("teleport_user", {})),
        _final_message("I can't do that, but here's what I can do instead."),
    ])
    client = TestClient(app)
    r = client.post("/api/chat/stream", json={"messages": [{"role": "user", "content": "teleport me"}]})
    events = parse_sse(r.text)
    tool_results = [e["tool_result"] for e in events if "tool_result" in e]
    assert tool_results == [{"name": "teleport_user", "ok": False}]
    text = "".join(e["t"] for e in events if "t" in e)
    assert "here's what I can do instead" in text


def test_tool_round_cap_stops_an_infinite_loop(app):
    provider = FakeToolProvider([_tool_call_message(("list_skills", {})) for _ in range(10)])
    app.state.node.provider = provider
    client = TestClient(app)
    r = client.post("/api/chat/stream", json={"messages": [{"role": "user", "content": "loop forever"}]})
    events = parse_sse(r.text)
    text = "".join(e["t"] for e in events if "t" in e)
    assert "tool-call limit" in text
    # capped at MAX_TOOL_ROUNDS (6) rounds, not all 10 queued replies consumed
    assert len(provider.seen_rounds) == 6


def test_forwarded_request_skips_tool_calling(app):
    provider = FakeToolProvider([_tool_call_message(("list_skills", {}))])
    app.state.node.provider = provider
    client = TestClient(app)
    r = client.post(
        "/api/chat/stream",
        json={"messages": [{"role": "user", "content": "hi"}]},
        headers={"X-Boddos-Forwarded": "1"},
    )
    assert r.status_code == 200
    assert provider.chat_stream_called is True
    assert provider.seen_rounds == []


def test_tools_false_flag_skips_tool_calling(app):
    provider = FakeToolProvider([_tool_call_message(("list_skills", {}))])
    app.state.node.provider = provider
    client = TestClient(app)
    r = client.post(
        "/api/chat/stream",
        json={"messages": [{"role": "user", "content": "hi"}], "tools": False},
    )
    assert r.status_code == 200
    assert provider.chat_stream_called is True
    assert provider.seen_rounds == []
