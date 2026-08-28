"""The Skill Portal — Orunmila's "new wishes" pipeline, matching the
brief's own diagram:

    repo -> RepoMix compression -> AST + Bandit security gate ->
    save to workspace_skills/ -> manifest-driven UI -> one-click run

Built on real, existing tools rather than reimplemented: RepoMix (npm)
does the compression, Python's `ast` module plus Bandit do the security
gate. A saved skill is deliberately *not* general-purpose code — it's a
small script plus a manifest describing its inputs, run the same way
every time. That's what makes "one click" possible: running it later
never calls the model again, it just executes the saved script — the
literal "muscle memory" the brief asks for.

Security note: the AST/Bandit gate is a real, useful first line of
defense, but — as documented in this project's own tool notes — static
analysis alone is necessary, not sufficient. It can be fooled by
obfuscation and can't see what code does at runtime. Treat it as a
tripwire for careless or lightly-obfuscated attempts, not a guarantee;
a production deployment should also run saved skills inside a real
sandbox (gVisor/Docker), which this pass doesn't add.
"""
from __future__ import annotations

import ast
import asyncio
import json
import re
import shutil
import subprocess
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from ..config import SkillsCfg

# Attribute-call patterns banned outright — same list as this project's own
# spec: destructive filesystem ops and shell escapes. Deliberately not a
# blanket ban on modules like `subprocess` or `socket` themselves — a
# legitimate skill adapted from a real repo may need to call an HTTP API
# or run a specific known command; it just can't `os.system()` an
# arbitrary string or `shutil.rmtree()` a path.
_BANNED_CALL_NAMES = {"eval", "exec", "compile", "__import__"}
_BANNED_ATTR_CALLS = {
    ("os", "system"), ("os", "popen"), ("os", "remove"), ("os", "unlink"),
    ("os", "rmdir"), ("shutil", "rmtree"), ("pickle", "loads"), ("pickle", "load"),
}

_INPUT_TYPES = {"text", "number"}
_SLUG_RE = re.compile(r"[^a-z0-9-]+")


def _slugify(name: str) -> str:
    slug = _SLUG_RE.sub("-", name.strip().lower()).strip("-")
    return slug or uuid.uuid4().hex[:8]


# ------------------------------- results ---------------------------------

@dataclass
class FetchResult:
    ok: bool
    error: str = ""
    source: str = ""
    files_packed: int = 0
    compressed: str = ""
    compressed_chars: int = 0

    def to_dict(self) -> dict:
        return dict(self.__dict__)


@dataclass
class ScanResult:
    ok: bool
    error: str = ""
    ast_findings: list[str] = field(default_factory=list)
    bandit_findings: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return dict(self.__dict__)


@dataclass
class SkillInput:
    name: str
    label: str
    type: str = "text"


@dataclass
class SkillRecord:
    slug: str
    label: str
    description: str
    inputs: list[dict] = field(default_factory=list)
    source_repo: str = ""

    def to_dict(self) -> dict:
        return dict(self.__dict__)


@dataclass
class RunResult:
    ok: bool
    error: str = ""
    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None

    def to_dict(self) -> dict:
        return dict(self.__dict__)


def _ast_gate(source: str) -> list[str]:
    """First-pass static scan. Non-empty result = hard block."""
    findings: list[str] = []
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        return [f"line {e.lineno}: syntax error — {e.msg}"]

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id in _BANNED_CALL_NAMES:
            findings.append(f"line {node.lineno}: calls banned function '{func.id}()'")
        elif (
            isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Name)
            and (func.value.id, func.attr) in _BANNED_ATTR_CALLS
        ):
            findings.append(f"line {node.lineno}: calls banned '{func.value.id}.{func.attr}()'")
    return findings


class SkillPortal:
    def __init__(self, cfg: SkillsCfg):
        self.cfg = cfg
        self.workdir = Path(cfg.workdir).expanduser()

    # ------------------------------ fetch ---------------------------------

    async def fetch(self, source: str) -> FetchResult:
        if not self.cfg.enabled:
            return FetchResult(ok=False, error="skill portal disabled on this node (set skills.enabled: true)")
        if not source.strip():
            return FetchResult(ok=False, error="empty source")
        if not shutil.which("git"):
            return FetchResult(ok=False, error="git not installed")

        clone_dir = self.workdir / f"_fetch-{uuid.uuid4().hex[:12]}"
        try:
            proc = await asyncio.create_subprocess_exec(
                "git", "clone", "--quiet", "--depth", "1", source, str(clone_dir),
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
            )
            try:
                log, _ = await asyncio.wait_for(proc.communicate(), timeout=self.cfg.fetch_timeout_s)
            except asyncio.TimeoutError:
                proc.kill()
                return FetchResult(ok=False, error=f"clone timed out after {self.cfg.fetch_timeout_s}s")
            if proc.returncode != 0 or not clone_dir.exists():
                return FetchResult(ok=False, error=f"clone failed: {log.decode(errors='replace')[-500:]}")

            file_count = sum(1 for p in clone_dir.rglob("*") if p.is_file() and ".git" not in p.parts)
            if file_count > self.cfg.max_repo_files:
                return FetchResult(ok=False, error=(
                    f"repo has {file_count} files, over this node's cap of "
                    f"{self.cfg.max_repo_files} — point at a subdirectory instead"
                ))

            compressed, error = await self._repomix(clone_dir)
            if error:
                return FetchResult(ok=False, error=error)
            return FetchResult(
                ok=True, source=source, files_packed=file_count,
                compressed=compressed[:self.cfg.max_compressed_chars],
                compressed_chars=len(compressed),
            )
        finally:
            shutil.rmtree(clone_dir, ignore_errors=True)

    async def _repomix(self, path: Path) -> tuple[str, str]:
        if not shutil.which("npx"):
            return "", "npx/node not installed"
        try:
            proc = await asyncio.create_subprocess_exec(
                "npx", "--yes", "repomix", str(path),
                "--stdout", "--style", "markdown", "--compress", "--remove-comments", "--quiet",
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            try:
                out, err = await asyncio.wait_for(proc.communicate(), timeout=self.cfg.fetch_timeout_s)
            except asyncio.TimeoutError:
                proc.kill()
                return "", f"repomix timed out after {self.cfg.fetch_timeout_s}s"
            if proc.returncode != 0:
                return "", f"repomix failed: {err.decode(errors='replace')[-500:]}"
            return out.decode(errors="replace"), ""
        except Exception as e:
            return "", f"repomix unavailable: {e}"

    # ------------------------------- scan -----------------------------------

    async def scan(self, source_code: str) -> ScanResult:
        if not self.cfg.enabled:
            return ScanResult(ok=False, error="skill portal disabled on this node (set skills.enabled: true)")
        ast_findings = _ast_gate(source_code)

        bandit_findings: list[dict] = []
        bandit_error = ""
        if shutil.which("bandit"):
            tmp = self.workdir / f"_scan-{uuid.uuid4().hex[:12]}.py"
            self.workdir.mkdir(parents=True, exist_ok=True)
            tmp.write_text(source_code)
            try:
                proc = await asyncio.create_subprocess_exec(
                    "bandit", "-f", "json", "-q", str(tmp),
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                )
                out, _ = await asyncio.wait_for(proc.communicate(), timeout=15.0)
                data = json.loads(out.decode(errors="replace") or "{}")
                bandit_findings = [
                    {
                        "test": r.get("test_name"), "severity": r.get("issue_severity"),
                        "confidence": r.get("issue_confidence"), "line": r.get("line_number"),
                        "text": r.get("issue_text"),
                    }
                    for r in data.get("results", [])
                ]
            except Exception as e:
                bandit_error = f"bandit scan failed: {e}"
            finally:
                tmp.unlink(missing_ok=True)
        else:
            bandit_error = "bandit not installed — AST gate only (weaker signal)"

        ok = not ast_findings and not any(
            f["severity"] == "HIGH" and f["confidence"] == "HIGH" for f in bandit_findings
        )
        return ScanResult(ok=ok, error=bandit_error, ast_findings=ast_findings, bandit_findings=bandit_findings)

    # ------------------------------- save ------------------------------------

    def _validate_manifest(self, manifest: dict) -> tuple[SkillRecord | None, str]:
        label = str(manifest.get("label", "")).strip()
        if not label:
            return None, "manifest.label is required"
        inputs = []
        for i, raw in enumerate(manifest.get("inputs", [])):
            if not isinstance(raw, dict) or "name" not in raw:
                return None, f"manifest.inputs[{i}] needs at least a 'name'"
            kind = raw.get("type", "text")
            if kind not in _INPUT_TYPES:
                return None, f"manifest.inputs[{i}].type must be one of {sorted(_INPUT_TYPES)}"
            inputs.append({"name": raw["name"], "label": raw.get("label", raw["name"]), "type": kind})
        return SkillRecord(
            slug=_slugify(manifest.get("skill_id") or label),
            label=label, description=str(manifest.get("description", "")),
            inputs=inputs, source_repo=str(manifest.get("source_repo", "")),
        ), ""

    async def save(self, script: str, manifest: dict, confirm: bool = False) -> tuple[SkillRecord | None, str]:
        if not self.cfg.enabled:
            return None, "skill portal disabled on this node (set skills.enabled: true)"
        if self.cfg.require_confirm and not confirm:
            return None, "confirmation required (pass confirm=true) — review the security scan first"
        if not script.strip():
            return None, "empty script"

        record, err = self._validate_manifest(manifest)
        if err:
            return None, err

        scan = await self.scan(script)
        if not scan.ok:
            reasons = scan.ast_findings + [f"{f['test']} ({f['severity']}/{f['confidence']})" for f in scan.bandit_findings
                                           if f["severity"] == "HIGH" and f["confidence"] == "HIGH"]
            return None, f"failed security scan: {'; '.join(reasons) or scan.error}"

        skill_dir = self.workdir / record.slug
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "skill.py").write_text(script)
        (skill_dir / "manifest.json").write_text(json.dumps(record.to_dict(), indent=2))
        return record, ""

    def list_skills(self) -> list[SkillRecord]:
        if not self.workdir.exists():
            return []
        out = []
        for d in sorted(self.workdir.iterdir()):
            manifest_path = d / "manifest.json"
            if d.is_dir() and manifest_path.exists():
                try:
                    out.append(SkillRecord(**json.loads(manifest_path.read_text())))
                except Exception:
                    continue
        return out

    def delete_skill(self, slug: str) -> bool:
        skill_dir = self.workdir / _slugify(slug)
        if not skill_dir.is_dir() or not (skill_dir / "manifest.json").exists():
            return False
        shutil.rmtree(skill_dir)
        return True

    # -------------------------- run (muscle memory) ---------------------------

    async def run(self, slug: str, inputs: dict) -> RunResult:
        """The one-click fast path: no model call, just execute the saved
        script with its inputs as a JSON argument. This is what makes a
        saved skill "muscle memory" rather than a fresh reasoning step."""
        if not self.cfg.enabled:
            return RunResult(ok=False, error="skill portal disabled on this node (set skills.enabled: true)")
        skill_dir = self.workdir / _slugify(slug)
        script_path = skill_dir / "skill.py"
        if not script_path.exists():
            return RunResult(ok=False, error=f"no such skill: {slug}")

        try:
            proc = await asyncio.create_subprocess_exec(
                "python3", str(script_path), json.dumps(inputs),
                cwd=str(skill_dir),
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            try:
                out, err = await asyncio.wait_for(proc.communicate(), timeout=self.cfg.run_timeout_s)
            except asyncio.TimeoutError:
                proc.kill()
                return RunResult(ok=False, error=f"skill timed out after {self.cfg.run_timeout_s}s")
            return RunResult(
                ok=proc.returncode == 0, stdout=out.decode(errors="replace")[:8000],
                stderr=err.decode(errors="replace")[:4000], exit_code=proc.returncode,
            )
        except Exception as e:
            return RunResult(ok=False, error=f"execution error: {e}")
