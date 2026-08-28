"""The voice/chat tool registry — every entry should be a real, callable
wrapper around an existing subsystem, with a valid Ollama tool schema."""
import pytest
from fastapi.testclient import TestClient

from boddos.api import build_app
from boddos.config import Config, NodeCfg


@pytest.fixture
def app_and_tools(tmp_path):
    cfg = Config(node=NodeCfg(id="x", role="host"))
    cfg.security.audit_log = str(tmp_path / "a.log")
    cfg.skills.workdir = str(tmp_path / "workspace_skills")
    app = build_app(cfg)
    with TestClient(app):
        yield app, app.state.node.tools


EXPECTED_TOOLS = {
    "run_skill", "list_skills",
    "build_3d_model", "check_combustion", "simulate_circuit", "simulate_beam",
    "simulate_rocket_flight", "analyze_sequence", "run_molecular_dynamics", "lookup_material",
    "get_directions",
    "scan_for_devices", "track_device", "stop_tracking_device", "device_tracking_status",
    "list_mesh_nodes",
    "get_weather", "translate_to_english",
    "drone_command", "place_call",
    "run_shell_command", "fetch_web_page",
    "look_at_screen", "drive_screen",
}


def test_every_expected_tool_is_registered(app_and_tools):
    _, tools = app_and_tools
    assert EXPECTED_TOOLS <= set(tools.keys())


def test_every_tool_has_a_valid_ollama_schema(app_and_tools):
    _, tools = app_and_tools
    for name, spec in tools.items():
        schema = spec.to_ollama_tool()
        assert schema["type"] == "function"
        fn = schema["function"]
        assert fn["name"] == name
        assert fn["description"]
        assert fn["parameters"]["type"] == "object"
        for req in spec.required:
            assert req in fn["parameters"]["properties"], f"{name}: required '{req}' not in properties"


async def test_run_skill_tool_reports_missing_skill(app_and_tools):
    _, tools = app_and_tools
    result = await tools["run_skill"].fn(slug="does-not-exist", inputs={})
    assert result["ok"] is False
    assert "no such skill" in result["error"]


async def test_list_skills_tool_returns_empty_list_initially(app_and_tools):
    _, tools = app_and_tools
    result = await tools["list_skills"].fn()
    assert result == {"skills": []}


async def test_get_weather_tool_respects_disabled_config(tmp_path):
    cfg = Config(node=NodeCfg(id="x", role="host"))
    cfg.security.audit_log = str(tmp_path / "a.log")
    cfg.services.weather.enabled = False
    app = build_app(cfg)
    with TestClient(app):
        result = await app.state.node.tools["get_weather"].fn()
    assert result == {"ok": False, "error": "weather disabled"}


async def test_look_at_screen_tool_disabled_by_default(app_and_tools):
    _, tools = app_and_tools
    result = await tools["look_at_screen"].fn()
    assert result["ok"] is False
    assert "disabled" in result["error"]


async def test_drive_screen_tool_disabled_by_default(app_and_tools):
    _, tools = app_and_tools
    result = await tools["drive_screen"].fn(goal="open settings")
    assert result["ok"] is False
    assert "disabled" in result["error"]


async def test_run_shell_command_tool_respects_agent_disabled(app_and_tools):
    _, tools = app_and_tools
    result = await tools["run_shell_command"].fn(command="echo hi")
    assert result["ok"] is False
    assert "disabled" in result["error"]


async def test_get_directions_tool_requires_routing_enabled(tmp_path):
    cfg = Config(node=NodeCfg(id="x", role="host"))
    cfg.security.audit_log = str(tmp_path / "a.log")
    cfg.services.routing.enabled = False
    app = build_app(cfg)
    with TestClient(app):
        result = await app.state.node.tools["get_directions"].fn(
            from_lat=40.0, from_lon=-74.0, destination="nowhere",
        )
    assert result == {"ok": False, "error": "routing disabled"}


async def test_scan_for_devices_tool_respects_finder_disabled(tmp_path):
    cfg = Config(node=NodeCfg(id="x", role="host"))
    cfg.security.audit_log = str(tmp_path / "a.log")
    cfg.services.finder.enabled = False
    app = build_app(cfg)
    with TestClient(app):
        result = await app.state.node.tools["scan_for_devices"].fn()
    assert result["ok"] is False
    assert "disabled" in result["error"]


async def test_run_skill_tool_executes_a_real_saved_skill(tmp_path):
    cfg = Config(node=NodeCfg(id="x", role="host"))
    cfg.security.audit_log = str(tmp_path / "a.log")
    cfg.skills.workdir = str(tmp_path / "workspace_skills")
    app = build_app(cfg)
    with TestClient(app):
        state = app.state.node
        script = (
            "import json, sys\n"
            "args = json.loads(sys.argv[1])\n"
            "print(json.dumps({'doubled': int(args['n']) * 2}))\n"
        )
        manifest = {"skill_id": "doubler", "label": "Doubler",
                    "inputs": [{"name": "n", "label": "Number", "type": "number"}]}
        record, err = await state.skills.save(script, manifest, confirm=True)
        assert record is not None, err

        result = await state.tools["run_skill"].fn(slug="doubler", inputs={"n": 21})
    assert result["ok"] is True
    assert '"doubled": 42' in result["stdout"]
