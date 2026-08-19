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
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, Header, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from ..config import Config
from ..models import OllamaProvider
from ..models.base import ChatMessage
from ..agent import OSAgent, fetch_url
from ..services import get_forecast, translate_to_english, DroneAdapter, CallingAdapter
from ..services.notify import Notifier
from ..sensors import SensorFusion, Reading
from ..safety import (
    DuressManager, TrackerDetector, ExposureAudit, DeadMansSwitch,
    scan_report, check_password, GeoFence, Zone,
)
from ..security import MeshAuth, ClientAuth, AuditLog, RateLimiter, SecretVault, totp
from ..mesh import NodeInfo, MeshRegistry, Router
from ..mesh.bus import EventBus

UI_DIR = Path(__file__).resolve().parent.parent / "ui"

ADVISOR_SYSTEM = (
    "You are BODDOS, a private personal advisor and safety assistant running on "
    "the user's own machines. Be concise, practical, and honest. You help the "
    "user protect themselves and get things done. You do not help surveil, "
    "deceive, or manipulate other people."
)

# Paths reachable without a client token (so the UI can load and prompt for one).
_AUTH_EXEMPT_PREFIXES = ("/health", "/ui", "/manifest")


class NodeState:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        me = NodeInfo(
            id=cfg.node.id,
            name=cfg.node.name,
            role=cfg.node.role,
            url=cfg.node.advertise_url or f"http://127.0.0.1:{cfg.node.bind_port}",
            ram_gb=cfg.models.ram_gb,
            has_gpu=cfg.models.has_gpu,
        )
        ttl = cfg.mesh.heartbeat_seconds * 3
        self.registry = MeshRegistry(me, ttl=ttl)
        self.router = Router(self.registry)
        self.provider = OllamaProvider(cfg.models.ollama_url)
        self.agent = OSAgent(cfg.agent)
        self.drone = DroneAdapter(cfg.services.drone)
        self.calling = CallingAdapter(cfg.services.calling)
        self.notifier = Notifier(cfg.services.notify)
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
                await c.post(f"{peer.rstrip('/')}/mesh/hello", content=body, headers=headers)
        except Exception:
            pass

    async def _heartbeat_loop() -> None:
        while True:
            await _refresh_models()
            for peer in cfg.mesh.peers:
                await _greet(peer)
            await asyncio.sleep(cfg.mesh.heartbeat_seconds)

    async def _deadman_loop() -> None:
        while True:
            for c in state.deadman.due():
                res = state.duress.trigger(note=f"missed check-in: {c.label}",
                                           location=state.duress.state.last_location)
                delivery = await state.notifier.deliver_all(res["alerts"])
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

    @app.post("/api/chat")
    async def api_chat(req: dict, x_boddos_forwarded: str | None = Header(default=None)):
        model = req.get("model") or cfg.models.default_model
        if "messages" in req:
            msgs = [ChatMessage(m["role"], m["content"]) for m in req["messages"]]
        else:
            msgs = [ChatMessage("user", req.get("prompt", ""))]
        if not any(m.role == "system" for m in msgs):
            msgs.insert(0, ChatMessage("system", ADVISOR_SYSTEM))

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

    # --------------------------- safety ---------------------------
    @app.post("/api/safety/duress")
    async def api_duress(req: dict):
        result = state.duress.trigger(req.get("note", ""), req.get("location"))
        delivery = await state.notifier.deliver_all(result["alerts"])
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

    @app.get("/")
    async def index():
        idx = UI_DIR / "index.html"
        if idx.exists():
            return FileResponse(idx)
        return JSONResponse({"ok": True, "note": "BODDOS node up; UI not found"})

    if UI_DIR.exists():
        app.mount("/ui", StaticFiles(directory=UI_DIR), name="ui")

    return app
