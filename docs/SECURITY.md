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

- Detect whether **you** are being followed by a rogue BLE tracker.
- Audit **your own** public exposure and generate a reduction plan.
- Panic/duress alerting to **your** consenting trusted contacts.
- Situational awareness from real, in-range signals (Wi-Fi/BLE/field/sound).

## Hardening the deployment

BODDOS is designed to run on a trusted LAN you control. Even so:

- **Mesh PSK.** Every node shares a secret (`mesh.psk`). Set it to a long random
  value. Mesh endpoints reject requests without it. Rotate it if a machine is lost.
- **Bind scope.** Nodes bind `0.0.0.0` for LAN access. Do **not** port-forward
  BODDOS to the public internet. For remote access use a private overlay
  (WireGuard/Tailscale) so the mesh never touches the open internet.
- **OS agent.** Off by default. When enabled it runs an allowlist of commands
  only, with no shell interpretation, confined to a working directory, and can
  require per-call confirmation. Keep the allowlist minimal.
- **Local models.** All inference is on your machines via Ollama; prompts and
  translations never leave your network.
- **Contacts & location.** Trusted-contact details and location live in your
  config and on your nodes only. Treat `config/boddos.yaml` as a secret (it is
  git-ignored).

## Legal note

You are responsible for using BODDOS lawfully. Recording, tracking, and drone
operation are regulated and vary by location. Only fly drones you own within the
rules that apply to you, and only record/track with the consent the law requires.
