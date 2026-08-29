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
| Hardware auto-detection | ✅ core | CPU/RAM/GPU detected at startup — picks a model tier for you, no guessing |
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
| Smart home (TP-Link Kasa) | ✅ core | Discover + control lights/plugs on your own LAN — `boddos[smarthome]` |
| Planner (calendar / alarms / tasks) | ✅ core | Local SQLite, no cloud calendar account |
| Daily news briefing | ✅ core | DuckDuckGo headlines, curated by your local model — `boddos[news]` |

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
curl -fsSL https://raw.githubusercontent.com/localinvestorsusa-create/boddos/claude/delete-boddos-folder-t8lh8m/install.sh | bash
```

Windows (PowerShell):

```powershell
irm https://raw.githubusercontent.com/localinvestorsusa-create/boddos/claude/delete-boddos-folder-t8lh8m/install.ps1 | iex
```

**Phone, tablet, smart glasses:** no download — open the running node's URL in the
browser and **Add to Home Screen**. It installs as an app (that's the PWA).

Manual, if you prefer (macOS/Linux):

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
cp config/boddos.example.yaml config/boddos.yaml   # edit peers + trusted contacts
python -m boddos --config config/boddos.yaml
```

Windows (PowerShell) — same steps, different syntax: no `&&` (use separate
lines or `;`), `.venv\Scripts\Activate.ps1` instead of `source ...`, and
`config/boddos.yaml` gets created for you on first run if you skip the
`copy` step:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .
python -m boddos --config config/boddos.yaml
```

Then open `http://<this-machine-ip>:8787/` on your phone (same network).

See [`docs/USAGE.md`](docs/USAGE.md) for how to use Ori across all your devices,
[`docs/DEPLOY.md`](docs/DEPLOY.md) for the full 3-machine + ESP32 setup, and
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for how the pieces fit.

## Adding a second machine

**From the UI (easiest):** open Orunmila's Mesh tab on both machines. On
one, click **"Get a code for this machine"** — it shows a 6-digit code
and this machine's auto-detected address. On the other, type that address
and code into **"connect to another"** and click **Connect**. Both nodes
adopt a shared `mesh.psk` and show up in each other's live node list
immediately — no YAML editing, no copying a PSK by hand, no guessing an
IP. The code is single-use and expires after 10 minutes
(`/api/mesh/pair/start` + `/api/mesh/pair/redeem` under the hood — see
`boddos/api/server.py`). This takes effect for the current run; add the
peer under `mesh.peers` in `config/boddos.yaml` by hand to keep it across
a restart.

**From the CLI**, the older one-shot token still works too. On the
machine that's already running:

```bash
python -m boddos --config config/boddos.yaml --join-code
```

That prints a token and a ready-to-paste command. Run it on the new
machine and the installer decodes the token straight into that node's
`mesh.psk`/`mesh.peers` — no manual YAML editing, matching secrets typed
by hand, or guessing an IP:

```bash
BODDOS_JOIN=bd1.XXXXX curl -fsSL <the install.sh URL you used> | bash -s -- --join $BODDOS_JOIN
```

(To do it by hand instead: match `mesh.psk` on both nodes and put each
one's `advertise_url` in the other's `mesh.peers`.)

Either way, each node shows up in the other's registry — visible live in
Orunmila's mesh panel, or via `GET /mesh/nodes` — with its auto-detected
RAM/GPU and whatever models it has pulled. `advertise_url` auto-detects
this machine's real LAN IP (`boddos/netutil.py`) when left blank, so a
fresh `boddos.yaml` from the example just works without editing it first.
`/api/chat` already routes a request to whichever peer actually has the
requested model. For machines that aren't on the same LAN, put
[Headscale](https://github.com/juanfont/headscale) (or Tailscale) between
them first so `advertise_url` is reachable at all.

## New frontend: the Orun shell

`frontend/` is a from-scratch React + Three.js UI: a persistent, draggable
geometric globe (binary strip above its equator, two odu-style strips below)
that vibrates with your mic while you talk and with the assistant's reply
while it speaks, plus three sections wired to real backend tools. Ogun 3D's
seven labs and Orunmila's five support panels are each a tab strip
(`TabNav.tsx`) rather than a single long scroll:

- **Orunmila** — chat (`/api/chat/stream`), continuous "hey ori" wake-word
  voice loop, the **skill portal** ("new wishes"): pull a GitHub repo,
  compress it with RepoMix, ask Ori to draft a small Python skill from it
  (or write one by hand), run it past an AST + Bandit security gate, and
  save it as a **muscle-memory tool** — a manifest-driven card, styled in
  the app's own theme, that runs the saved script directly via subprocess
  with one click and zero further model calls; a screen-control panel
  (screenshot → local vision model → click, gated behind `screen.enabled`)
  for manual point-and-click, plus a `drive_screen` voice/chat tool that
  autonomously works toward a goal across several clicks at full speed
  (see "Voice control" below); a mesh panel showing this machine's auto-detected
  hardware plus every peer node and its specs live, and a **device finder**
  — scan for nearby Bluetooth devices you own (earbuds, a tag) and track
  one with a "getting warmer/colder" proximity readout from its real BLE
  signal strength.
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

### Voice control: every action is a tool call

Orunmila's chat isn't just talk — `/api/chat/stream` runs a real agentic
tool-calling loop (`boddos/tools/registry.py`) against every action this
node can take: build a 3D model, check combustion, simulate a circuit/beam/
rocket, analyze a sequence, get directions, scan for a lost device, run a
muscle-memory skill, look at or drive this machine's own screen, and more.
Ask for something that needs one and the model just calls it — no button
required — and it can chain or parallelize several calls in one turn (look
up a skill, run it, check the result) rather than stopping after the first
step. Each call/result narrates live in the chat as "using X..." with a
✓/✗ once it resolves. This makes the wake-word voice loop a full voice
control surface for free: anything typed also works spoken.

Deliberately left out of tool-calling: the duress trigger, the encrypted
vault, 2FA verification, and geofence/breach edits stay manual/REST-only —
a misheard voice command is the wrong way to fire a real panic alert or
read vault secrets aloud.

**Screen control runs at full speed by default.** `drive_screen` is a
perceive → decide → act loop (screenshot, ask what's on screen, ask which
single action gets closer to the goal, act, repeat) with no artificial
delay between steps — it moves as fast as the two model calls underneath
it allow, not slowed down by a confirmation dialog per click. Two
exceptions, both deliberate: pass `slow: true` (or just ask Ori to "go
slow"/"show me") to insert a visible pause between steps when you want to
watch it work, and anything that looks financial or destructive (pay,
delete, send money, sudo, ...) always stops and asks for an explicit yes
before acting, regardless of speed — see `is_sensitive()` in
`boddos/agent/screen_agent.py` for the exact pattern list.

```bash
# system deps for screen control, Ogun 3D, the device finder, and the
# skill portal (optional — each section degrades to a clear
# "disabled"/"unavailable" message without these). macOS: brew install
# equivalents, formula names may differ — check `brew search <name>`.
apt install openscad xvfb ngspice libngspice0-dev calculix-ccx bluez git
npm install -g repomix   # or rely on `npx repomix`, which fetches it on first use
pip install -e ".[screen,ogun,finder,skills]"

# terminal 1 — backend
python -m boddos --config config/boddos.yaml --port 8000

# terminal 2 — frontend (Windows: run each line separately, no &&)
cd frontend
npm install
npm run dev   # http://localhost:5173
```

The backend's default port is 8787 (see Install above); the frontend dev
proxy in `frontend/vite.config.ts` expects it on 8000, so pass `--port 8000`
or edit the proxy target to match. The old `boddos/ui/` PWA still works
unchanged and is still served at `/` by the backend directly.

### Natural voice replies (Piper)

Same philosophy as every Ogun lab: the local chat model only decides *what*
to say — a real, external, open-source engine is the "muscle" that makes it
actually sound like something (`boddos/voice/tts.py`). Out of the box Ori
falls back to your browser's flat default voice; this swaps that for
[Piper](https://github.com/OHF-voice/piper1-gpl), a neural TTS engine that
runs in real time on CPU with no GPU required — a good fit even on a
low-RAM machine, since it's a completely separate process from the chat
model.

```bash
pip install -e ".[voice]"

# pick a voice (samples in the piper1-gpl repo above), then fetch it once —
# downloads <name>.onnx + <name>.onnx.json into voices_dir:
python -m piper.download_voices en_US-amy-medium --download-dir ~/.boddos/voices
```

That's it — no config edit needed if you're happy with the default voice
(`voice.tts_voice: "en_US-amy-medium"`, matching the default above); restart
the backend and reload the browser tab. Prefer a different voice? List
options with `python -m piper.download_voices` (no args), download the one
you want the same way, and set `voice.tts_voice` in `config/boddos.yaml` to
its name. Until a model is downloaded, the "New wishes" chat panel shows a
one-line notice and keeps speaking through the browser instead — nothing
breaks, it just sounds like the default OS voice until you fetch one.

### Fast local speech recognition (Vosk)

Same split again, this time on the *listening* side: the browser's own
SpeechRecognition API isn't actually local on Chrome (it streams your mic
audio to Google's servers to transcribe it) and doesn't exist at all on
Firefox. This swaps it for [Vosk](https://alphacephei.com/vosk/) — a small,
fast, fully offline recognizer (`boddos/voice/stt.py`) that runs in real
time on CPU, so recognition speed and reliability never depend on the local
chat model's size. The browser streams raw mic audio to the backend over a
WebSocket (`/ws/voice/stt`) instead of doing recognition itself.

```bash
pip install -e ".[voice]"

# download a model (the small English one is ~40MB) and unzip it —
# browse more languages/sizes at https://alphacephei.com/vosk/models
mkdir -p ~/.boddos/stt && cd ~/.boddos/stt
curl -LO https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip
unzip vosk-model-small-en-us-0.15.zip && rm vosk-model-small-en-us-0.15.zip
```

On Windows (PowerShell):

```powershell
pip install -e ".[voice]"

New-Item -ItemType Directory -Force -Path "$HOME\.boddos\stt" | Out-Null
Invoke-WebRequest -Uri "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip" -OutFile "$HOME\.boddos\stt\vosk.zip"
Expand-Archive -Path "$HOME\.boddos\stt\vosk.zip" -DestinationPath "$HOME\.boddos\stt" -Force
Remove-Item "$HOME\.boddos\stt\vosk.zip"
```

Same as the voice above: no config edit needed if the folder ends up at
`~/.boddos/stt/vosk-model-small-en-us-0.15` (matching `voice.stt_model_dir`'s
default); just restart the backend and reload the browser tab. Until a
model is downloaded, the mic button falls back to the browser's own
SpeechRecognition automatically (when the browser has one) with a one-line
notice explaining why — nothing breaks, it just isn't the fast local engine
until you fetch one.

The Ogun 3D engineering labs (chemistry, circuits, structures, aerospace,
biology, materials) each import their heavy library — Cantera, PySpice,
RocketPy, OpenMM, Biopython, mp-api — lazily, on first actual use, not at
server startup, so `pip install`ing all of them doesn't slow down every
node's boot. First use of each lab still pays that one-time import cost,
which can take a while on a cold cache (Windows especially, if antivirus
scans each newly-loaded DLL) — that's normal, not a hang.
