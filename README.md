# BODDOS

**B**ackbone for **O**n-**D**evice **D**istributed **O**perations & **S**afety.

A private, self-hosted personal AI + safety assistant that runs across *your own*
machines. Heavy AI models run on your laptops; you operate the whole thing from
your phone (a web app) and an ESP32 sensor node. Nothing is sent to a cloud you
don't control.

> BODDOS is built to protect **you**. It is deliberately **not** a tool for
> covertly surveilling or manipulating other people. See
> [`docs/SECURITY.md`](docs/SECURITY.md) for the explicit boundaries — some
> commonly-requested "spy" features are excluded on purpose, both because they
> are illegal in most places and because they are not what this project is for.

## What it does (honestly scoped)

| Area | Status | Notes |
|------|--------|-------|
| Distributed mesh across your machines | ✅ core | Nodes discover each other, share load |
| Local LLM advisor ("Assistant") | ✅ core | Ollama-backed, any local model, pluggable |
| Always-on live conversation | ✅ core | "Hey Ori" wake word → listen → stream → speak |
| Streaming replies + model pulling | ✅ core | Token-by-token SSE; pull models from the UI |
| Camera vision (phone / glasses / external) | ✅ core | Local multimodal model; add cameras by URL |
| Lock-screen alerts (Web Push) | ✅ safety | Duress reaches the phone even when closed |
| OS agent for *your own* laptops | ✅ core | Allowlisted shell + web fetch/parse |
| Weather-aware planning | ✅ core | Open-Meteo, no API key |
| Live translation → English | ✅ core | Uses your local model; hands-free voice input |
| Hands-free voice | ✅ core | Speak to the advisor / translator (Web Speech API) |
| Environmental sensing (ESP32) | ✅ core | Wi-Fi/BLE discovery, magnetometer, mic, motion |
| Sensor-fusion "situational awareness" | ✅ core | Real physics only — not X-ray vision |
| Panic / duress mode + check-ins | ✅ safety | Trusted-contact alerts, location share |
| Alert delivery | ✅ safety | Webhook / email (SMTP) / SMS gateway |
| Dead-man's switch / check-in timer | ✅ safety | Miss a check-in → auto duress alert |
| "Am I being tracked?" detection | ✅ safety | Rogue BLE / AirTag-style follower detection |
| Surveillance scan | ✅ safety | Evil-twin AP + camera/tracker vendor fingerprint |
| Geofenced safe zones | ✅ safety | Alert on leaving safe / entering danger zones |
| Password breach check | ✅ safety | k-anonymity, only a hash prefix leaves the device |
| Your-own OSINT exposure audit | ✅ safety | What's public about *you*, so you can lock it down |
| Hardened transport | ✅ security | Signed mesh, client auth, TLS, rate-limit, audit, vault |
| TOTP 2FA | ✅ security | Second factor on agent / drone / vault actions |
| Drone control (your drones) | ✅ adapter | Real MAVLink backend (`boddos[mavlink]`) + queue fallback |
| Calling | 🔌 adapter | Provider stub |

## What it does NOT do

See [`docs/SECURITY.md`](docs/SECURITY.md). Short version: no covert surveillance
of other people, no remote reading of strangers' vitals/emotions, no OSINT
dossiers on third parties, no voice-impersonation. And no physically-impossible
claims (a phone + ESP32 cannot see through walls or read a stranger's heartbeat
from across a room).

## Topology (default)

```
                 ┌─────────────┐        ┌─────────────┐
   Phone (PWA) ──┤  MacBook    │◀──────▶│   ZBook     │
        ▲        │  32 GB      │  mesh  │   32 GB     │
        │        │  PRIMARY    │        │  FAILOVER   │
   ESP32 sensor  │  model host │        │  model host │
        │        └──────┬──────┘        └─────────────┘
        └──── ingest ───┘        ▲
                                 │
                          ┌──────┴──────┐
                          │  HP 8 GB    │
                          │  edge/tools │
                          └─────────────┘
```

## Install

**One line per computer** (macOS / Linux) — clones, installs, offers to set up
Ollama + models, and writes a config with fresh secrets:

```bash
curl -fsSL https://raw.githubusercontent.com/localinvestorsusa-create/boddos/claude/personal-security-assistant-yi36rv/install.sh | bash
```

Windows (PowerShell):

```powershell
irm https://raw.githubusercontent.com/localinvestorsusa-create/boddos/claude/personal-security-assistant-yi36rv/install.ps1 | iex
```

**Phone, tablet, smart glasses:** no download — open the running node's URL in the
browser and **Add to Home Screen**. It installs as an app (that's the PWA).

Manual, if you prefer:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
cp config/boddos.example.yaml config/boddos.yaml   # edit peers + trusted contacts
python -m boddos --config config/boddos.yaml
```

Then open `http://<this-machine-ip>:8787/` on your phone (same network).

See [`docs/USAGE.md`](docs/USAGE.md) for how to use Ori across all your devices,
[`docs/DEPLOY.md`](docs/DEPLOY.md) for the full 3-machine + ESP32 setup, and
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for how the pieces fit.

## New frontend: the Orun shell

`frontend/` is a from-scratch React + Three.js UI: a persistent, draggable
geometric globe (binary strip above its equator, two odu-style strips below)
that vibrates with your mic while you talk and with the assistant's reply
while it speaks, plus three sections wired to real backend tools:

- **Orunmila** — chat (`/api/chat/stream`), continuous "hey ori" wake-word
  voice loop, and a screen-control panel (screenshot → local vision model →
  click, gated behind `screen.enabled` + a per-click confirm).
- **Esu Pathfinder** — turn-by-turn directions on a Leaflet/OSM map
  (Nominatim + OSRM) and a camera "lookout" that describes hazards via the
  local vision model.
- **Ogun 3D** — describe a part and get real OpenSCAD + a rendered STL
  preview; check a combustion mixture with Cantera; sketch an RC/RL/RLC
  circuit and simulate it with ngspice; solve a cantilever beam with
  CalculiX (cross-checked against closed-form beam theory); fly a rocket
  with RocketPy; read a DNA/protein sequence or run a toy molecular
  dynamics simulation with Biopython/OpenMM; look up real material
  properties via the Materials Project (needs a free API key).

It talks to the same backend above over `/api`, proxied in dev.

```bash
# system deps for screen control + Ogun 3D (optional — each section
# degrades to a clear "disabled"/"unavailable" message without these)
apt install openscad xvfb ngspice libngspice0-dev calculix-ccx
pip install -e ".[screen,ogun]"

# terminal 1 — backend
python -m boddos --config config/boddos.yaml --port 8000

# terminal 2 — frontend
cd frontend && npm install && npm run dev   # http://localhost:5173
```

The backend's default port is 8787 (see Install above); the frontend dev
proxy in `frontend/vite.config.ts` expects it on 8000, so pass `--port 8000`
or edit the proxy target to match. The old `boddos/ui/` PWA still works
unchanged and is still served at `/` by the backend directly.
