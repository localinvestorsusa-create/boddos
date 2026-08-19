# CLAUDE.md — working in the BODDOS repo

BODDOS is a private, self-hosted personal AI + safety assistant that runs as a
mesh of identical nodes across the user's own machines, operated from a phone
(PWA) and an ESP32 sensor node. Read `README.md` and `docs/` first.

## Scope boundaries (important)

This project is **defensive** and has hard limits documented in
`docs/SECURITY.md`. Do **not** add: covert surveillance of other people, remote
reading of strangers' vitals/emotions, third-party OSINT dossiers, impersonation,
or physically-impossible sensing claims. New "spy on others" features are out of
scope; new features that protect the operator are welcome.

## Layout

- `boddos/mesh/` — node identity, peer registry, one-hop model router, event bus
- `boddos/models/` — local model provider (Ollama) + `ModelProvider` protocol
- `boddos/agent/` — allowlisted OS agent (own machine) + web fetch
- `boddos/services/` — weather, translate, drone/calling adapters, `notify.py`
- `boddos/sensors/` — ESP32/phone reading fusion
- `boddos/safety/` — duress, deadman, trackers, surveillance, geofence, breach, exposure
- `boddos/security/` — mesh HMAC signing, client auth, ratelimit, audit, vault, tls, totp
- `boddos/api/server.py` — FastAPI app factory wiring it all together
- `boddos/ui/` — phone PWA (vanilla JS, no build step)
- `firmware/esp32/` — Arduino sensor sketch
- `deploy/` — systemd unit + launchd plist; `Dockerfile` at root

## Conventions

- Python 3.10+, FastAPI, async. Type hints, `from __future__ import annotations`.
- Mesh-to-mesh calls are HMAC-signed (`security/auth.py`); never send the PSK
  in a header. Sensitive actions record to the hash-chained audit log and may
  require TOTP when 2FA is enabled.
- Keep new features honest about hardware limits and label heuristics as such.

## Dev commands

```bash
python3 -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"
python -m pytest -q            # test suite
python -m boddos --config config/boddos.yaml   # run a node
python -m boddos --new-totp    # provision a 2FA secret
```

CI runs `pytest` on 3.10 and 3.12 (`.github/workflows/ci.yml`). Keep it green.
