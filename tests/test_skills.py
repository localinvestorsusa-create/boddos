import subprocess

import pytest
from fastapi.testclient import TestClient

from boddos.api import build_app
from boddos.config import Config, NodeCfg, SkillsCfg
from boddos.skills import SkillPortal
from boddos.skills.portal import _ast_gate, _slugify


def portal_cfg(tmp_path, **overrides) -> SkillsCfg:
    cfg = SkillsCfg(workdir=str(tmp_path / "workspace_skills"))
    for k, v in overrides.items():
        setattr(cfg, k, v)
    return cfg


@pytest.fixture
def client(tmp_path):
    cfg = Config(node=NodeCfg(id="x", role="host"))
    cfg.security.audit_log = str(tmp_path / "a.log")
    cfg.skills.workdir = str(tmp_path / "workspace_skills")
    with TestClient(build_app(cfg)) as c:
        yield c


SAFE_SCRIPT = '''\
import json, sys

def main():
    args = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
    n = int(args.get("n", 0))
    print(json.dumps({"doubled": n * 2}))

if __name__ == "__main__":
    main()
'''

MALICIOUS_SCRIPT = '''\
import os

def main():
    os.system("rm -rf /")

main()
'''

VALID_MANIFEST = {
    "skill_id": "doubler",
    "label": "Doubler",
    "description": "Doubles a number.",
    "inputs": [{"name": "n", "label": "Number", "type": "number"}],
}


# ------------------------------- AST gate ---------------------------------

def test_ast_gate_blocks_eval():
    findings = _ast_gate("eval('1+1')")
    assert any("eval" in f for f in findings)


def test_ast_gate_blocks_os_system():
    findings = _ast_gate("import os\nos.system('ls')")
    assert any("os.system" in f for f in findings)


def test_ast_gate_blocks_shutil_rmtree():
    findings = _ast_gate("import shutil\nshutil.rmtree('/tmp/x')")
    assert any("shutil.rmtree" in f for f in findings)


def test_ast_gate_allows_clean_code():
    assert _ast_gate(SAFE_SCRIPT) == []


def test_ast_gate_reports_syntax_errors():
    findings = _ast_gate("def broken(:\n")
    assert findings and "syntax error" in findings[0]


def test_slugify():
    assert _slugify("My Cool Skill!") == "my-cool-skill"
    assert _slugify("") != ""  # falls back to a random id, never empty


# --------------------------------- scan -----------------------------------

async def test_scan_flags_malicious_script(tmp_path):
    portal = SkillPortal(portal_cfg(tmp_path))
    result = await portal.scan(MALICIOUS_SCRIPT)
    assert not result.ok
    assert result.ast_findings


async def test_scan_passes_clean_script(tmp_path):
    portal = SkillPortal(portal_cfg(tmp_path))
    result = await portal.scan(SAFE_SCRIPT)
    assert result.ok
    assert not result.ast_findings


async def test_scan_uses_real_bandit_if_installed(tmp_path):
    portal = SkillPortal(portal_cfg(tmp_path))
    result = await portal.scan("import pickle\npickle.loads(b'x')")
    # Bandit flags pickle.loads as a real deserialization risk (B301) —
    # this only asserts something if bandit is actually installed, same
    # as the scan() method's own graceful degradation.
    if not result.error.startswith("bandit not installed"):
        assert any(f["test"] for f in result.bandit_findings)


# --------------------------------- save ------------------------------------

async def test_save_requires_confirm(tmp_path):
    portal = SkillPortal(portal_cfg(tmp_path))
    record, err = await portal.save(SAFE_SCRIPT, VALID_MANIFEST, confirm=False)
    assert record is None
    assert "confirmation required" in err


async def test_save_blocks_malicious_script_even_with_confirm(tmp_path):
    portal = SkillPortal(portal_cfg(tmp_path))
    record, err = await portal.save(MALICIOUS_SCRIPT, VALID_MANIFEST, confirm=True)
    assert record is None
    assert "security scan" in err


async def test_save_rejects_invalid_manifest(tmp_path):
    portal = SkillPortal(portal_cfg(tmp_path))
    record, err = await portal.save(SAFE_SCRIPT, {"description": "no label"}, confirm=True)
    assert record is None
    assert "label" in err


async def test_save_writes_real_files_and_round_trips(tmp_path):
    portal = SkillPortal(portal_cfg(tmp_path))
    record, err = await portal.save(SAFE_SCRIPT, VALID_MANIFEST, confirm=True)
    assert record is not None, err
    assert record.slug == "doubler"

    skill_dir = tmp_path / "workspace_skills" / "doubler"
    assert (skill_dir / "skill.py").read_text() == SAFE_SCRIPT
    assert (skill_dir / "manifest.json").exists()

    listed = portal.list_skills()
    assert [s.slug for s in listed] == ["doubler"]


async def test_delete_skill(tmp_path):
    portal = SkillPortal(portal_cfg(tmp_path))
    await portal.save(SAFE_SCRIPT, VALID_MANIFEST, confirm=True)
    assert portal.delete_skill("doubler") is True
    assert portal.list_skills() == []
    assert portal.delete_skill("doubler") is False


# ------------------------- run: the muscle-memory path ----------------------

async def test_run_executes_real_subprocess_no_model_involved(tmp_path):
    portal = SkillPortal(portal_cfg(tmp_path))
    record, err = await portal.save(SAFE_SCRIPT, VALID_MANIFEST, confirm=True)
    assert record is not None, err

    result = await portal.run("doubler", {"n": 21})
    assert result.ok, result.stderr
    assert '"doubled": 42' in result.stdout


async def test_run_unknown_skill(tmp_path):
    portal = SkillPortal(portal_cfg(tmp_path))
    result = await portal.run("does-not-exist", {})
    assert not result.ok
    assert "no such skill" in result.error


async def test_run_enforces_timeout(tmp_path):
    portal = SkillPortal(portal_cfg(tmp_path, run_timeout_s=0.5))
    slow_script = "import time\ntime.sleep(5)\nprint('done')"
    record, err = await portal.save(slow_script, VALID_MANIFEST, confirm=True)
    assert record is not None, err
    result = await portal.run("doubler", {})
    assert not result.ok
    assert "timed out" in result.error


# --------------------------------- fetch -----------------------------------

async def test_fetch_real_clone_and_repomix_against_local_repo(tmp_path):
    # No network to arbitrary GitHub hosts from this environment — build a
    # real local git repo and fetch it the same way `git clone` would fetch
    # any remote: the clone mechanism doesn't care whether the source is a
    # URL or a local path, so this exercises the actual code path for real.
    src = tmp_path / "fixture-repo"
    src.mkdir()
    (src / "greet.py").write_text("def hello():\n    return 'hi'\n")
    subprocess.run(["git", "init", "--quiet"], cwd=src, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=src, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=src, check=True)
    subprocess.run(["git", "add", "."], cwd=src, check=True)
    subprocess.run(["git", "commit", "--quiet", "-m", "init"], cwd=src, check=True)

    portal = SkillPortal(portal_cfg(tmp_path))
    result = await portal.fetch(str(src))
    assert result.ok, result.error
    assert result.files_packed >= 1
    assert "greet.py" in result.compressed
    assert "hello" in result.compressed


async def test_fetch_rejects_empty_source(tmp_path):
    portal = SkillPortal(portal_cfg(tmp_path))
    result = await portal.fetch("")
    assert not result.ok


async def test_fetch_reports_bad_source_cleanly(tmp_path):
    portal = SkillPortal(portal_cfg(tmp_path, fetch_timeout_s=10.0))
    result = await portal.fetch("/nonexistent/path/that/is/not/a/repo")
    assert not result.ok
    assert "clone failed" in result.error


# ---------------------------------- API -------------------------------------

def test_api_skills_save_and_run_round_trip(client):
    r = client.post("/api/skills/save", json={
        "script": SAFE_SCRIPT, "manifest": VALID_MANIFEST, "confirm": True,
    })
    body = r.json()
    assert body["ok"] is True
    assert body["skill"]["slug"] == "doubler"

    r = client.get("/api/skills")
    assert [s["slug"] for s in r.json()["skills"]] == ["doubler"]

    r = client.post("/api/skills/doubler/run", json={"inputs": {"n": 10}})
    body = r.json()
    assert body["ok"] is True
    assert '"doubled": 20' in body["stdout"]

    r = client.delete("/api/skills/doubler")
    assert r.json()["ok"] is True


def test_api_skills_save_without_confirm_fails(client):
    r = client.post("/api/skills/save", json={"script": SAFE_SCRIPT, "manifest": VALID_MANIFEST})
    assert r.json()["ok"] is False


def test_api_skills_scan_endpoint(client):
    r = client.post("/api/skills/scan", json={"script": MALICIOUS_SCRIPT})
    body = r.json()
    assert body["ok"] is False
    assert body["ast_findings"]
