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
| OS agent for *your own* laptops | ✅ core | Allowlisted shell + web fetch/parse |
| Weather-aware planning | ✅ core | Open-Meteo, no API key |
| Live translation → English | ✅ core | Uses your local model |
| Environmental sensing (ESP32) | ✅ core | Wi-Fi/BLE discovery, magnetometer, mic, motion |
| Sensor-fusion "situational awareness" | ✅ core | Real physics only — not X-ray vision |
| Panic / duress mode + check-ins | ✅ safety | Trusted-contact alerts, location share |
| Dead-man's switch / check-in timer | ✅ safety | Miss a check-in → auto duress alert |
| "Am I being tracked?" detection | ✅ safety | Rogue BLE / AirTag-style follower detection |
| Surveillance scan | ✅ safety | Evil-twin AP + camera/tracker vendor fingerprint |
| Geofenced safe zones | ✅ safety | Alert on leaving safe / entering danger zones |
| Password breach check | ✅ safety | k-anonymity, only a hash prefix leaves the device |
| Your-own OSINT exposure audit | ✅ safety | What's public about *you*, so you can lock it down |
| Hardened transport | ✅ security | Signed mesh, client auth, TLS, rate-limit, audit, vault |
| Drone control (your drones) | 🔌 adapter | MAVLink-style stub, bring your own link |
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

## Quick start (one node)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
cp config/boddos.example.yaml config/boddos.yaml   # edit peers + trusted contacts
python -m boddos --config config/boddos.yaml
```

Then open `http://<this-machine-ip>:8787/` on your phone (same network).

See [`docs/DEPLOY.md`](docs/DEPLOY.md) for the full 3-machine + ESP32 setup and
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for how the pieces fit.
