"""OpenSCAD-driven "describe a part, get a solid" loop for Ogun 3D.

Ogun doesn't write meshes directly — the local model writes OpenSCAD
source (a small, purely declarative CSG language: cubes, cylinders,
booleans, transforms), and this module renders that source to a real
STL plus a PNG preview via the `openscad` CLI. The declarative language
is a much narrower attack surface than handing the model a full
Python/Blender scripting environment: there's no file I/O, no network,
no arbitrary code execution — just solid geometry in, geometry out.

Needs the `openscad` binary and a virtual framebuffer for the preview
render: `apt install openscad xvfb`.
"""
from __future__ import annotations

import asyncio
import base64
import uuid
from dataclasses import dataclass
from pathlib import Path

from ..config import OgunCfg


@dataclass
class ModelResult:
    ok: bool
    error: str = ""
    stl_b64: str | None = None
    image_b64: str | None = None
    facets: int = 0
    log: str = ""

    def to_dict(self) -> dict:
        return dict(self.__dict__)


class CadStudio:
    def __init__(self, cfg: OgunCfg):
        self.cfg = cfg

    async def _openscad(self, *args: str) -> tuple[int, str]:
        try:
            proc = await asyncio.create_subprocess_exec(
                "xvfb-run", "-a", "openscad", *args,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
            )
        except FileNotFoundError as e:
            return -1, f"openscad/xvfb-run not installed: {e}"
        try:
            out, _ = await asyncio.wait_for(proc.communicate(), timeout=self.cfg.render_timeout_s)
        except asyncio.TimeoutError:
            proc.kill()
            return -1, f"openscad timed out after {self.cfg.render_timeout_s}s"
        return proc.returncode, out.decode(errors="replace")

    async def build(self, scad_source: str) -> ModelResult:
        if not self.cfg.enabled:
            return ModelResult(ok=False, error="Ogun 3D disabled on this node (set ogun.enabled: true)")
        if not scad_source.strip():
            return ModelResult(ok=False, error="empty model source")
        if len(scad_source) > self.cfg.max_source_chars:
            return ModelResult(ok=False, error=f"model source too long (>{self.cfg.max_source_chars} chars)")

        workdir = Path(self.cfg.workdir).expanduser()
        workdir.mkdir(parents=True, exist_ok=True)
        job_id = uuid.uuid4().hex[:12]
        scad_path = workdir / f"{job_id}.scad"
        stl_path = workdir / f"{job_id}.stl"
        png_path = workdir / f"{job_id}.png"
        scad_path.write_text(scad_source)

        try:
            code, log = await self._openscad("-o", str(stl_path), str(scad_path))
            if code != 0 or not stl_path.exists():
                return ModelResult(ok=False, error="model has no valid geometry — see log", log=log)

            facets = sum(1 for line in stl_path.read_text(errors="replace").splitlines()
                        if "facet normal" in line)

            _, preview_log = await self._openscad(
                "-o", str(png_path), "--autocenter", "--viewall", "--imgsize=640,640", str(scad_path),
            )

            stl_b64 = base64.b64encode(stl_path.read_bytes()).decode()
            image_b64 = base64.b64encode(png_path.read_bytes()).decode() if png_path.exists() else None
            return ModelResult(ok=True, stl_b64=stl_b64, image_b64=image_b64, facets=facets,
                               log=log or preview_log)
        finally:
            for p in (scad_path, stl_path, png_path):
                p.unlink(missing_ok=True)
