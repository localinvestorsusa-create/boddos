"""FastAPI application factory for a BODDOS node.

Brings together: mesh registry/router, local model provider, OS agent, services,
sensor fusion, the safety modules, and the security layer (mesh request signing,
client auth, rate limiting, audit log, encrypted vault) behind one HTTP +
WebSocket API that the phone PWA and peer nodes talk to.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import secrets
import time
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, Header, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .. import hardware
from ..netutil import detect_lan_ip
from ..config import Config
from ..models import OllamaProvider
from ..models.base import ChatMessage
from ..agent import OSAgent, ScreenAgent, fetch_url
from ..ogun import CadStudio, ChemLab, CircuitLab, StructuresLab, AerospaceLab, BioLab, MaterialsLab
from ..skills import SkillPortal
from ..tools import build_tool_registry
from ..voice import TTSEngine
from ..services import (
    get_forecast, translate_to_english, DroneAdapter, CallingAdapter, geocode, route, directions,
    DeviceFinder,
)
from ..services.notify import Notifier
from ..services.push import PushManager
from ..sensors import SensorFusion, Reading, CameraRegistry
from ..safety import (
    DuressManager, TrackerDetector, ExposureAudit, DeadMansSwitch,
    scan_report, check_password, GeoFence, Zone,
)
from ..security import MeshAuth, ClientAuth, AuditLog, RateLimiter, SecretVault, totp
from ..mesh import NodeInfo, MeshRegistry, Router
from ..mesh.bus import EventBus

UI_DIR = Path(__file__).resolve().parent.parent / "ui"

def advisor_system(name: str) -> str:
    return (
        f"You are {name}, a private personal advisor and safety assistant running "
        "on the user's own machines. Be concise, practical, and honest — you are "
        "often spoken to and answered aloud, so keep replies natural and to the "
        "point. You help the user protect themselves and get things done. You do "
        "not help surveil, deceive, or manipulate other people.\n\n"
        "You have real tools wired to this machine — 3D modeling, chemistry, "
        "circuits, structural/rocket simulation, biology, directions, a Bluetooth "
        "device finder, muscle-memory skills, and control of this machine's own "
        "screen. When a request needs one, just call it — don't ask permission "
        "first or describe what you would do, do it. A single request often needs "
        "several tool calls in a row (e.g. look up a skill, run it, then check the "
        "result) or several at once — chain and parallelize freely to fully "
        "satisfy the request in one turn rather than stopping after the first "
        "step. Report results plainly once you have them. The one exception is "
        "drive_screen: if it comes back with awaiting_confirmation, stop and ask "
        "the user for an explicit yes before calling it again — that field means "
        "the next click looks financial or destructive."
    )

# Paths reachable without a client token (so the UI can load and prompt for one).
_AUTH_EXEMPT_PREFIXES = (
    "/health", "/ui", "/manifest", "/sw.js", "/api/ui-config",
    # A joining node's own backend calls this on the host node before the
    # two have ever exchanged a client-auth token — the one-time pairing
    # code itself is the credential here, same trust model as /mesh/hello's
    # HMAC signing (checked in-handler, not by this middleware).
    "/api/mesh/pair/claim",
)


class NodeState:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.hardware = hardware.detect()
        # A hardcoded default model doesn't know your RAM — on a 7GB
        # machine "llama3.1" (an 8B model) isn't a working default, it's a
        # silent failure mode. Blank config means "trust the hardware
        # detection this node already ran" instead.
        cfg.models.default_model = cfg.models.default_model or self.hardware.recommended_model
        cfg.models.vision_model = cfg.models.vision_model or self.hardware.recommended_vision_model
        me = NodeInfo(
            id=cfg.node.id,
            name=cfg.node.name,
            role=cfg.node.role,
            # 127.0.0.1 always means "myself" to whoever resolves it, so
            # it's useless as an address a peer could actually reach —
            # auto-detect this machine's real LAN IP instead of falling
            # back to a loopback address nobody else can dial.
            url=cfg.node.advertise_url or f"http://{detect_lan_ip()}:{cfg.node.bind_port}",
            ram_gb=round(self.hardware.ram_gb),
            has_gpu=self.hardware.has_gpu,
            vram_gb=self.hardware.vram_gb,
            gpu_name=self.hardware.gpu_name or "",
        )
        ttl = cfg.mesh.heartbeat_seconds * 3
        self.registry = MeshRegistry(me, ttl=ttl)
        self.router = Router(self.registry)
        self.provider = OllamaProvider(cfg.models.ollama_url)
        self.finder = DeviceFinder()
        self.agent = OSAgent(cfg.agent)
        self.screen = ScreenAgent(cfg.screen)
        self.cad = CadStudio(cfg.ogun)
        self.chem = ChemLab(cfg.ogun)
        self.circuits = CircuitLab(cfg.ogun)
        self.structures = StructuresLab(cfg.ogun)
        self.aerospace = AerospaceLab(cfg.ogun)
        self.bio = BioLab(cfg.ogun)
        self.materials = MaterialsLab(cfg.ogun)
        self.skills = SkillPortal(cfg.skills)
        self.tts = TTSEngine(cfg.voice)
        self.drone = DroneAdapter(cfg.services.drone)
        self.calling = CallingAdapter(cfg.services.calling)
        self.notifier = Notifier(cfg.services.notify)
        self.push = PushManager(
            cfg.services.push.vapid_public, cfg.services.push.vapid_private,
            cfg.services.push.subject, cfg.services.push.store_file,
        ) if cfg.services.push.enabled else None
        self.cameras = CameraRegistry()
        self.fusion = SensorFusion()
        self.duress = DuressManager(cfg.safety)
        self.trackers = TrackerDetector(cfg.safety.tracker_follow_threshold)
        self.exposure = ExposureAudit(self.provider, cfg.services.translate.model)
        self.deadman = DeadMansSwitch()
        self.geofence = GeoFence([
            Zone(z.name, z.lat, z.lon, z.radius_m, z.kind) for z in cfg.safety.geofences
        ])
        self.last_surveillance: dict = {"clear": True, "evil_twin_candidates": [], "flagged_devices": []}
        self.bus = EventBus()
        self.local_models: list[str] = []
        # Short-lived, one-time pairing codes for "click connect on both
        # machines" mesh joining — see the /api/mesh/pair/* endpoints.
        self.pending_pairings: dict[str, float] = {}

        # --- security ---
        self.mesh_auth = MeshAuth(cfg.mesh.psk)
        if cfg.security.require_auth and not cfg.security.api_token:
            cfg.security.api_token = ClientAuth.generate_token()
            print(f"[security] generated API token: {cfg.security.api_token}")
        self.client_auth = ClientAuth(cfg.security.api_token, cfg.security.require_auth)
        self.audit = AuditLog(cfg.security.audit_log)
        self.ratelimit = RateLimiter(
            rate_per_sec=cfg.security.rate_per_sec,
            capacity=cfg.security.rate_burst,
            lockout_threshold=cfg.security.lockout_threshold,
            lockout_seconds=cfg.security.lockout_seconds,
        )
        self.vault = SecretVault(cfg.security.vault_file)

        # --- voice/chat tool-calling: every action above, reachable from the
        # agentic loop in /api/chat/stream. Built last so it can bind every
        # subsystem constructed above.
        self.tools = build_tool_registry(self, cfg)

    def hello_payload(self) -> dict:
        me = self.registry.me
        me.models = self.local_models
        return me.to_dict()

    def signed(self, payload: dict, extra: dict | None = None) -> tuple[bytes, dict]:
        body = json.dumps(payload).encode()
        headers = self.mesh_auth.sign(body)
        headers["Content-Type"] = "application/json"
        if extra:
            headers.update(extra)
        return body, headers


def build_app(cfg: Config) -> FastAPI:
    state = NodeState(cfg)

    async def _refresh_models() -> None:
        state.local_models = await state.provider.list_models()

    async def _greet(peer: str) -> None:
        try:
            body, headers = state.signed(state.hello_payload())
            async with httpx.AsyncClient(timeout=5.0) as c:
                r = await c.post(f"{peer.rstrip('/')}/mesh/hello", content=body, headers=headers)
            # mesh_hello's response carries the peer's own hello payload —
            # register it now instead of waiting for that peer's own next
            # heartbeat to greet us back. Makes pairing feel instant on
            # whichever side clicked "Connect", not just the other one.
            info = r.json().get("me")
            if info:
                state.registry.from_hello(info)
        except Exception:
            pass

    async def _heartbeat_loop() -> None:
        while True:
            await _refresh_models()
            for peer in cfg.mesh.peers:
                await _greet(peer)
            await asyncio.sleep(cfg.mesh.heartbeat_seconds)

    async def _alert_push(title: str, body: str, data: dict | None = None) -> None:
        if state.push and state.push.enabled:
            await asyncio.to_thread(state.push.notify_all, title, body, data or {})

    async def _deadman_loop() -> None:
        while True:
            for c in state.deadman.due():
                res = state.duress.trigger(note=f"missed check-in: {c.label}",
                                           location=state.duress.state.last_location)
                delivery = await state.notifier.deliver_all(res["alerts"])
                await _alert_push("BODDOS duress", f"Missed check-in: {c.label}")
                state.audit.record("deadman.fire", {"label": c.label, "delivery": delivery})
                await _broadcast(res["event"])
            await asyncio.sleep(5)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await _refresh_models()
        tasks = [asyncio.create_task(_heartbeat_loop()),
                 asyncio.create_task(_deadman_loop())]
        try:
            yield
        finally:
            for t in tasks:
                t.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await t
            await state.finder.stop()

    app = FastAPI(title="BODDOS", version="0.1.0", lifespan=lifespan)
    app.state.node = state

    # ----------------------- security middleware ------------------
    @app.middleware("http")
    async def _guard(request: Request, call_next):
        client = request.client.host if request.client else "unknown"
        path = request.url.path

        if path == "/" or any(path.startswith(p) for p in _AUTH_EXEMPT_PREFIXES):
            return await call_next(request)

        if state.ratelimit.is_locked(client):
            return JSONResponse({"detail": "temporarily locked out"}, status_code=429)
        if not state.ratelimit.allow(client):
            return JSONResponse({"detail": "rate limit exceeded"}, status_code=429)

        # Client-token gate for the phone/UI API (mesh uses HMAC in-handler).
        if path.startswith("/api/") and state.client_auth.require:
            if not state.client_auth.check(request.headers.get("authorization")):
                state.ratelimit.record_failure(client)
                state.audit.record("auth.fail", {"path": path, "client": client})
                return JSONResponse({"detail": "unauthorized"}, status_code=401)
            state.ratelimit.record_success(client)
        return await call_next(request)

    async def _verify_mesh(request: Request) -> dict:
        body = await request.body()
        ok, reason = state.mesh_auth.verify(dict(request.headers), body)
        if not ok:
            state.audit.record("mesh.auth_fail", {"reason": reason})
            raise HTTPException(status_code=401, detail=f"mesh auth: {reason}")
        try:
            return json.loads(body or b"{}")
        except Exception:
            raise HTTPException(status_code=400, detail="bad json body")

    def _require_2fa(req: dict, action: str) -> None:
        """Enforce a TOTP code on sensitive actions when 2FA is enabled."""
        if not (cfg.security.require_2fa and cfg.security.totp_secret):
            return
        code = str(req.get("totp", "")) if isinstance(req, dict) else ""
        if not totp.verify(cfg.security.totp_secret, code):
            state.audit.record("twofa.fail", {"action": action})
            raise HTTPException(status_code=403, detail="valid TOTP code required")

    # ---------------------------- mesh ----------------------------
    @app.post("/mesh/hello")
    async def mesh_hello(request: Request):
        payload = await _verify_mesh(request)
        state.registry.from_hello(payload)
        return {"ok": True, "me": state.hello_payload()}

    @app.get("/mesh/nodes")
    async def mesh_nodes():
        return {"nodes": [n.to_dict() for n in state.registry.all_nodes()]}

    @app.post("/mesh/event")
    async def mesh_event(request: Request):
        event = await _verify_mesh(request)
        await state.bus.publish({**event, "_relayed": True})
        return {"ok": True}

    _PAIR_CODE_TTL_S = 600.0

    def _new_pairing_code() -> str:
        for _ in range(20):
            code = f"{secrets.randbelow(1_000_000):06d}"
            if code not in state.pending_pairings:
                return code
        raise RuntimeError("could not allocate a pairing code")  # pragma: no cover

    def _prune_pairings() -> None:
        now = time.time()
        expired = [c for c, exp in state.pending_pairings.items() if exp < now]
        for c in expired:
            del state.pending_pairings[c]

    @app.post("/api/mesh/pair/start")
    async def api_mesh_pair_start():
        """Step 1 of "click connect on both machines": generate a short,
        one-time code this node will accept for the next 10 minutes. Read
        it (and this machine's address) off to whoever's joining."""
        _prune_pairings()
        code = _new_pairing_code()
        state.pending_pairings[code] = time.time() + _PAIR_CODE_TTL_S
        state.audit.record("mesh.pair.start", {"code": code})
        return {
            "code": code,
            "expires_in_s": int(_PAIR_CODE_TTL_S),
            "my_url": state.registry.me.url,
            "my_name": cfg.node.name,
        }

    @app.post("/api/mesh/pair/claim")
    async def api_mesh_pair_claim(req: dict):
        """Step 2, called BY the joining node's own backend (not by a
        person): redeem a code this node issued. One-time use, short TTL —
        the code itself is the credential, matching the same trust model as
        the existing join-token/CLI flow (a URL alone reaches this node;
        the PSK returned here is what actually gates the mesh handshake)."""
        _prune_pairings()
        code = str(req.get("code", "")).strip()
        if code not in state.pending_pairings:
            return JSONResponse({"ok": False, "error": "unknown or expired code"}, status_code=404)
        del state.pending_pairings[code]
        state.audit.record("mesh.pair.claim", {"code": code})
        return {
            "ok": True,
            "psk": cfg.mesh.psk,
            "peer_url": state.registry.me.url,
            "name": cfg.node.name,
        }

    @app.post("/api/mesh/pair/redeem")
    async def api_mesh_pair_redeem(req: dict):
        """Step 3, called from THIS node's own UI: given another machine's
        address and the code shown on its screen, fetch its PSK/URL, adopt
        them, and greet it immediately instead of waiting for the next
        heartbeat. Takes effect for this running session; add the peer to
        config/boddos.yaml by hand to keep it after a restart."""
        host_url = str(req.get("host_url", "")).strip().rstrip("/")
        code = str(req.get("code", "")).strip()
        if not host_url or not code:
            return {"ok": False, "error": "host_url and code are both required"}
        try:
            async with httpx.AsyncClient(timeout=8.0) as c:
                r = await c.post(f"{host_url}/api/mesh/pair/claim", json={"code": code})
        except Exception as e:
            return {"ok": False, "error": f"couldn't reach {host_url}: {e}"}
        if r.status_code != 200:
            try:
                detail = r.json().get("error", r.text)
            except Exception:
                detail = r.text
            return {"ok": False, "error": f"that machine rejected the code: {detail}"}
        data = r.json()
        cfg.mesh.psk = data["psk"]
        state.mesh_auth = MeshAuth(cfg.mesh.psk)
        peer_url = data["peer_url"]
        if peer_url not in cfg.mesh.peers:
            cfg.mesh.peers.append(peer_url)
        await _greet(peer_url)
        state.audit.record("mesh.pair.redeem", {"peer_url": peer_url})
        return {"ok": True, "connected_to": data.get("name") or peer_url, "peer_url": peer_url}

    async def _broadcast(event: dict) -> None:
        await state.bus.publish(event)
        if cfg.safety.broadcast:
            for peer in cfg.mesh.peers:
                try:
                    body, headers = state.signed(event)
                    async with httpx.AsyncClient(timeout=4.0) as c:
                        await c.post(f"{peer.rstrip('/')}/mesh/event", content=body, headers=headers)
                except Exception:
                    pass

    # --------------------------- models ---------------------------
    @app.get("/api/models")
    async def api_models():
        mesh_models: dict[str, list[str]] = {state.registry.me.id: state.local_models}
        for p in state.registry.alive_peers():
            mesh_models[p.id] = p.models
        return {"local": state.local_models, "mesh": mesh_models,
                "default": cfg.models.default_model}

    @app.get("/api/hardware")
    async def api_hardware():
        return state.hardware.to_dict()

    # -------------------------- skill portal --------------------------
    @app.post("/api/skills/fetch")
    async def api_skills_fetch(req: dict):
        res = await state.skills.fetch(req.get("source", ""))
        state.audit.record("skills.fetch", {"ok": res.ok, "source": req.get("source")})
        return res.to_dict()

    @app.post("/api/skills/scan")
    async def api_skills_scan(req: dict):
        res = await state.skills.scan(req.get("script", ""))
        return res.to_dict()

    @app.post("/api/skills/save")
    async def api_skills_save(req: dict):
        record, err = await state.skills.save(
            req.get("script", ""), req.get("manifest", {}), confirm=bool(req.get("confirm")),
        )
        state.audit.record("skills.save", {"ok": record is not None, "error": err})
        if record is None:
            return {"ok": False, "error": err}
        return {"ok": True, "skill": record.to_dict()}

    @app.get("/api/skills")
    async def api_skills_list():
        return {"skills": [s.to_dict() for s in state.skills.list_skills()]}

    @app.post("/api/skills/{slug}/run")
    async def api_skills_run(slug: str, req: dict | None = None):
        res = await state.skills.run(slug, (req or {}).get("inputs", {}))
        state.audit.record("skills.run", {"ok": res.ok, "slug": slug})
        return res.to_dict()

    @app.delete("/api/skills/{slug}")
    async def api_skills_delete(slug: str):
        ok = state.skills.delete_skill(slug)
        state.audit.record("skills.delete", {"ok": ok, "slug": slug})
        return {"ok": ok}

    @app.post("/api/voice/speak")
    async def api_voice_speak(req: dict):
        text = req.get("text", "")
        voice = req.get("voice") or None
        res = await asyncio.to_thread(state.tts.speak, text, voice)
        if not res.ok:
            return JSONResponse({"ok": False, "error": res.error})
        return Response(content=res.audio_wav, media_type="audio/wav")

    @app.post("/api/chat")
    async def api_chat(req: dict, x_boddos_forwarded: str | None = Header(default=None)):
        model = req.get("model") or cfg.models.default_model
        if "messages" in req:
            msgs = [ChatMessage(m["role"], m["content"]) for m in req["messages"]]
        else:
            msgs = [ChatMessage("user", req.get("prompt", ""))]
        if not any(m.role == "system" for m in msgs):
            msgs.insert(0, ChatMessage("system", advisor_system(cfg.assistant.name)))

        target = state.router.select_model_node(model, state.local_models)
        if target.id != state.registry.me.id and not x_boddos_forwarded:
            try:
                body, headers = state.signed(
                    {"model": model, "messages": [m.to_dict() for m in msgs]},
                    extra={"X-Boddos-Forwarded": "1"},
                )
                async with httpx.AsyncClient(timeout=180.0) as c:
                    r = await c.post(f"{target.url}/api/chat", content=body, headers=headers)
                    r.raise_for_status()
                    data = r.json()
                    data["served_by"] = target.id
                    return data
            except Exception as e:
                reply = await state.provider.chat(model, msgs)
                return {"reply": reply, "served_by": state.registry.me.id,
                        "note": f"peer {target.id} unreachable ({e}); served locally"}

        reply = await state.provider.chat(model, msgs)
        return {"reply": reply, "served_by": state.registry.me.id, "model": model}

    def _build_messages(req: dict) -> list[ChatMessage]:
        if "messages" in req:
            msgs = [ChatMessage(m["role"], m["content"]) for m in req["messages"]]
        else:
            msgs = [ChatMessage("user", req.get("prompt", ""))]
        if not any(m.role == "system" for m in msgs):
            msgs.insert(0, ChatMessage("system", advisor_system(cfg.assistant.name)))
        return msgs

    MAX_TOOL_ROUNDS = 6

    async def _execute_tool_call(call: dict) -> tuple[str, dict]:
        fn = call.get("function", {})
        name = fn.get("name", "")
        raw_args = fn.get("arguments", {})
        if isinstance(raw_args, str):
            try:
                args = json.loads(raw_args) if raw_args else {}
            except json.JSONDecodeError:
                args = {}
        else:
            args = raw_args or {}
        spec = state.tools.get(name)
        if spec is None:
            return name, {"ok": False, "error": f"unknown tool: {name}"}
        try:
            result = await spec.fn(**args)
            if not isinstance(result, dict):
                result = {"ok": True, "result": result}
            return name, result
        except TypeError as e:
            return name, {"ok": False, "error": f"bad arguments for {name}: {e}"}
        except Exception as e:
            return name, {"ok": False, "error": f"{name} failed: {e}"}

    async def _agentic_stream(model: str, msgs: list[ChatMessage]):
        """The tool-calling loop: ask the model, execute anything it wants to
        call — possibly several tools in one round, run concurrently — feed
        the results back, and repeat until it answers in plain text or the
        round cap is hit. Every call/result is yielded as its own SSE event
        so the UI can narrate "using X..." live; the final answer streams as
        plain text same as before tool-calling existed."""
        tool_defs = [spec.to_ollama_tool() for spec in state.tools.values()]
        raw_msgs: list[dict] = [m.to_dict() for m in msgs]

        for _ in range(MAX_TOOL_ROUNDS):
            message = await state.provider.chat_with_tools(model, raw_msgs, tool_defs)
            calls = message.get("tool_calls") or []
            if not calls:
                content = message.get("content", "")
                if content:
                    yield {"t": content}
                return

            raw_msgs.append({"role": "assistant", "content": message.get("content", ""), "tool_calls": calls})
            for call in calls:
                fn = call.get("function", {})
                yield {"tool_call": {"name": fn.get("name", ""), "args": fn.get("arguments", {})}}

            results = await asyncio.gather(*(_execute_tool_call(c) for c in calls))
            for name, result in results:
                yield {"tool_result": {"name": name, "ok": bool(result.get("ok", True))}}
                raw_msgs.append({"role": "tool", "name": name, "content": json.dumps(result)[:6000]})

        yield {"t": "\n\n[reached this turn's tool-call limit — ask me to continue and I'll pick up from here]"}

    @app.post("/api/chat/stream")
    async def api_chat_stream(req: dict, x_boddos_forwarded: str | None = Header(default=None)):
        model = req.get("model") or cfg.models.default_model
        msgs = _build_messages(req)
        images = req.get("images")
        target = state.router.select_model_node(model, state.local_models)
        use_peer = target.id != state.registry.me.id and not x_boddos_forwarded
        # Tools act on THIS node's own hardware/screen/services, so they only
        # run for a genuinely local request — never when this node is just
        # serving compute for a peer's user, and never alongside images
        # (vision + tool-calling together isn't attempted here).
        use_tools = (not use_peer) and (not x_boddos_forwarded) and not images and req.get("tools", True) and bool(state.tools)

        async def gen_local():
            if use_tools:
                async for event in _agentic_stream(model, msgs):
                    yield f"data: {json.dumps(event)}\n\n"
            else:
                async for chunk in state.provider.chat_stream(model, msgs, images):
                    yield f"data: {json.dumps({'t': chunk})}\n\n"
            yield f"data: {json.dumps({'done': True, 'served_by': state.registry.me.id})}\n\n"

        async def gen_peer():
            try:
                body, headers = state.signed(
                    {"model": model, "messages": [m.to_dict() for m in msgs], "images": images},
                    extra={"X-Boddos-Forwarded": "1"},
                )
                async with httpx.AsyncClient(timeout=None) as c:
                    async with c.stream("POST", f"{target.url}/api/chat/stream",
                                        content=body, headers=headers) as r:
                        async for line in r.aiter_lines():
                            if line:
                                yield line + "\n"
            except Exception as e:
                yield f"data: {json.dumps({'t': f'[peer {target.id} unreachable: {e}]'})}\n\n"
                async for chunk in state.provider.chat_stream(model, msgs, images):
                    yield f"data: {json.dumps({'t': chunk})}\n\n"
                yield f"data: {json.dumps({'done': True})}\n\n"

        gen = gen_peer if use_peer else gen_local
        return StreamingResponse(gen(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.post("/api/models/pull")
    async def api_models_pull(req: dict):
        model = req.get("model", "").strip()
        if not model:
            return JSONResponse({"error": "model required"}, status_code=400)
        state.audit.record("models.pull", {"model": model})

        async def gen():
            async for prog in state.provider.pull(model):
                yield f"data: {json.dumps(prog)}\n\n"
            await _refresh_models()
            yield f"data: {json.dumps({'done': True})}\n\n"

        return StreamingResponse(gen(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache"})

    @app.post("/api/vision")
    async def api_vision(req: dict):
        """Analyze an image (base64, no data: prefix) with the local vision model."""
        image = req.get("image_b64", "")
        if not image:
            return {"ok": False, "error": "image_b64 required"}
        prompt = req.get("prompt") or "Describe what you see. Note anything relevant to my safety or situation."
        model = req.get("model") or cfg.models.vision_model
        msgs = [ChatMessage("user", prompt)]
        reply = await state.provider.chat(model, msgs, images=[image])
        return {"ok": True, "model": model, "analysis": reply}

    # ---------------------------- agent ---------------------------
    @app.post("/api/agent/run")
    async def api_agent_run(req: dict):
        _require_2fa(req, "agent.run")
        command = req.get("command", "")
        res = await state.agent.run(command, confirm=bool(req.get("confirm")))
        state.audit.record("agent.run", {"command": command, "ok": res.ok,
                                         "exit": res.exit_code})
        return res.to_dict()

    @app.post("/api/agent/fetch")
    async def api_agent_fetch(req: dict):
        return await fetch_url(req.get("url", ""))

    # ------------------------- screen control -----------------------
    @app.post("/api/agent/screen/look")
    async def api_screen_look(req: dict | None = None):
        req = req or {}
        model = req.get("model") or cfg.screen.vision_model or cfg.models.vision_model
        res = await state.screen.look(state.provider, model, req.get("prompt"))
        state.audit.record("screen.look", {"ok": res.ok, "elements": len(res.elements)})
        return res.to_dict()

    @app.post("/api/agent/screen/click")
    async def api_screen_click(req: dict):
        _require_2fa(req, "screen.click")
        res = state.screen.click(float(req.get("x", 0)), float(req.get("y", 0)),
                                 confirm=bool(req.get("confirm")))
        state.audit.record("screen.click", {"ok": res.ok, "x": req.get("x"), "y": req.get("y")})
        return res.to_dict()

    @app.post("/api/agent/screen/type")
    async def api_screen_type(req: dict):
        _require_2fa(req, "screen.type")
        text = req.get("text", "")
        res = state.screen.type_text(text, confirm=bool(req.get("confirm")))
        state.audit.record("screen.type", {"ok": res.ok, "chars": len(text)})
        return res.to_dict()

    @app.post("/api/agent/screen/press")
    async def api_screen_press(req: dict):
        _require_2fa(req, "screen.press")
        res = state.screen.press(req.get("key", ""), confirm=bool(req.get("confirm")))
        state.audit.record("screen.press", {"ok": res.ok, "key": req.get("key")})
        return res.to_dict()

    @app.post("/api/agent/screen/drive")
    async def api_screen_drive(req: dict):
        _require_2fa(req, "screen.drive")
        goal = req.get("goal", "").strip()
        if not goal:
            return {"ok": False, "error": "goal required"}
        model = req.get("model") or cfg.models.default_model
        vision_model = cfg.screen.vision_model or cfg.models.vision_model
        res = await state.screen.drive(
            state.provider, model, vision_model, goal,
            req.get("max_steps"), bool(req.get("slow")),
        )
        state.audit.record("screen.drive", {"ok": res.ok, "goal": goal, "finished": res.finished})
        return res.to_dict()

    # --------------------------- services -------------------------
    @app.get("/api/weather")
    async def api_weather(lat: float | None = None, lon: float | None = None):
        if not cfg.services.weather.enabled:
            return {"ok": False, "error": "weather disabled"}
        return await get_forecast(lat if lat is not None else cfg.services.weather.lat,
                                  lon if lon is not None else cfg.services.weather.lon)

    @app.post("/api/translate")
    async def api_translate(req: dict):
        if not cfg.services.translate.enabled:
            return {"ok": False, "error": "translate disabled"}
        return await translate_to_english(state.provider, cfg.services.translate.model,
                                          req.get("text", ""))

    # ----------------------- esu pathfinder -------------------------
    @app.get("/api/esu/geocode")
    async def api_esu_geocode(q: str):
        if not cfg.services.routing.enabled:
            return {"ok": False, "error": "routing disabled"}
        return await geocode(q, cfg.services.routing.nominatim_url)

    @app.get("/api/esu/route")
    async def api_esu_route(from_lat: float, from_lon: float, to_lat: float, to_lon: float,
                            profile: str = "walking"):
        if not cfg.services.routing.enabled:
            return {"ok": False, "error": "routing disabled"}
        return await route(from_lat, from_lon, to_lat, to_lon, profile, cfg.services.routing.osrm_url)

    @app.post("/api/esu/directions")
    async def api_esu_directions(req: dict):
        if not cfg.services.routing.enabled:
            return {"ok": False, "error": "routing disabled"}
        destination = req.get("destination", "").strip()
        if not destination:
            return {"ok": False, "error": "destination required"}
        if req.get("from_lat") is None or req.get("from_lon") is None:
            return {"ok": False, "error": "from_lat/from_lon required — share your location"}
        result = await directions(
            float(req["from_lat"]), float(req["from_lon"]), destination,
            req.get("profile", "walking"),
            cfg.services.routing.nominatim_url, cfg.services.routing.osrm_url,
        )
        state.audit.record("esu.directions", {"ok": result.get("ok"), "destination": destination})
        return result

    # ------------------------- device finder -------------------------
    @app.post("/api/finder/scan")
    async def api_finder_scan(req: dict | None = None):
        req = req or {}
        if not cfg.services.finder.enabled:
            return {"ok": False, "error": "finder disabled", "devices": []}
        res = await state.finder.scan(float(req.get("seconds", 4.0)))
        state.audit.record("finder.scan", {"ok": res.ok, "found": len(res.devices)})
        return res.to_dict()

    @app.post("/api/finder/track")
    async def api_finder_track(req: dict):
        if not cfg.services.finder.enabled:
            return {"ok": False, "error": "finder disabled"}
        address = req.get("address", "").strip()
        if not address:
            return {"ok": False, "error": "address required — pick one from /api/finder/scan first"}
        res = await state.finder.start(address, req.get("name", ""))
        state.audit.record("finder.track", {"ok": res.ok, "address": address})
        return res.to_dict()

    @app.post("/api/finder/stop")
    async def api_finder_stop():
        res = await state.finder.stop()
        return res.to_dict()

    @app.get("/api/finder/status")
    async def api_finder_status():
        return state.finder.status().to_dict()

    # -------------------------- ogun 3d -----------------------------
    @app.post("/api/ogun/model")
    async def api_ogun_model(req: dict):
        scad = req.get("scad", "")
        res = await state.cad.build(scad)
        state.audit.record("ogun.model", {"ok": res.ok, "facets": res.facets, "chars": len(scad)})
        return res.to_dict()

    @app.post("/api/ogun/combustion")
    async def api_ogun_combustion(req: dict):
        mixture = req.get("mixture", "")
        res = state.chem.combustion(
            mixture,
            float(req.get("initial_temp_k", 300.0)),
            float(req.get("pressure_atm", 1.0)),
        )
        state.audit.record("ogun.combustion", {"ok": res.ok, "mixture": mixture})
        return res.to_dict()

    @app.post("/api/ogun/circuit")
    async def api_ogun_circuit(req: dict):
        res = await state.circuits.simulate(
            req.get("components", []),
            req.get("source", {}),
            req.get("trace_nodes", []),
            float(req.get("step_us", 1.0)),
            float(req.get("end_ms", 5.0)),
        )
        state.audit.record("ogun.circuit", {"ok": res.ok, "components": len(req.get("components", []))})
        return res.to_dict()

    @app.post("/api/ogun/beam")
    async def api_ogun_beam(req: dict):
        try:
            res = await state.structures.cantilever_beam(
                float(req["length_m"]), float(req["width_m"]), float(req["height_m"]),
                float(req["tip_force_n"]), req.get("material", "aluminum"),
                req.get("youngs_pa"), req.get("poisson"),
                int(req.get("elements_along_length", 20)),
            )
        except (KeyError, TypeError, ValueError) as e:
            return {"ok": False, "error": f"bad beam description: {e}"}
        state.audit.record("ogun.beam", {"ok": res.ok, "material": req.get("material")})
        return res.to_dict()

    @app.post("/api/ogun/rocket")
    async def api_ogun_rocket(req: dict):
        try:
            res = state.aerospace.rocket_flight(
                float(req["total_impulse_ns"]), float(req["burn_time_s"]),
                float(req["propellant_mass_kg"]), float(req["rocket_dry_mass_kg"]),
                float(req["rocket_radius_m"]),
                motor_dry_mass_kg=float(req.get("motor_dry_mass_kg", 1.0)),
                drag_coefficient=float(req.get("drag_coefficient", 0.5)),
                fin_count=int(req.get("fin_count", 4)),
                rail_length_m=float(req.get("rail_length_m", 2.0)),
                inclination_deg=float(req.get("inclination_deg", 85.0)),
            )
        except (KeyError, TypeError, ValueError) as e:
            return {"ok": False, "error": f"bad rocket description: {e}"}
        state.audit.record("ogun.rocket", {"ok": res.ok})
        return res.to_dict()

    @app.post("/api/ogun/sequence")
    async def api_ogun_sequence(req: dict):
        res = state.bio.sequence_report(req.get("sequence", ""))
        state.audit.record("ogun.sequence", {"ok": res.ok, "kind": res.kind})
        return res.to_dict()

    @app.post("/api/ogun/dynamics")
    async def api_ogun_dynamics(req: dict):
        res = state.bio.particle_chain_dynamics(
            int(req.get("particle_count", 8)),
            float(req.get("bond_length_nm", 0.15)),
            float(req.get("bond_strength", 500.0)),
            int(req.get("steps", 2000)),
        )
        state.audit.record("ogun.dynamics", {"ok": res.ok})
        return res.to_dict()

    @app.post("/api/ogun/material")
    async def api_ogun_material(req: dict):
        res = state.materials.search_by_formula(req.get("formula", ""), int(req.get("limit", 5)))
        state.audit.record("ogun.material", {"ok": res.ok, "formula": req.get("formula")})
        return res.to_dict()

    @app.post("/api/drone")
    async def api_drone(req: dict):
        _require_2fa(req, "drone.command")
        action = req.get("action", "")
        res = await state.drone.command(action, req.get("params"))
        state.audit.record("drone.command", {"action": action, "ok": res.get("ok")})
        return res

    @app.post("/api/call")
    async def api_call(req: dict):
        number = req.get("number", "")
        res = await state.calling.place_call(number, req.get("message", ""))
        state.audit.record("call.place", {"number": number, "ok": res.get("ok")})
        return res

    # --------------------------- sensors --------------------------
    @app.post("/api/sensors/ingest")
    async def api_sensors_ingest(req: dict):
        r = Reading(
            source=req.get("source", "unknown"),
            wifi=req.get("wifi", []),
            ble=req.get("ble", []),
            mag_uT=req.get("mag_uT"),
            sound_db=req.get("sound_db"),
            motion=req.get("motion"),
            lat=req.get("lat"),
            lon=req.get("lon"),
        )
        state.fusion.ingest(r)
        state.trackers.observe(r.ble, r.lat, r.lon)
        state.last_surveillance = scan_report(r.wifi, r.ble)

        events: list[dict] = [{"type": "sensors.update", "source": r.source}]
        if not state.last_surveillance["clear"]:
            events.append({"type": "safety.surveillance", "report": state.last_surveillance})
        if r.lat is not None and state.geofence.zones:
            geo = state.geofence.evaluate(r.lat, r.lon)
            if geo["alerts"]:
                events.append({"type": "safety.geofence", "alerts": geo["alerts"]})
        for e in events:
            await state.bus.publish(e)
        return {"ok": True, "surveillance_clear": state.last_surveillance["clear"]}

    @app.get("/api/sensors")
    async def api_sensors():
        return state.fusion.snapshot()

    # --------------------------- cameras --------------------------
    @app.get("/api/cameras")
    async def api_cameras():
        return {"cameras": state.cameras.list()}

    @app.post("/api/cameras")
    async def api_cameras_add(req: dict):
        name, url = req.get("name", "").strip(), req.get("url", "").strip()
        if not name or not url:
            return {"ok": False, "error": "name and url required"}
        cam = state.cameras.add(name, url, req.get("kind", "snapshot"), req.get("note", ""))
        state.audit.record("camera.add", {"name": name, "kind": cam.kind})
        return {"ok": True, "camera": cam.to_dict()}

    @app.delete("/api/cameras/{name}")
    async def api_cameras_del(name: str):
        return {"ok": state.cameras.remove(name)}

    @app.post("/api/cameras/{name}/analyze")
    async def api_cameras_analyze(name: str, req: dict):
        snap = await state.cameras.snapshot_b64(name)
        if not snap.get("ok"):
            return snap
        prompt = req.get("prompt") or "Describe what this camera sees. Flag anything relevant to safety."
        analysis = await state.provider.chat(
            cfg.models.vision_model,
            [ChatMessage("user", prompt)], images=[snap["image_b64"]],
        )
        return {"ok": True, "camera": name, "analysis": analysis}

    # ---------------------------- push ----------------------------
    @app.get("/api/push/publickey")
    async def api_push_key():
        if not (state.push and state.push.enabled):
            return {"enabled": False}
        return {"enabled": True, "public_key": cfg.services.push.vapid_public}

    @app.post("/api/push/subscribe")
    async def api_push_subscribe(req: dict):
        if not (state.push and state.push.enabled):
            return {"ok": False, "error": "push not configured"}
        return state.push.subscribe(req.get("subscription", req))

    @app.post("/api/push/unsubscribe")
    async def api_push_unsubscribe(req: dict):
        if not state.push:
            return {"ok": False, "error": "push not configured"}
        return state.push.unsubscribe(req.get("endpoint", ""))

    @app.post("/api/push/test")
    async def api_push_test():
        await _alert_push("BODDOS", "Test notification — push is working.")
        return {"ok": True, "subscriptions": state.push.count() if state.push else 0}

    # --------------------------- safety ---------------------------
    @app.post("/api/safety/duress")
    async def api_duress(req: dict):
        result = state.duress.trigger(req.get("note", ""), req.get("location"))
        delivery = await state.notifier.deliver_all(result["alerts"])
        await _alert_push("BODDOS duress alert", req.get("note", "") or "I may need help",
                          {"location": req.get("location")})
        result["delivery"] = delivery
        state.audit.record("safety.duress", {"note": req.get("note", ""), "delivery": delivery})
        await _broadcast(result["event"])
        return result

    @app.post("/api/safety/clear")
    async def api_duress_clear():
        state.audit.record("safety.duress_clear", {})
        return state.duress.clear()

    @app.get("/api/safety/status")
    async def api_safety_status():
        return {
            "duress": state.duress.snapshot(),
            "tracker_suspects": state.trackers.suspects(),
            "deadman": state.deadman.status(),
            "surveillance": state.last_surveillance,
        }

    @app.get("/api/safety/trackers")
    async def api_trackers():
        return {"suspects": state.trackers.suspects()}

    @app.post("/api/safety/exposure")
    async def api_exposure(req: dict):
        ids = req.get("identifiers", [])
        if req.get("plan"):
            return await state.exposure.plan(ids)
        return state.exposure.surfaces_for(ids)

    @app.post("/api/safety/deadman/arm")
    async def api_deadman_arm(req: dict):
        res = state.deadman.arm(req.get("label", "check-in"),
                                float(req.get("minutes", 30)),
                                bool(req.get("recurring", False)))
        state.audit.record("deadman.arm", res)
        return res

    @app.post("/api/safety/deadman/checkin")
    async def api_deadman_checkin(req: dict):
        return state.deadman.check_in(req.get("label", "check-in"))

    @app.post("/api/safety/deadman/cancel")
    async def api_deadman_cancel(req: dict):
        return state.deadman.cancel(req.get("label", "check-in"))

    @app.get("/api/safety/deadman")
    async def api_deadman_status():
        return {"checkins": state.deadman.status()}

    @app.get("/api/safety/surveillance")
    async def api_surveillance():
        return state.last_surveillance

    @app.post("/api/safety/breach")
    async def api_breach(req: dict):
        return await check_password(req.get("password", ""))

    @app.get("/api/safety/geofence")
    async def api_geofence(lat: float, lon: float):
        return state.geofence.evaluate(lat, lon)

    # -------------------------- security --------------------------
    @app.get("/api/security/status")
    async def api_security_status():
        intact, checked = state.audit.verify_chain()
        return {
            "require_auth": state.client_auth.require,
            "tls_enabled": cfg.security.tls_enabled,
            "mesh_signing": True,
            "two_factor": bool(cfg.security.require_2fa and cfg.security.totp_secret),
            "audit": {"intact": intact, "entries": checked, "recent": state.audit.tail(20)},
            "vault_unlocked": state.vault.unlocked,
        }

    @app.get("/api/security/vault")
    async def api_vault_keys():
        if not state.vault.unlocked:
            return {"unlocked": False, "keys": []}
        try:
            return {"unlocked": True, "keys": sorted(state.vault.load().keys())}
        except Exception as e:
            return {"unlocked": True, "error": str(e), "keys": []}

    @app.post("/api/security/vault/set")
    async def api_vault_set(req: dict):
        _require_2fa(req, "vault.set")
        if not state.vault.unlocked:
            return {"ok": False, "error": "vault locked (set BODDOS_VAULT_PASSPHRASE)"}
        state.vault.set(req.get("name", ""), req.get("value"))
        state.audit.record("vault.set", {"name": req.get("name", "")})
        return {"ok": True}

    @app.get("/api/security/2fa")
    async def api_2fa_status():
        return {"enabled": bool(cfg.security.require_2fa and cfg.security.totp_secret),
                "configured": bool(cfg.security.totp_secret)}

    @app.post("/api/security/2fa/verify")
    async def api_2fa_verify(req: dict):
        if not cfg.security.totp_secret:
            return {"ok": False, "error": "no TOTP secret configured"}
        return {"ok": totp.verify(cfg.security.totp_secret, str(req.get("code", "")))}

    # --------------------------- websocket ------------------------
    @app.websocket("/ws")
    async def ws(websocket: WebSocket):
        token = websocket.query_params.get("token")
        if state.client_auth.require and not state.client_auth.check(None, token):
            await websocket.close(code=1008)
            return
        await websocket.accept()
        q = state.bus.subscribe()
        try:
            await websocket.send_json({"type": "hello", "node": state.registry.me.id})
            while True:
                event = await q.get()
                await websocket.send_json(event)
        except WebSocketDisconnect:
            pass
        finally:
            state.bus.unsubscribe(q)

    # ----------------------------- ui -----------------------------
    @app.get("/health")
    async def health():
        return {"ok": True, "node": state.registry.me.id, "role": cfg.node.role,
                "models": state.local_models, "auth_required": state.client_auth.require}

    @app.get("/api/ui-config")
    async def ui_config():
        return {
            "assistant_name": cfg.assistant.name,
            "wake_words": [w.lower() for w in cfg.assistant.wake_words],
            "greeting": cfg.assistant.greeting,
            "vision_model": cfg.models.vision_model,
            "push_enabled": bool(state.push and state.push.enabled),
            "tts_enabled": cfg.voice.enabled,
            "tts_voice": cfg.voice.tts_voice,
        }

    @app.get("/")
    async def index():
        idx = UI_DIR / "index.html"
        if idx.exists():
            return FileResponse(idx)
        return JSONResponse({"ok": True, "note": "BODDOS node up; UI not found"})

    @app.get("/sw.js")
    async def service_worker():
        # Served at root so its scope covers the whole app (required for push).
        sw = UI_DIR / "sw.js"
        if sw.exists():
            return FileResponse(sw, media_type="application/javascript")
        return JSONResponse({"error": "no service worker"}, status_code=404)

    if UI_DIR.exists():
        app.mount("/ui", StaticFiles(directory=UI_DIR), name="ui")

    return app
