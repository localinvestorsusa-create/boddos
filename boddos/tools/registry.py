"""Voice/chat tool-calling registry — the bridge from Orunmila's agentic
chat loop to every action this node can already take.

Each entry wraps an existing service/lab method exactly the way its REST
endpoint does (same validation, same audit-log entry, `via: "voice"` added
so the audit trail shows it was chat/voice-triggered rather than a manual
button click). A spoken command reaches the same production code path as
the UI buttons, never a shortcut around it — including the 2FA gate that
`agent.run`/`drone.command`/`screen.click` already enforce when 2FA is on:
tool-calling doesn't bypass that, it's just another caller of it.

Deliberately NOT wired in here: the duress trigger, the encrypted vault,
2FA verification, and geofence/breach edits. Those stay manual/REST-only —
a misheard voice command firing a real panic alert to trusted contacts, or
reading vault secrets aloud, is a different risk class than re-running a
beam simulation, and warrants a separate, explicit decision.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from ..agent.web import fetch_url
from ..services import directions, get_forecast, translate_to_english


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict
    required: list[str]
    fn: Callable[..., Awaitable[dict]]

    def to_ollama_tool(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": self.parameters,
                    "required": self.required,
                },
            },
        }


def build_tool_registry(state: Any, cfg: Any) -> dict[str, ToolSpec]:
    tools: dict[str, ToolSpec] = {}

    def register(name: str, description: str, parameters: dict, required: list[str],
                 fn: Callable[..., Awaitable[dict]]) -> None:
        tools[name] = ToolSpec(name, description, parameters, required, fn)

    # ---------------------------- skills ----------------------------
    async def _skills_run(slug: str, inputs: dict | None = None) -> dict:
        res = await state.skills.run(slug, inputs or {})
        state.audit.record("skills.run", {"ok": res.ok, "slug": slug, "via": "voice"})
        return res.to_dict()

    register(
        "run_skill", "Run a previously saved muscle-memory skill by its slug, with JSON inputs.",
        {"slug": {"type": "string"}, "inputs": {"type": "object", "description": "input name -> value"}},
        ["slug"], _skills_run,
    )

    async def _skills_list() -> dict:
        return {"skills": [s.to_dict() for s in state.skills.list_skills()]}

    register("list_skills", "List every saved muscle-memory skill (slug, label, description, inputs).",
             {}, [], _skills_list)

    # ---------------------------- ogun 3d ----------------------------
    async def _ogun_model(scad: str) -> dict:
        res = await state.cad.build(scad)
        state.audit.record("ogun.model", {"ok": res.ok, "facets": res.facets, "chars": len(scad), "via": "voice"})
        return res.to_dict()

    register(
        "build_3d_model", "Build a 3D model from OpenSCAD source and render an STL + preview image.",
        {"scad": {"type": "string", "description": "OpenSCAD source code"}}, ["scad"], _ogun_model,
    )

    async def _ogun_combustion(mixture: str, initial_temp_k: float = 300.0, pressure_atm: float = 1.0) -> dict:
        res = state.chem.combustion(mixture, initial_temp_k, pressure_atm)
        state.audit.record("ogun.combustion", {"ok": res.ok, "mixture": mixture, "via": "voice"})
        return res.to_dict()

    register(
        "check_combustion",
        "Compute the adiabatic flame temperature and product mole fractions of a fuel/air mixture with Cantera.",
        {"mixture": {"type": "string", "description": "Cantera mole-fraction string, e.g. 'CH4:1, O2:2, N2:7.52'"},
         "initial_temp_k": {"type": "number"}, "pressure_atm": {"type": "number"}},
        ["mixture"], _ogun_combustion,
    )

    async def _ogun_circuit(components: list, source: dict, trace_nodes: list,
                            step_us: float = 1.0, end_ms: float = 5.0) -> dict:
        res = await state.circuits.simulate(components, source, trace_nodes, step_us, end_ms)
        state.audit.record("ogun.circuit", {"ok": res.ok, "components": len(components), "via": "voice"})
        return res.to_dict()

    register(
        "simulate_circuit", "Simulate an RC/RL/RLC circuit with ngspice and return time-series voltage traces.",
        {"components": {"type": "array", "description": "[{type: 'R'|'C'|'L', a: node, b: node, value: number}]"},
         "source": {"type": "object", "description": "{node_pos, node_neg, volts}"},
         "trace_nodes": {"type": "array", "items": {"type": "string"}},
         "step_us": {"type": "number"}, "end_ms": {"type": "number"}},
        ["components", "source", "trace_nodes"], _ogun_circuit,
    )

    async def _ogun_beam(length_m: float, width_m: float, height_m: float, tip_force_n: float,
                         material: str = "aluminum", youngs_pa: float | None = None,
                         poisson: float | None = None, elements_along_length: int = 20) -> dict:
        res = await state.structures.cantilever_beam(
            length_m, width_m, height_m, tip_force_n, material, youngs_pa, poisson, elements_along_length,
        )
        state.audit.record("ogun.beam", {"ok": res.ok, "material": material, "via": "voice"})
        return res.to_dict()

    register(
        "simulate_beam",
        "Solve a cantilever beam's tip deflection with CalculiX FEA, cross-checked against closed-form beam theory.",
        {"length_m": {"type": "number"}, "width_m": {"type": "number"}, "height_m": {"type": "number"},
         "tip_force_n": {"type": "number"}, "material": {"type": "string", "description": "aluminum, steel, titanium, ..."}},
        ["length_m", "width_m", "height_m", "tip_force_n"], _ogun_beam,
    )

    async def _ogun_rocket(total_impulse_ns: float, burn_time_s: float, propellant_mass_kg: float,
                           rocket_dry_mass_kg: float, rocket_radius_m: float,
                           motor_dry_mass_kg: float = 1.0, drag_coefficient: float = 0.5,
                           fin_count: int = 4, rail_length_m: float = 2.0, inclination_deg: float = 85.0) -> dict:
        res = state.aerospace.rocket_flight(
            total_impulse_ns, burn_time_s, propellant_mass_kg, rocket_dry_mass_kg, rocket_radius_m,
            motor_dry_mass_kg=motor_dry_mass_kg, drag_coefficient=drag_coefficient,
            fin_count=fin_count, rail_length_m=rail_length_m, inclination_deg=inclination_deg,
        )
        state.audit.record("ogun.rocket", {"ok": res.ok, "via": "voice"})
        return res.to_dict()

    register(
        "simulate_rocket_flight",
        "Fly a rocket with RocketPy given motor/airframe parameters; flags aerodynamic instability (negative static margin).",
        {"total_impulse_ns": {"type": "number"}, "burn_time_s": {"type": "number"},
         "propellant_mass_kg": {"type": "number"}, "rocket_dry_mass_kg": {"type": "number"},
         "rocket_radius_m": {"type": "number"}},
        ["total_impulse_ns", "burn_time_s", "propellant_mass_kg", "rocket_dry_mass_kg", "rocket_radius_m"],
        _ogun_rocket,
    )

    async def _ogun_sequence(sequence: str) -> dict:
        res = state.bio.sequence_report(sequence)
        state.audit.record("ogun.sequence", {"ok": res.ok, "kind": res.kind, "via": "voice"})
        return res.to_dict()

    register(
        "analyze_sequence",
        "Analyze a DNA/RNA/protein sequence with Biopython (GC content, translation, molecular weight, instability index).",
        {"sequence": {"type": "string"}}, ["sequence"], _ogun_sequence,
    )

    async def _ogun_dynamics(particle_count: int = 8, bond_length_nm: float = 0.15,
                             bond_strength: float = 500.0, steps: int = 2000) -> dict:
        res = state.bio.particle_chain_dynamics(particle_count, bond_length_nm, bond_strength, steps)
        state.audit.record("ogun.dynamics", {"ok": res.ok, "via": "voice"})
        return res.to_dict()

    register(
        "run_molecular_dynamics", "Run a toy OpenMM molecular dynamics simulation of a bonded particle chain.",
        {"particle_count": {"type": "integer"}, "steps": {"type": "integer"}}, [], _ogun_dynamics,
    )

    async def _ogun_material(formula: str, limit: int = 5) -> dict:
        res = state.materials.search_by_formula(formula, limit)
        state.audit.record("ogun.material", {"ok": res.ok, "formula": formula, "via": "voice"})
        return res.to_dict()

    register(
        "lookup_material",
        "Look up real material properties (density, band gap, stability) by chemical formula via the Materials Project.",
        {"formula": {"type": "string"}, "limit": {"type": "integer"}}, ["formula"], _ogun_material,
    )

    # ------------------------- esu pathfinder -------------------------
    async def _directions(from_lat: float, from_lon: float, destination: str, profile: str = "walking") -> dict:
        if not cfg.services.routing.enabled:
            return {"ok": False, "error": "routing disabled"}
        result = await directions(
            from_lat, from_lon, destination, profile,
            cfg.services.routing.nominatim_url, cfg.services.routing.osrm_url,
        )
        state.audit.record("esu.directions", {"ok": result.get("ok"), "destination": destination, "via": "voice"})
        return result

    register(
        "get_directions", "Turn-by-turn walking/driving/cycling directions from the user's current position to a named destination.",
        {"from_lat": {"type": "number"}, "from_lon": {"type": "number"}, "destination": {"type": "string"},
         "profile": {"type": "string", "enum": ["walking", "driving", "cycling"]}},
        ["from_lat", "from_lon", "destination"], _directions,
    )

    # ------------------------- device finder -------------------------
    async def _finder_scan(seconds: float = 4.0) -> dict:
        if not cfg.services.finder.enabled:
            return {"ok": False, "error": "finder disabled", "devices": []}
        res = await state.finder.scan(seconds)
        state.audit.record("finder.scan", {"ok": res.ok, "found": len(res.devices), "via": "voice"})
        return res.to_dict()

    register("scan_for_devices", "Scan for nearby Bluetooth devices (earbuds, tags, etc) and their signal strength.",
             {"seconds": {"type": "number"}}, [], _finder_scan)

    async def _finder_track(address: str, name: str = "") -> dict:
        if not cfg.services.finder.enabled:
            return {"ok": False, "error": "finder disabled"}
        res = await state.finder.start(address, name)
        state.audit.record("finder.track", {"ok": res.ok, "address": address, "via": "voice"})
        return res.to_dict()

    register(
        "track_device", "Start tracking one Bluetooth device's proximity (getting warmer/colder) by its address.",
        {"address": {"type": "string"}, "name": {"type": "string"}}, ["address"], _finder_track,
    )

    async def _finder_stop() -> dict:
        res = await state.finder.stop()
        return res.to_dict()

    register("stop_tracking_device", "Stop tracking the currently-tracked Bluetooth device.", {}, [], _finder_stop)

    async def _finder_status() -> dict:
        return state.finder.status().to_dict()

    register("device_tracking_status", "Get the current tracked device's proximity/trend without starting a new scan.",
             {}, [], _finder_status)

    # ------------------------------ mesh ------------------------------
    async def _mesh_nodes() -> dict:
        return {"nodes": [n.to_dict() for n in state.registry.all_nodes()]}

    register("list_mesh_nodes", "List every machine in this BODDOS mesh and its live hardware/models.", {}, [], _mesh_nodes)

    # ------------------------ weather / translate ------------------------
    async def _weather(lat: float | None = None, lon: float | None = None) -> dict:
        if not cfg.services.weather.enabled:
            return {"ok": False, "error": "weather disabled"}
        return await get_forecast(
            lat if lat is not None else cfg.services.weather.lat,
            lon if lon is not None else cfg.services.weather.lon,
        )

    register("get_weather", "Get the current weather forecast for a location (defaults to the configured home location).",
             {"lat": {"type": "number"}, "lon": {"type": "number"}}, [], _weather)

    async def _translate(text: str) -> dict:
        if not cfg.services.translate.enabled:
            return {"ok": False, "error": "translate disabled"}
        return await translate_to_english(state.provider, cfg.services.translate.model, text)

    register("translate_to_english", "Translate text into English with the local model.",
             {"text": {"type": "string"}}, ["text"], _translate)

    # -------------------------- drone / calling --------------------------
    async def _drone(action: str, params: dict | None = None) -> dict:
        res = await state.drone.command(action, params)
        state.audit.record("drone.command", {"action": action, "ok": res.get("ok"), "via": "voice"})
        return res

    register(
        "drone_command", "Send a command to the connected drone (e.g. takeoff, land, goto, return_home).",
        {"action": {"type": "string"}, "params": {"type": "object"}}, ["action"], _drone,
    )

    async def _call(number: str, message: str = "") -> dict:
        res = await state.calling.place_call(number, message)
        state.audit.record("call.place", {"number": number, "ok": res.get("ok"), "via": "voice"})
        return res

    register(
        "place_call", "Place a phone call, optionally with a message, via the configured calling provider.",
        {"number": {"type": "string"}, "message": {"type": "string"}}, ["number"], _call,
    )

    # ------------------------- OS agent / web fetch -------------------------
    async def _run_command(command: str) -> dict:
        res = await state.agent.run(command, confirm=True)
        state.audit.record("agent.run", {"command": command, "ok": res.ok, "exit": res.exit_code, "via": "voice"})
        return res.to_dict()

    register(
        "run_shell_command",
        "Run one allowlisted shell command on this machine (only commands in agent.allowed_commands are permitted).",
        {"command": {"type": "string"}}, ["command"], _run_command,
    )

    async def _fetch(url: str) -> dict:
        return await fetch_url(url)

    register("fetch_web_page", "Fetch a web page and return its title and de-tagged text.",
             {"url": {"type": "string"}}, ["url"], _fetch)

    # --------------------------- screen control ---------------------------
    async def _screen_look(prompt: str | None = None) -> dict:
        model = cfg.screen.vision_model or cfg.models.vision_model
        res = await state.screen.look(state.provider, model, prompt)
        state.audit.record("screen.look", {"ok": res.ok, "elements": len(res.elements), "via": "voice"})
        return res.to_dict()

    register("look_at_screen", "Take a screenshot of this machine's own display and list clickable elements on it.",
             {"prompt": {"type": "string"}}, [], _screen_look)

    async def _screen_drive(goal: str, max_steps: int | None = None, slow: bool = False) -> dict:
        vision_model = cfg.screen.vision_model or cfg.models.vision_model
        res = await state.screen.drive(state.provider, cfg.models.default_model, vision_model, goal, max_steps, slow)
        state.audit.record("screen.drive", {"ok": res.ok, "goal": goal, "finished": res.finished, "via": "voice"})
        return res.to_dict()

    register(
        "drive_screen",
        "Autonomously click/type/press through this machine's own screen to accomplish a goal, one "
        "perceive-decide-act loop at a time. Runs at full speed with no artificial delay by default — pass "
        "slow=true only if the user explicitly asked to watch it work. Anything that looks financial or "
        "destructive (pay, delete, send money, sudo, ...) always stops and returns awaiting_confirmation "
        "instead of acting; surface that to the user and call this again only after they say yes.",
        {"goal": {"type": "string"}, "max_steps": {"type": "integer"}, "slow": {"type": "boolean"}},
        ["goal"], _screen_drive,
    )

    return tools
