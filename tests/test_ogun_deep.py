import pytest
from fastapi.testclient import TestClient

from boddos.api import build_app
from boddos.config import Config, NodeCfg, OgunCfg
from boddos.ogun import AerospaceLab, BioLab, MaterialsLab, StructuresLab


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


# --------------------------- Structures (FEA) -------------------------

async def test_cantilever_beam_matches_analytical_theory(tmp_path):
    lab = StructuresLab(ogun_cfg(tmp_path))
    result = await lab.cantilever_beam(
        length_m=1.0, width_m=0.05, height_m=0.05, tip_force_n=-100.0, material="aluminum",
    )
    assert result.ok, result.error
    assert result.nodes > 0 and result.elements > 0
    # Real FEA on a coarse mesh vs. closed-form Euler-Bernoulli beam theory
    # should agree to within engineering tolerance, not exactly.
    assert result.agreement_pct > 85


async def test_beam_rejects_unknown_material(tmp_path):
    lab = StructuresLab(ogun_cfg(tmp_path))
    result = await lab.cantilever_beam(1.0, 0.05, 0.05, -100.0, material="unobtainium")
    assert not result.ok
    assert "unknown material" in result.error


async def test_beam_accepts_explicit_material_properties(tmp_path):
    lab = StructuresLab(ogun_cfg(tmp_path))
    result = await lab.cantilever_beam(
        1.0, 0.05, 0.05, -100.0, youngs_pa=69e9, poisson=0.33,
    )
    assert result.ok, result.error


async def test_beam_rejects_bad_dimensions(tmp_path):
    lab = StructuresLab(ogun_cfg(tmp_path))
    result = await lab.cantilever_beam(0, 0.05, 0.05, -100.0)
    assert not result.ok


async def test_beam_disabled_by_default_config(tmp_path):
    lab = StructuresLab(ogun_cfg(tmp_path, enabled=False))
    result = await lab.cantilever_beam(1.0, 0.05, 0.05, -100.0)
    assert not result.ok
    assert "disabled" in result.error


def test_ogun_beam_endpoint(client):
    r = client.post("/api/ogun/beam", json={
        "length_m": 1.0, "width_m": 0.05, "height_m": 0.05, "tip_force_n": -100.0,
        "material": "steel",
    })
    body = r.json()
    assert body["ok"] is True
    assert body["agreement_pct"] > 80


# ----------------------------- Aerospace -------------------------------

def test_rocket_flight_produces_plausible_trajectory(tmp_path):
    lab = AerospaceLab(ogun_cfg(tmp_path))
    result = lab.rocket_flight(
        total_impulse_ns=2000, burn_time_s=1.5, propellant_mass_kg=0.5,
        rocket_dry_mass_kg=5, rocket_radius_m=0.04,
    )
    assert result.ok, result.error
    assert result.apogee_m > 0
    assert result.max_speed_ms > 0
    assert result.time_to_apogee_s > 0
    # This default fin/nose geometry is intentionally minimal and, as
    # RocketPy's own stability check confirms, not aerodynamically stable —
    # exercising that the warning surfaces rather than being swallowed.
    assert any("static margin" in w for w in result.warnings)


def test_rocket_rejects_nonpositive_impulse(tmp_path):
    lab = AerospaceLab(ogun_cfg(tmp_path))
    result = lab.rocket_flight(0, 1.5, 0.5, 5, 0.04)
    assert not result.ok


def test_rocket_disabled_by_default_config(tmp_path):
    lab = AerospaceLab(ogun_cfg(tmp_path, enabled=False))
    result = lab.rocket_flight(2000, 1.5, 0.5, 5, 0.04)
    assert not result.ok
    assert "disabled" in result.error


def test_ogun_rocket_endpoint(client):
    r = client.post("/api/ogun/rocket", json={
        "total_impulse_ns": 2000, "burn_time_s": 1.5, "propellant_mass_kg": 0.5,
        "rocket_dry_mass_kg": 5, "rocket_radius_m": 0.04,
    })
    body = r.json()
    assert body["ok"] is True
    assert body["apogee_m"] > 0


# ------------------------- Living Matter (bio) --------------------------

def test_sequence_report_dna_translates_correctly(tmp_path):
    lab = BioLab(ogun_cfg(tmp_path))
    result = lab.sequence_report("ATGGCCATTGTAATGGGCCGCTGAAAGGGTGCCCGATAG")
    assert result.ok, result.error
    assert result.kind == "nucleotide"
    assert result.translated_protein == "MAIVMGR"
    assert result.gc_fraction is not None


def test_sequence_report_protein_direct(tmp_path):
    lab = BioLab(ogun_cfg(tmp_path))
    result = lab.sequence_report("MAIVMGR")
    assert result.ok, result.error
    assert result.kind == "protein"
    assert result.protein_molecular_weight_da > 0


def test_sequence_report_empty(tmp_path):
    lab = BioLab(ogun_cfg(tmp_path))
    result = lab.sequence_report("   ")
    assert not result.ok


def test_particle_chain_dynamics_conserves_energy(tmp_path):
    lab = BioLab(ogun_cfg(tmp_path))
    result = lab.particle_chain_dynamics(particle_count=6, steps=1000)
    assert result.ok, result.error
    assert len(result.energy_kj_mol) > 5
    # A real symplectic integrator should conserve energy tightly over a
    # short run — this is the actual physics check, not a placeholder.
    assert result.max_energy_drift_pct < 5.0


def test_particle_chain_dynamics_rejects_too_few_particles(tmp_path):
    lab = BioLab(ogun_cfg(tmp_path))
    result = lab.particle_chain_dynamics(particle_count=1)
    assert not result.ok


def test_bio_disabled_by_default_config(tmp_path):
    lab = BioLab(ogun_cfg(tmp_path, enabled=False))
    assert not lab.sequence_report("ATGC").ok
    assert not lab.particle_chain_dynamics().ok


def test_ogun_sequence_endpoint(client):
    r = client.post("/api/ogun/sequence", json={"sequence": "ATGGCCATTGTAATGGGCCGCTGAAAGGGTGCCCGATAG"})
    body = r.json()
    assert body["ok"] is True
    assert body["translated_protein"] == "MAIVMGR"


def test_ogun_dynamics_endpoint(client):
    r = client.post("/api/ogun/dynamics", json={"particle_count": 5, "steps": 500})
    body = r.json()
    assert body["ok"] is True
    assert body["max_energy_drift_pct"] < 5.0


# ------------------------------ Materials --------------------------------

def test_materials_lookup_without_api_key_fails_cleanly(tmp_path):
    lab = MaterialsLab(ogun_cfg(tmp_path))
    result = lab.search_by_formula("Fe2O3")
    assert not result.ok
    assert "API key" in result.error


def test_materials_disabled_by_default_config(tmp_path):
    lab = MaterialsLab(ogun_cfg(tmp_path, enabled=False))
    result = lab.search_by_formula("Fe2O3")
    assert not result.ok
    assert "disabled" in result.error


def test_ogun_material_endpoint_without_key(client):
    r = client.post("/api/ogun/material", json={"formula": "Fe2O3"})
    body = r.json()
    assert body["ok"] is False
    assert "API key" in body["error"]
