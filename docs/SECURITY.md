# BODDOS — scope, ethics, and security boundaries

BODDOS is a tool to help you **operate day-to-day and protect yourself**. It is
built with hard boundaries. This document states them plainly so the project
stays on the right side of both the law and its purpose.

## What BODDOS will not do

These are out of scope by design and will not be added:

1. **Covert surveillance of other people.** No secretly recording, tracking,
   locating, or identifying non-consenting individuals or their devices. In most
   jurisdictions this is illegal (wiretapping, stalking, unlawful surveillance).
2. **Remote reading of a person's body or mind.** No "read their heartbeat / fear
   / emotions to gain a persuasive advantage." This is both technically bogus at
   a distance and ethically a manipulation tool.
3. **OSINT dossiers on third parties.** The exposure module audits *your own*
   identifiers so you can reduce your footprint. It does not assemble profiles of
   other people from a photo, email, or phone number.
4. **Impersonation.** No real-time voice cloning/modification aimed at deceiving
   someone about who they're talking to.
5. **Physically impossible claims.** A phone + ESP32 cannot see through walls,
   give 360° vision, or sense strangers' vitals. BODDOS reports only what the
   hardware can actually measure and labels it honestly.

## What BODDOS does do — defensively

Personal safety:

- Detect whether **you** are being followed by a rogue BLE tracker.
- **Dead-man's switch / check-in timer** — arm before a risky activity; miss the
  check-in and it auto-fires a duress alert (`safety/deadman.py`).
- **Surveillance scan** — evil-twin / rogue-AP detection and camera/tracker
  vendor fingerprinting from the signals around you (`safety/surveillance.py`).
- **Geofenced safe zones** — alert when you leave all safe zones or enter a
  danger zone (`safety/geofence.py`).
- **Password breach check** with k-anonymity — only a hash prefix leaves the
  device (`safety/breach.py`).
- Audit **your own** public exposure and generate a reduction plan.
- Panic/duress alerting to **your** consenting trusted contacts, mesh-broadcast.
- Situational awareness from real, in-range signals (Wi-Fi/BLE/field/sound).

Infrastructure hardening (`security/`):

- **Mesh request signing** — every node-to-node request is HMAC-SHA256 signed
  over timestamp+nonce+body, with a replay window and seen-nonce cache. The PSK
  never travels on the wire and captured requests can't be replayed.
- **Client auth** — optional bearer token for the phone/UI API (and WebSocket),
  auto-generated if you enable auth without setting one.
- **Rate limiting + lockout** — token-bucket per client, with automatic lockout
  after repeated auth failures (brute-force protection).
- **Tamper-evident audit log** — hash-chained JSONL of sensitive actions
  (agent runs, duress, calls, auth failures); `verify_chain()` detects edits.
- **Encrypted secret vault** — AES-GCM with scrypt-derived key; passphrase via
  `BODDOS_VAULT_PASSPHRASE`, never written to disk.
- **TLS** — self-signed cert generation so LAN traffic is encrypted.

## Hardening the deployment

BODDOS is designed to run on a trusted LAN you control. Even so:

- **Mesh signing.** Every node shares a secret (`mesh.psk`) used to HMAC-sign
  inter-node requests. Set it to a long random value; rotate it if a machine is
  lost. The secret itself is never sent over the network.
- **Bind scope.** Nodes bind `0.0.0.0` for LAN access. Do **not** port-forward
  BODDOS to the public internet. For remote access use a private overlay
  (WireGuard/Tailscale) so the mesh never touches the open internet.
- **Client auth & TLS.** Enable `security.require_auth` for a bearer-token gate on
  the phone/UI API, and `security.tls_enabled` to encrypt LAN traffic.
- **OS agent.** Off by default. When enabled it runs an allowlist of commands
  only, with no shell interpretation, confined to a working directory, and can
  require per-call confirmation. Keep the allowlist minimal.
- **Local models.** All inference is on your machines via Ollama; prompts and
  translations never leave your network.
- **Contacts & location.** Trusted-contact details and location live in your
  config and on your nodes only. Treat `config/boddos.yaml` as a secret (it is
  git-ignored). Store API keys in the encrypted vault, not in plaintext config.

## Legal note

You are responsible for using BODDOS lawfully. Recording, tracking, and drone
operation are regulated and vary by location. Only fly drones you own within the
rules that apply to you, and only record/track with the consent the law requires.
