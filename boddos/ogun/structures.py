"""Structural FEA for Ogun 3D's physical lab, via CalculiX (`ccx`).

Scoped to one well-defined case — a rectangular cantilever beam under a
tip load — the same way circuits.py is scoped to RC/RL/RLC rather than
arbitrary netlists: it's a real, useful, and independently verifiable
piece of the "full physical lab" instead of a fragile attempt at
general-geometry FEA in one pass.

The mesh is generated directly (a structured grid of C3D8R hex
elements — reduced-integration, to avoid the well-known shear-locking
that makes plain C3D8 elements read artificially stiff in bending) and
solved with CalculiX. For arbitrary geometry meshing in a future pass,
`gmsh` is installed alongside this and can mesh a CAD Studio STL
directly; this module doesn't need it for a simple beam.

Needs the `ccx` binary: `apt install calculix-ccx`.
"""
from __future__ import annotations

import asyncio
import shutil
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from ..config import OgunCfg

MATERIAL_PRESETS = {
    "steel": (200e9, 0.30),
    "aluminum": (69e9, 0.33),
    "titanium": (116e9, 0.34),
    "wood_pine": (9e9, 0.35),
    "abs_plastic": (2.3e9, 0.35),
}


@dataclass
class BeamResult:
    ok: bool
    error: str = ""
    tip_deflection_m: float = 0.0
    analytical_deflection_m: float = 0.0
    agreement_pct: float = 0.0
    max_stress_note: str = ""
    nodes: int = 0
    elements: int = 0

    def to_dict(self) -> dict:
        return dict(self.__dict__)


def _grid(n: int, size: float) -> list[float]:
    return [i * size / n for i in range(n + 1)]


class StructuresLab:
    def __init__(self, cfg: OgunCfg):
        self.cfg = cfg

    def _build_mesh(self, length: float, width: float, height: float,
                    nx: int, ny: int, nz: int):
        xs, ys, zs = _grid(nx, length), _grid(ny, width), _grid(nz, height)

        def nid(i: int, j: int, k: int) -> int:
            return 1 + i * (ny + 1) * (nz + 1) + j * (nz + 1) + k

        nodes = [(nid(i, j, k), x, y, z)
                 for i, x in enumerate(xs) for j, y in enumerate(ys) for k, z in enumerate(zs)]

        elements = []
        eid = 1
        for i in range(nx):
            for j in range(ny):
                for k in range(nz):
                    conn = [
                        nid(i, j, k), nid(i + 1, j, k), nid(i + 1, j + 1, k), nid(i, j + 1, k),
                        nid(i, j, k + 1), nid(i + 1, j, k + 1), nid(i + 1, j + 1, k + 1), nid(i, j + 1, k + 1),
                    ]
                    elements.append((eid, conn))
                    eid += 1

        fixed = [n for n, x, _, _ in nodes if abs(x) < 1e-9]
        tip = [n for n, x, _, _ in nodes if abs(x - length) < 1e-9]
        return nodes, elements, fixed, tip

    @staticmethod
    def _chunked(ids: list[int], width: int = 8) -> list[str]:
        return [", ".join(str(x) for x in ids[i:i + width]) for i in range(0, len(ids), width)]

    def _write_inp(self, path: Path, length: float, width: float, height: float,
                   youngs_pa: float, poisson: float, tip_force_n: float,
                   nx: int, ny: int, nz: int) -> tuple[int, int]:
        nodes, elements, fixed, tip = self._build_mesh(length, width, height, nx, ny, nz)
        force_per_node = tip_force_n / len(tip)

        lines = ["*NODE"]
        lines += [f"{n}, {x:.6f}, {y:.6f}, {z:.6f}" for n, x, y, z in nodes]
        lines.append("*ELEMENT, TYPE=C3D8R, ELSET=BEAM")
        lines += [f"{e}, " + ", ".join(str(c) for c in conn) for e, conn in elements]
        lines.append("*NSET, NSET=TIP")
        lines += self._chunked(tip)
        lines.append("*MATERIAL, NAME=MAT1")
        lines.append("*ELASTIC")
        lines.append(f"{youngs_pa}, {poisson}")
        lines.append("*SOLID SECTION, ELSET=BEAM, MATERIAL=MAT1")
        lines.append("*BOUNDARY")
        lines += [f"{n}, 1, 3" for n in fixed]
        lines.append("*STEP")
        lines.append("*STATIC")
        lines.append("*CLOAD")
        lines += [f"{n}, 3, {force_per_node:.6f}" for n in tip]
        lines.append("*NODE PRINT, NSET=TIP")
        lines.append("U")
        lines.append("*END STEP")
        path.write_text("\n".join(lines) + "\n")
        return len(nodes), len(elements)

    @staticmethod
    def _parse_tip_deflection(dat_text: str) -> float | None:
        """Average the z-displacement across the tip node set's *NODE PRINT block."""
        in_block = False
        values: list[float] = []
        for line in dat_text.splitlines():
            if "displacements" in line and "TIP" in line:
                in_block = True
                continue
            if in_block:
                parts = line.split()
                if len(parts) == 4:
                    try:
                        values.append(float(parts[3]))
                    except ValueError:
                        break
                elif values:
                    break
        return sum(values) / len(values) if values else None

    async def cantilever_beam(
        self, length_m: float, width_m: float, height_m: float,
        tip_force_n: float, material: str = "aluminum",
        youngs_pa: float | None = None, poisson: float | None = None,
        elements_along_length: int = 20,
    ) -> BeamResult:
        if not self.cfg.enabled:
            return BeamResult(ok=False, error="Ogun 3D disabled on this node (set ogun.enabled: true)")
        if not shutil.which("ccx"):
            return BeamResult(ok=False, error="CalculiX not installed (apt install calculix-ccx)")
        if min(length_m, width_m, height_m) <= 0:
            return BeamResult(ok=False, error="length/width/height must all be positive")

        if youngs_pa is None or poisson is None:
            preset = MATERIAL_PRESETS.get(material.lower())
            if preset is None:
                return BeamResult(ok=False, error=(
                    f"unknown material '{material}' — pass youngs_pa/poisson explicitly, "
                    f"or use one of: {', '.join(MATERIAL_PRESETS)}"
                ))
            youngs_pa, poisson = preset

        nx = max(4, min(60, elements_along_length))
        ny = nz = 4

        workdir = Path(self.cfg.workdir).expanduser()
        job_dir = workdir / f"beam-{uuid.uuid4().hex[:12]}"
        job_dir.mkdir(parents=True)
        inp_path = job_dir / "beam.inp"

        try:
            n_nodes, n_elements = self._write_inp(
                inp_path, length_m, width_m, height_m, youngs_pa, poisson, tip_force_n, nx, ny, nz,
            )
            proc = await asyncio.create_subprocess_exec(
                "ccx", "beam", cwd=str(job_dir),
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
            )
            try:
                log, _ = await asyncio.wait_for(proc.communicate(), timeout=self.cfg.render_timeout_s)
            except asyncio.TimeoutError:
                proc.kill()
                return BeamResult(ok=False, error=f"solve timed out after {self.cfg.render_timeout_s}s")

            dat_path = job_dir / "beam.dat"
            if not dat_path.exists():
                return BeamResult(ok=False, error=f"solve failed: {log.decode(errors='replace')[-500:]}")

            deflection = self._parse_tip_deflection(dat_path.read_text())
            if deflection is None:
                return BeamResult(ok=False, error="couldn't parse solver output")

            inertia = width_m * height_m ** 3 / 12
            analytical = tip_force_n * length_m ** 3 / (3 * youngs_pa * inertia) if inertia else 0.0
            agreement = (100.0 * (1 - abs(abs(deflection) - abs(analytical)) / abs(analytical))
                        if analytical else 0.0)

            note = ""
            if length_m / max(width_m, height_m) < 5:
                note = "length is not much greater than the cross-section — beam theory is a rough check here, not ground truth"

            return BeamResult(
                ok=True, tip_deflection_m=deflection, analytical_deflection_m=analytical,
                agreement_pct=agreement, max_stress_note=note, nodes=n_nodes, elements=n_elements,
            )
        finally:
            for p in job_dir.glob("*"):
                p.unlink(missing_ok=True)
            job_dir.rmdir()
