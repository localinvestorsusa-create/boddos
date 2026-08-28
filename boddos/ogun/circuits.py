"""RC/RL/RLC-scale circuit simulation for Ogun 3D's electronics lab.

Builds a netlist with PySpice's `Circuit` API (reliable, version-
independent text generation) but runs it through ngspice's own batch
mode as a subprocess rather than PySpice's shared-library binding —
that binding has real version friction against current ngspice
releases, while `ngspice -b` plus a `.control ... wrdata ...` block is
stable and matches this project's "fire a subprocess, get a result,
drop it" execution model everywhere else.

Needs the `ngspice` binary: `apt install ngspice`.
"""
from __future__ import annotations

import asyncio
import shutil
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from ..config import OgunCfg

try:
    from PySpice.Spice.Netlist import Circuit
    from PySpice.Unit import u_V
except ImportError:  # pragma: no cover - exercised via the ok=False path
    Circuit = None
    u_V = None

_GND_ALIASES = {"0", "gnd", "ground"}
_COMPONENT_BUILDERS = {"R", "C", "L"}
_OUTPUT_FILE = "ogun_trace.txt"


def _node(name: str) -> str:
    return "0" if str(name).strip().lower() in _GND_ALIASES else str(name).strip()


@dataclass
class CircuitResult:
    ok: bool
    error: str = ""
    netlist: str = ""
    time_s: list[float] = field(default_factory=list)
    traces: dict[str, list[float]] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return dict(self.__dict__)


class CircuitLab:
    def __init__(self, cfg: OgunCfg):
        self.cfg = cfg

    def _build_netlist(self, components: list[dict], source: dict,
                       trace_nodes: list[str], step_us: float, end_ms: float) -> str:
        circuit = Circuit("ogun circuit")
        pos, neg = _node(source["node_pos"]), _node(source.get("node_neg", "0"))
        volts = float(source["volts"])
        # A step turned on at t=0 — RC/RL/RLC transients need something to
        # respond to; a constant source alone just sits at its DC solution.
        circuit.PulseVoltageSource(
            "in", pos, neg, initial_value=0 @ u_V, pulsed_value=volts @ u_V,
            pulse_width=1, period=2, delay_time=0, rise_time=1e-9, fall_time=1e-9,
        )

        for i, comp in enumerate(components):
            kind = str(comp["type"]).upper()
            if kind not in _COMPONENT_BUILDERS:
                raise ValueError(f"unsupported component type: {kind}")
            a, b = _node(comp["a"]), _node(comp["b"])
            name = str(comp.get("name") or i + 1)
            value = float(comp["value"])
            getattr(circuit, kind)(name, a, b, value)

        if not trace_nodes:
            raise ValueError("trace_nodes must name at least one node to observe")
        traces = " ".join(f"v({_node(n)})" for n in trace_nodes)
        control = f"\n.control\ntran {step_us}u {end_ms}m\nwrdata {_OUTPUT_FILE} {traces}\n.endc\n"
        return str(circuit) + control + ".end\n"

    async def simulate(self, components: list[dict], source: dict, trace_nodes: list[str],
                       step_us: float = 1.0, end_ms: float = 5.0) -> CircuitResult:
        if not self.cfg.enabled:
            return CircuitResult(ok=False, error="Ogun 3D disabled on this node (set ogun.enabled: true)")
        if Circuit is None:
            return CircuitResult(ok=False, error="PySpice not installed (pip install 'boddos[ogun]')")
        if not shutil.which("ngspice"):
            return CircuitResult(ok=False, error="ngspice not installed (apt install ngspice)")

        try:
            netlist = self._build_netlist(components, source, trace_nodes, step_us, end_ms)
        except (KeyError, ValueError, TypeError) as e:
            return CircuitResult(ok=False, error=f"bad circuit description: {e}")

        workdir = Path(self.cfg.workdir).expanduser()
        job_dir = workdir / f"circuit-{uuid.uuid4().hex[:12]}"
        job_dir.mkdir(parents=True)
        netlist_path = job_dir / "circuit.cir"
        out_path = job_dir / _OUTPUT_FILE
        netlist_path.write_text(netlist)

        try:
            proc = await asyncio.create_subprocess_exec(
                "ngspice", "-b", str(netlist_path), cwd=str(job_dir),
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
            )
            try:
                log, _ = await asyncio.wait_for(proc.communicate(), timeout=self.cfg.render_timeout_s)
            except asyncio.TimeoutError:
                proc.kill()
                return CircuitResult(ok=False, netlist=netlist,
                                     error=f"simulation timed out after {self.cfg.render_timeout_s}s")

            if not out_path.exists():
                return CircuitResult(ok=False, netlist=netlist,
                                     error=f"simulation produced no output: {log.decode(errors='replace')[-500:]}")

            time_s, traces = self._parse_wrdata(out_path.read_text(), trace_nodes)
            return CircuitResult(ok=True, netlist=netlist, time_s=time_s, traces=traces)
        finally:
            for p in job_dir.glob("*"):
                p.unlink(missing_ok=True)
            job_dir.rmdir()

    @staticmethod
    def _parse_wrdata(text: str, trace_nodes: list[str],
                      max_points: int = 400) -> tuple[list[float], dict[str, list[float]]]:
        rows: list[list[float]] = []
        for line in text.splitlines():
            parts = line.split()
            if not parts:
                continue
            try:
                rows.append([float(x) for x in parts])
            except ValueError:
                continue
        if not rows:
            return [], {n: [] for n in trace_nodes}

        stride = max(1, len(rows) // max_points)
        sampled = rows[::stride]
        time_s = [r[0] for r in sampled]
        traces: dict[str, list[float]] = {}
        for i, node in enumerate(trace_nodes):
            col = 1 + i * 2  # wrdata writes interleaved (time, value) pairs per vector
            traces[node] = [r[col] for r in sampled if col < len(r)]
        return time_s, traces
