# Using Ori across your devices — seamlessly

Ori is the assistant; BODDOS is the mesh it runs on. You set the mesh up once,
then use Ori from any device on your network (or anywhere, over WireGuard).

## The one-time setup (10 minutes)

1. **Install a node on each machine** (MacBook = primary, ZBook = failover,
   HP = edge). See `docs/DEPLOY.md`. Same `mesh.psk` on all three; each with a
   unique `node.id`. Pull models on the two 32 GB hosts:
   `ollama pull llama3.1 && ollama pull llava`.
2. **Turn on the things that make it seamless** in each `config/boddos.yaml`:
   - `security.tls_enabled: true` — HTTPS, required for mic/camera/push on phones.
   - `security.require_auth: true` — one shared token gates the API.
   - `services.push.enabled: true` with keys from `python -m boddos --new-vapid`.
   - `assistant.name: "Ori"` and `wake_words: ["ori", "hey ori"]` (already default).
3. **Start each node** (`python -m boddos --config config/boddos.yaml`, or install
   the service in `deploy/`). They find each other within a heartbeat.

## Add each device once

Everything is the **same web app** — no app store, no per-device build. Open the
node URL, install it, grant permissions once. It remembers your token afterwards.

| Device | How to add it | What it becomes |
|--------|---------------|-----------------|
| **Phone** | Open `https://<macbook-ip>:8787/`, trust the cert, **Add to Home Screen**. Paste the API token when asked. Allow mic, camera, notifications, location. | Your main Ori: voice, vision, safety, push. |
| **Second phone / tablet** | Same URL, same token. | Another full Ori screen. |
| **Laptop / desktop** | Same URL in a browser tab. | Typing + voice + its own camera. |
| **Smart glasses** | Pair them so they present as a **camera/mic** to the phone, then on the **Vision** tab pick them from the camera dropdown (🔄 to cycle). | Ori sees through the glasses. |
| **External / IP camera** | **Vision → External cameras**: type a name + a snapshot/MJPEG/`rtsp://` URL. | Ori can look through it on demand. |
| **ESP32** | Flash `firmware/esp32/`, set `NODE_URL` to the MacBook. | Pocket sensor: nearby devices, trackers, fields. |
| **Another computer (compute)** | Install a node, share the `mesh.psk`, list it as a peer. | More brains: models + load sharing. |

Because every node serves the same UI and shares the same mesh, it does not
matter which node's URL you open — if the MacBook is off, open the ZBook's URL
and everything works the same.

## Talking to Ori (hands-free)

1. On the **Advisor** tab tap **Hey Ori** once (arms listening; the button glows).
2. Say **"Hey Ori"** or just **"Ori"** — it answers with "Yes?".
3. Ask anything: *"Ori, what's the weather for my run?"*, *"Ori, what am I looking
   at?"*, *"Ori, is anyone following me?"* It replies out loud and keeps the
   conversation open for follow-ups.
4. Say **"stop"** / **"goodbye"** to send it back to sleep. Tap **Talk** to start a
   conversation instantly without the wake word.

Tips:
- **"Speak replies"** (Advisor tab) also voices typed answers.
- You can say the wake word *with* the command in one breath — "Hey Ori, translate
  this" — it strips the wake word and runs the rest.
- To rename it (e.g. Jarvis): set `assistant.name` and `wake_words`, restart. The
  whole UI and voice update automatically.

## Seeing (vision)

- **Vision** tab → **Start** → ask a question (or leave blank to just describe).
  Frames are analyzed by the local `llava` model on a host node — nothing leaves
  your machines.
- Use the camera dropdown / 🔄 to switch between phone front/back or **glasses**.
- External cameras added by URL get a **Look** button.

## Staying safe (always-on)

- **PANIC** button (top bar) → alerts your trusted contacts (webhook/SMS/email)
  **and** pushes to every enrolled phone's lock screen, with your location.
- **Dead-man's switch** (Safety tab): arm a check-in before something risky; miss
  it and Ori raises the alarm automatically.
- **Followers / surveillance / geofence** run off your ESP32 + phone sensors and
  surface on the Safety tab and as live alerts.
- **Enable push to this phone** (Safety tab) once, so alerts reach you even when
  the app is closed or the phone is locked.

## Using it away from home

Don't expose BODDOS to the internet. Put your phone + machines on a **WireGuard**
or **Tailscale** overlay. Then the same `https://<node>:8787/` URLs work from
anywhere, encrypted end to end, and Ori is with you on the road exactly as at home.

## Everyday phrases

- "Hey Ori, what's around me?" — situational-awareness summary.
- "Ori, look and tell me if this door is locked." — vision.
- "Ori, translate what she just said." — listens, returns English.
- "Ori, remember I parked on level 3." — quick note to the advisor.
- "Ori, check in with me in 20 minutes." — arms a dead-man's switch.
- "Ori, run `git status` on my laptop." — OS agent (if enabled + 2FA code).
