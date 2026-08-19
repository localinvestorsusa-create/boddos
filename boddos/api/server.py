"""FastAPI application factory for a BODDOS node.

Brings together: mesh registry/router, local model provider, OS agent, services,
sensor fusion, and the safety modules — behind one HTTP + WebSocket API that the
phone PWA and peer nodes talk to.
"""
from __future__ import annotations

import asyncio
import contextlib
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from ..config import Config
from ..models import OllamaProvider
from ..models.base import ChatMessage
from ..agent import OSAgent, fetch_url
from ..services import get_forecast, translate_to_english, DroneAdapter, CallingAdapter
from ..sensors import SensorFusion, Reading
from ..safety import DuressManager, TrackerDetector, ExposureAudit
from ..mesh import NodeInfo, MeshRegistry, Router
from ..mesh.bus import EventBus

UI_DIR = Path(__file__).resolve().parent.parent / "ui"

ADVISOR_SYSTEM = (
    "You are BODDOS, a private personal advisor and safety assistant running on "
    "the user's own machines. Be concise, practical, and honest. You help the "
    "user protect themselves and get things done. You do not help surveil, "
    "deceive, or manipulate other people."
)


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
        self.fusion = SensorFusion()
        self.duress = DuressManager(cfg.safety)
        self.trackers = TrackerDetector(cfg.safety.tracker_follow_threshold)
        self.exposure = ExposureAudit(self.provider, cfg.services.translate.model)
        self.bus = EventBus()
        self.local_models: list[str] = []

    def hello_payload(self) -> dict:
        me = self.registry.me
        me.models = self.local_models
        return me.to_dict()


def _check_psk(state: NodeState, psk: str | None) -> None:
    if psk != state.cfg.mesh.psk:
        raise HTTPException(status_code=401, detail="bad or missing mesh PSK")


def build_app(cfg: Config) -> FastAPI:
    state = NodeState(cfg)

    # ---- background: refresh local models, greet peers, heartbeat ----
    async def _refresh_models() -> None:
        state.local_models = await state.provider.list_models()

    async def _greet(peer: str) -> None:
        try:
            async with httpx.AsyncClient(timeout=5.0) as c:
                await c.post(
                    f"{peer.rstrip('/')}/mesh/hello",
                    json=state.hello_payload(),
                    headers={"X-Boddos-PSK": cfg.mesh.psk},
                )
        except Exception:
            pass

    async def _heartbeat_loop() -> None:
        while True:
            await _refresh_models()
            for peer in cfg.mesh.peers:
                await _greet(peer)
            await asyncio.sleep(cfg.mesh.heartbeat_seconds)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await _refresh_models()
        task = asyncio.create_task(_heartbeat_loop())
        try:
            yield
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    app = FastAPI(title="BODDOS", version="0.1.0", lifespan=lifespan)
    app.state.node = state

    # ---------------------------- mesh ----------------------------
    @app.post("/mesh/hello")
    async def mesh_hello(payload: dict, x_boddos_psk: str | None = Header(default=None)):
        _check_psk(state, x_boddos_psk)
        state.registry.from_hello(payload)
        return {"ok": True, "me": state.hello_payload()}

    @app.get("/mesh/nodes")
    async def mesh_nodes():
        return {"nodes": [n.to_dict() for n in state.registry.all_nodes()]}

    @app.post("/mesh/event")
    async def mesh_event(event: dict, x_boddos_psk: str | None = Header(default=None)):
        _check_psk(state, x_boddos_psk)
        await state.bus.publish({**event, "_relayed": True})
        return {"ok": True}

    async def _broadcast(event: dict) -> None:
        await state.bus.publish(event)
        if cfg.safety.broadcast:
            for peer in cfg.mesh.peers:
                try:
                    async with httpx.AsyncClient(timeout=4.0) as c:
                        await c.post(f"{peer.rstrip('/')}/mesh/event", json=event,
                                     headers={"X-Boddos-PSK": cfg.mesh.psk})
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

        # Route — but never forward more than one hop.
        target = state.router.select_model_node(model, state.local_models)
        if target.id != state.registry.me.id and not x_boddos_forwarded:
            try:
                async with httpx.AsyncClient(timeout=180.0) as c:
                    r = await c.post(
                        f"{target.url}/api/chat",
                        json={"model": model, "messages": [m.to_dict() for m in msgs]},
                        headers={"X-Boddos-Forwarded": "1", "X-Boddos-PSK": cfg.mesh.psk},
                    )
                    r.raise_for_status()
                    data = r.json()
                    data["served_by"] = target.id
                    return data
            except Exception as e:
                # Fall through to local if the peer is unreachable.
                reply = await state.provider.chat(model, msgs)
                return {"reply": reply, "served_by": state.registry.me.id,
                        "note": f"peer {target.id} unreachable ({e}); served locally"}

        reply = await state.provider.chat(model, msgs)
        return {"reply": reply, "served_by": state.registry.me.id, "model": model}

    # ---------------------------- agent ---------------------------
    @app.post("/api/agent/run")
    async def api_agent_run(req: dict):
        res = await state.agent.run(req.get("command", ""), confirm=bool(req.get("confirm")))
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
        return await state.drone.command(req.get("action", ""), req.get("params"))

    @app.post("/api/call")
    async def api_call(req: dict):
        return await state.calling.place_call(req.get("number", ""), req.get("message", ""))

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
        await state.bus.publish({"type": "sensors.update", "source": r.source})
        return {"ok": True}

    @app.get("/api/sensors")
    async def api_sensors():
        return state.fusion.snapshot()

    # --------------------------- safety ---------------------------
    @app.post("/api/safety/duress")
    async def api_duress(req: dict):
        result = state.duress.trigger(req.get("note", ""), req.get("location"))
        await _broadcast(result["event"])
        return result

    @app.post("/api/safety/clear")
    async def api_duress_clear():
        return state.duress.clear()

    @app.get("/api/safety/status")
    async def api_safety_status():
        return {"duress": state.duress.snapshot(),
                "tracker_suspects": state.trackers.suspects()}

    @app.get("/api/safety/trackers")
    async def api_trackers():
        return {"suspects": state.trackers.suspects()}

    @app.post("/api/safety/exposure")
    async def api_exposure(req: dict):
        ids = req.get("identifiers", [])
        if req.get("plan"):
            return await state.exposure.plan(ids)
        return state.exposure.surfaces_for(ids)

    # --------------------------- websocket ------------------------
    @app.websocket("/ws")
    async def ws(websocket: WebSocket):
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
                "models": state.local_models}

    @app.get("/")
    async def index():
        idx = UI_DIR / "index.html"
        if idx.exists():
            return FileResponse(idx)
        return JSONResponse({"ok": True, "note": "BODDOS node up; UI not found"})

    if UI_DIR.exists():
        app.mount("/ui", StaticFiles(directory=UI_DIR), name="ui")

    return app
