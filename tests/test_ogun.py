import pytest
from fastapi.testclient import TestClient

from boddos.api import build_app
from boddos.config import Config, NodeCfg, OgunCfg
from boddos.ogun import CadStudio, ChemLab, CircuitLab


@pytest.fixture
def client(tmp_path):
    cfg = Config(node=NodeCfg(id="x", role="host"))
    cfg.security.audit_log = str(tmp_path / "a.log")
    cfg.ogun.workdir = str(tmp_path / "ogun")
    with TestClient(build_app(cfg)) as c:
        yield c


def ogun_cfg(tmp_path, **overrides) -> OgunCfg:
    cfg = OgunCfg(workdir=str(tmp_path / "ogun"))
    for k, v in overrides.items():
        setattr(cfg, k, v)
    return cfg


# ------------------------------- CAD --------------------------------

async def test_cad_builds_a_real_solid(tmp_path):
    studio = CadStudio(ogun_cfg(tmp_path))
    scad = "cube([10, 10, 10]);"
    result = await studio.build(scad)
    assert result.ok, result.log
    assert result.facets == 12  # a cube is 12 triangular facets
    assert result.stl_b64
    assert result.image_b64


async def test_cad_rejects_invalid_geometry(tmp_path):
    studio = CadStudio(ogun_cfg(tmp_path))
    result = await studio.build("this is not valid openscad syntax {{{")
    assert not result.ok
    assert result.error


async def test_cad_disabled_by_default_config(tmp_path):
    studio = CadStudio(ogun_cfg(tmp_path, enabled=False))
    result = await studio.build("cube(1);")
    assert not result.ok
    assert "disabled" in result.error


async def test_cad_rejects_oversized_source(tmp_path):
    studio = CadStudio(ogun_cfg(tmp_path, max_source_chars=10))
    result = await studio.build("cube([1,1,1]);")
    assert not result.ok
    assert "too long" in result.error


async def test_cad_rejects_empty_source(tmp_path):
    studio = CadStudio(ogun_cfg(tmp_path))
    result = await studio.build("   ")
    assert not result.ok


def test_ogun_model_endpoint(client):
    r = client.post("/api/ogun/model", json={"scad": "sphere(r=5, $fn=16);"})
    body = r.json()
    assert body["ok"] is True
    assert body["facets"] > 0


# ---------------------------- Chemistry ------------------------------

def test_combustion_methane_air_gives_realistic_flame_temp(tmp_path):
    lab = ChemLab(ogun_cfg(tmp_path))
    result = lab.combustion("CH4:1, O2:2, N2:7.52")
    assert result.ok, result.error
    # Stoichiometric methane/air adiabatic flame temperature is a
    # well-known real-world figure (~2200-2300K).
    assert 2000 < result.flame_temperature_k < 2500
    assert "CO2" in result.products or "H2O" in result.products


def test_combustion_rejects_garbage_mixture(tmp_path):
    lab = ChemLab(ogun_cfg(tmp_path))
    result = lab.combustion("NotARealSpecies:1")
    assert not result.ok


def test_combustion_disabled_by_default_config(tmp_path):
    lab = ChemLab(ogun_cfg(tmp_path, enabled=False))
    result = lab.combustion("CH4:1, O2:2")
    assert not result.ok
    assert "disabled" in result.error


def test_combustion_empty_mixture(tmp_path):
    lab = ChemLab(ogun_cfg(tmp_path))
    result = lab.combustion("")
    assert not result.ok


def test_ogun_combustion_endpoint(client):
    r = client.post("/api/ogun/combustion", json={"mixture": "CH4:1, O2:2, N2:7.52"})
    body = r.json()
    assert body["ok"] is True
    assert body["flame_temperature_k"] > 1000


# ----------------------------- Circuits ------------------------------

RC_COMPONENTS = [
    {"type": "R", "a": "in", "b": "out", "value": 1000},
    {"type": "C", "a": "out", "b": "0", "value": 1e-6},
]
RC_SOURCE = {"node_pos": "in", "node_neg": "0", "volts": 5.0}


async def test_rc_circuit_matches_real_charging_curve(tmp_path):
    lab = CircuitLab(ogun_cfg(tmp_path))
    result = await lab.simulate(RC_COMPONENTS, RC_SOURCE, ["in", "out"], step_us=1.0, end_ms=5.0)
    assert result.ok, result.error
    assert result.traces["out"][0] == pytest.approx(0.0, abs=0.05)
    # tau = R*C = 1ms; after 5 tau the node should be close to fully charged.
    assert result.traces["out"][-1] == pytest.approx(5.0, abs=0.1)
    # And it should be a real curve, not a step: roughly 63% charged at 1 tau.
    one_tau_idx = min(range(len(result.time_s)), key=lambda i: abs(result.time_s[i] - 0.001))
    assert result.traces["out"][one_tau_idx] == pytest.approx(3.16, abs=0.15)


async def test_circuit_rejects_unsupported_component(tmp_path):
    lab = CircuitLab(ogun_cfg(tmp_path))
    result = await lab.simulate(
        [{"type": "TRANSISTOR", "a": "in", "b": "out", "value": 1}], RC_SOURCE, ["out"],
    )
    assert not result.ok
    assert "unsupported" in result.error


async def test_circuit_rejects_missing_trace_nodes(tmp_path):
    lab = CircuitLab(ogun_cfg(tmp_path))
    result = await lab.simulate(RC_COMPONENTS, RC_SOURCE, [])
    assert not result.ok


async def test_circuit_disabled_by_default_config(tmp_path):
    lab = CircuitLab(ogun_cfg(tmp_path, enabled=False))
    result = await lab.simulate(RC_COMPONENTS, RC_SOURCE, ["out"])
    assert not result.ok
    assert "disabled" in result.error


def test_ogun_circuit_endpoint(client):
    r = client.post("/api/ogun/circuit", json={
        "components": RC_COMPONENTS, "source": RC_SOURCE, "trace_nodes": ["in", "out"],
    })
    body = r.json()
    assert body["ok"] is True
    assert len(body["traces"]["out"]) > 10
