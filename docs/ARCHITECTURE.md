# BODDOS architecture

BODDOS is a small mesh of identical **nodes** (one per machine) plus edge devices
(your phone and ESP32). Every node runs the same code; config decides its role.

```
  Phone PWA ─────┐            mesh (HTTP + PSK, WebSocket events)
                 ▼        ┌───────────────┬───────────────┐
  ESP32 ──ingest──▶  MacBook(host)  ◀──▶  ZBook(host)   HP(edge)
                    ▲  models         failover         tools/sensors
                    │
             all inference local (Ollama)
```

## Node internals

Each node (`boddos/`) is a FastAPI app (`api/server.py`) composed of:

| Module | Responsibility |
|--------|----------------|
| `mesh/node.py` | Node identity + in-memory peer registry (TTL'd heartbeats) |
| `mesh/router.py` | Pick the best node to serve a model request |
| `mesh/bus.py` | WebSocket event fan-out (safety/sensor/mesh events) |
| `models/` | Local model provider (Ollama) + pluggable "Assistant" registry |
| `agent/` | Allowlisted OS agent + web fetch/parse (this machine only) |
| `services/` | Weather, translation, drone/calling adapters, alert delivery (`notify.py`) |
| `sensors/fusion.py` | Ingest ESP32/phone readings → situational-awareness snapshot |
| `safety/` | Duress, dead-man's switch, tracker/surveillance/geofence/breach, exposure |
| `security/` | Mesh signing, client auth, rate-limit, audit, vault, TLS, TOTP 2FA |
| `ui/` | Phone PWA served by every node (chat, awareness, safety, tools, voice) |

## How the mesh forms

1. On startup each node greets its configured `peers` with `POST /mesh/hello`
   (carrying its id/role/RAM/GPU/models), authenticated by the shared `mesh.psk`.
2. Heartbeats repeat every `heartbeat_seconds`; peers age out after 3× that.
3. `GET /mesh/nodes` returns the live view from any node.

## How a chat request is served

1. Phone → `POST /api/chat` on whatever node it's connected to (usually the
   nearest / the MacBook).
2. `Router.select_model_node()` prefers the local node if it has the model, else
   the highest-capacity host peer that has it.
3. If the target is a peer, the node forwards **one hop** (guarded by an
   `X-Boddos-Forwarded` header) and returns the peer's answer, tagged
   `served_by`. If the peer is unreachable it falls back to local.

With the default topology, the MacBook is primary host and the ZBook is failover:
if the MacBook is down, the phone connects to the ZBook and the same UI works.

## Events

Safety and sensor events publish to the local `EventBus` and, when
`safety.broadcast` is on, relay to peers via `POST /mesh/event`. The phone holds a
`/ws` WebSocket, so a duress trigger on any node lights up every screen.

## Extending it

- **New model backend:** implement the `ModelProvider` protocol (`models/base.py`)
  — e.g. a llama.cpp server or MLX on the MacBook — and swap it in `NodeState`.
- **New service:** add an adapter under `services/` and an endpoint in
  `api/server.py`.
- **New sensor:** POST more fields to `/api/sensors/ingest`; extend
  `sensors/fusion.py` to derive observations from them.
- **Add a machine:** install BODDOS, give it a unique `node.id`, list it in the
  others' `peers` (or vice-versa), share the `mesh.psk`. It joins on next heartbeat.
