# Deploying BODDOS across your machines

Target topology: **MacBook (primary model host)**, **ZBook (failover host)**,
**HP (edge/tools)**, plus your **phone** and an **ESP32**.

## 0. Prerequisites (each machine)

- Python 3.10+
- [Ollama](https://ollama.com) on the two 32 GB hosts (MacBook, ZBook):
  ```bash
  ollama pull llama3.1        # advisor / translation model
  ```
  The HP (8 GB) can run a smaller model (e.g. `ollama pull llama3.2:3b`) or none.
- All machines on the **same LAN**. Note each machine's LAN IP (`ipconfig` /
  `ip addr` / `ifconfig`).

## 1. Install (each machine)

```bash
git clone https://github.com/localinvestorsusa-create/boddos
cd boddos
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
cp config/boddos.example.yaml config/boddos.yaml
```

## 2. Configure per node

Edit `config/boddos.yaml` on each machine. The important differences:

| Field | MacBook | ZBook | HP |
|-------|---------|-------|----|
| `node.id` | `macbook` | `zbook` | `hp` |
| `node.role` | `host` | `host` | `edge` |
| `node.advertise_url` | its LAN IP:8787 | its LAN IP:8787 | its LAN IP:8787 |
| `models.default_model` | `llama3.1` | `llama3.1` | `llama3.2:3b` |
| `models.ram_gb` | 32 | 32 | 8 |
| `mesh.peers` | [zbook, hp] | [macbook, hp] | [macbook, zbook] |

Set the **same** `mesh.psk` on all three. Fill `safety.trusted_contacts` with
your consenting contacts, and `services.weather` with your lat/lon.

## 3. Run each node

```bash
python -m boddos --config config/boddos.yaml
```

Leave it running (or use `scripts/run_node.sh`, a systemd unit, or `launchd` on
macOS). Within one heartbeat the nodes find each other — verify:

```bash
curl http://<macbook-ip>:8787/mesh/nodes
```

## 4. Phone

On the same Wi-Fi, open `http://<macbook-ip>:8787/` in the phone browser and
"Add to Home Screen" to install the PWA. It talks to whichever node you point it
at; if the MacBook is off, use the ZBook's IP.

## 5. ESP32

Flash `firmware/esp32/boddos_sensor/` (see its README), setting `NODE_URL` to the
MacBook's `/api/sensors/ingest`. Readings show up under **Awareness**.

## 6. Alerts, 2FA, and running as a service

**Alert delivery.** Duress and dead-man's-switch alerts go to `trusted_contacts`
by their `channel`:
- `webhook` — set `target` to a URL you control (ntfy, Home Assistant, your bot).
  Works with no extra config.
- `email` — fill `services.notify.smtp` (use `BODDOS_SMTP_PASSWORD` for the
  password rather than plaintext).
- `sms` — set `services.notify.sms_webhook` to your own gateway URL template
  (`{target}` / `{body}` are substituted).

**2FA (optional).** Require a TOTP code on sensitive actions (OS agent, drone,
vault writes):
```bash
python -m boddos --new-totp          # prints a secret + otpauth:// URI
```
Add the secret to `security.totp_secret` (or `BODDOS_TOTP_SECRET`), set
`security.require_2fa: true`, and scan the URI into an authenticator app. The UI
appends the code to guarded requests.

**Run as a service.**
- Linux (HP/ZBook): `deploy/boddos.service` (systemd) — see the header comments.
- macOS (MacBook): `deploy/com.boddos.node.plist` (launchd).
- Container: `docker build -t boddos . && docker run -p 8787:8787 -v $PWD/config:/config boddos`.

## 7. Remote access (optional, recommended)

Do **not** port-forward to the internet. Put all machines + phone on a private
overlay like **WireGuard** or **Tailscale**; then the same LAN URLs work from
anywhere, encrypted, with the mesh never exposed publicly.

## Troubleshooting

- **Advisor says "model unavailable"** → Ollama isn't running or the model isn't
  pulled on the serving host. `ollama list` to check.
- **Peers don't appear** → PSK mismatch, wrong `advertise_url`, or a firewall
  blocking 8787. Confirm with `curl .../health` between machines.
- **ESP32 no data** → check Serial Monitor for `POST 200`; verify `NODE_URL` IP.
