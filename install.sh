#!/usr/bin/env bash
# BODDOS / Ori one-shot installer for macOS and Linux.
#
#   curl -fsSL https://raw.githubusercontent.com/localinvestorsusa-create/boddos/claude/personal-security-assistant-yi36rv/install.sh | bash
#
# What it does (asks before anything heavy):
#   1. Checks Python 3.10+.
#   2. Clones/updates the repo into ~/boddos.
#   3. Creates a virtualenv and installs BODDOS (+ push support).
#   4. Offers to install Ollama and pull the advisor + vision models.
#   5. Generates config/boddos.yaml with fresh secrets (PSK, API token, VAPID).
#   6. Prints the URL + token and how to start Ori.
set -euo pipefail

REPO="https://github.com/localinvestorsusa-create/boddos"
BRANCH="${BODDOS_BRANCH:-claude/personal-security-assistant-yi36rv}"
DEST="${BODDOS_HOME:-$HOME/boddos}"
PORT="${BODDOS_PORT:-8787}"

say()  { printf "\033[1;36m▶ %s\033[0m\n" "$*"; }
ok()   { printf "\033[1;32m✓ %s\033[0m\n" "$*"; }
warn() { printf "\033[1;33m! %s\033[0m\n" "$*"; }
ask()  { read -r -p "$1 [y/N] " a; [[ "$a" =~ ^[Yy]$ ]]; }

say "BODDOS / Ori installer"

# 1. Python
if ! command -v python3 >/dev/null; then
  echo "Python 3.10+ is required. Install it (macOS: brew install python; Linux: apt install python3 python3-venv) and re-run."
  exit 1
fi
PYV=$(python3 -c 'import sys;print("%d.%d"%sys.version_info[:2])')
ok "Python $PYV found"

# 2. Repo
if [ -d "$DEST/.git" ]; then
  say "Updating existing checkout at $DEST"
  git -C "$DEST" fetch --quiet origin "$BRANCH" && git -C "$DEST" checkout --quiet "$BRANCH" && git -C "$DEST" pull --quiet origin "$BRANCH"
else
  say "Cloning into $DEST"
  git clone --quiet --branch "$BRANCH" "$REPO" "$DEST"
fi
cd "$DEST"
ok "Source ready"

# 3. venv + install
say "Installing Python packages (this can take a minute)"
python3 -m venv .venv
# shellcheck disable=SC1091
. .venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet -e ".[push]"
ok "BODDOS installed"

# 4. Hardware detection, then Ollama + the right-sized models
say "Checking what this machine can actually run"
HW_JSON=$(python3 -c "
from boddos.hardware import detect
import json
print(json.dumps(detect().to_dict()))
")
DEFAULT_MODEL=$(python3 -c "import json,sys; print(json.loads(sys.argv[1])['recommended_model'])" "$HW_JSON")
VISION_MODEL=$(python3 -c "import json,sys; print(json.loads(sys.argv[1])['recommended_vision_model'])" "$HW_JSON")
HW_NOTE=$(python3 -c "import json,sys; print(json.loads(sys.argv[1])['notes'][0])" "$HW_JSON")
RAM_GB=$(python3 -c "import json,sys; print(json.loads(sys.argv[1])['ram_gb'])" "$HW_JSON")
HAS_GPU=$(python3 -c "import json,sys; print(json.loads(sys.argv[1])['has_gpu'])" "$HW_JSON")
ok "${RAM_GB}GB RAM, GPU: ${HAS_GPU} → recommending $DEFAULT_MODEL ($HW_NOTE)"

if command -v ollama >/dev/null; then
  ok "Ollama already installed"
  OLLAMA_OK=1
else
  if [[ "$(uname)" == "Darwin" || "$(uname)" == "Linux" ]] && ask "Install Ollama now (runs the local AI models)?"; then
    curl -fsSL https://ollama.com/install.sh | sh && OLLAMA_OK=1 || warn "Ollama install failed; install it later from https://ollama.com"
  else
    warn "Skipping Ollama — install it later from https://ollama.com, then: ollama pull $DEFAULT_MODEL && ollama pull $VISION_MODEL"
    OLLAMA_OK=0
  fi
fi
if [[ "${OLLAMA_OK:-0}" == "1" ]] && ask "Pull $DEFAULT_MODEL (advisor) and $VISION_MODEL (vision) now? (several GB, sized to this machine)"; then
  ollama pull "$DEFAULT_MODEL" || true
  ollama pull "$VISION_MODEL" || true
fi

# 5. Config with fresh secrets
mkdir -p "$HOME/.boddos"
CFG="config/boddos.yaml"
if [ -f "$CFG" ]; then
  warn "config/boddos.yaml already exists — leaving it untouched"
else
  say "Generating config with fresh secrets"
  PSK=$(python3 -c 'import secrets;print(secrets.token_urlsafe(32))')
  TOKEN=$(python3 -c 'import secrets;print(secrets.token_urlsafe(24))')
  ID=$(hostname | tr 'A-Z' 'a-z' | tr -cd 'a-z0-9' | cut -c1-16)
  IP=$(python3 - <<'PY'
import socket
s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
try:
    s.connect(("8.8.8.8",80)); print(s.getsockname()[0])
except Exception:
    print("127.0.0.1")
finally:
    s.close()
PY
)
  VAPID=$(python3 -m boddos --new-vapid 2>/dev/null || true)
  VPUB=$(echo "$VAPID" | grep vapid_public | sed 's/.*: *"\(.*\)"/\1/' || true)
  VPRIV=$(echo "$VAPID" | grep vapid_private | sed 's/.*: *"\(.*\)"/\1/' || true)
  cp config/boddos.example.yaml "$CFG"
  python3 - "$CFG" "$ID" "$IP" "$PORT" "$PSK" "$TOKEN" "$VPUB" "$VPRIV" "$DEFAULT_MODEL" "$VISION_MODEL" <<'PY'
import sys, yaml
path, nid, ip, port, psk, token, vpub, vpriv, default_model, vision_model = sys.argv[1:11]
d = yaml.safe_load(open(path))
d["node"]["id"] = nid
d["node"]["advertise_url"] = f"http://{ip}:{port}"
d["node"]["bind_port"] = int(port)
d["mesh"]["psk"] = psk
d["mesh"]["peers"] = []
d["models"]["default_model"] = default_model
d["models"]["vision_model"] = vision_model
d["security"]["require_auth"] = True
d["security"]["api_token"] = token
if vpub and vpriv:
    d["services"]["push"].update({"enabled": True, "vapid_public": vpub, "vapid_private": vpriv})
yaml.safe_dump(d, open(path, "w"), sort_keys=False)
print(f"NODE_IP={ip}"); print(f"API_TOKEN={token}")
PY
  ok "Wrote $CFG (edit it to add peer machines + trusted contacts)"
fi

echo
ok "Install complete."
echo "Start Ori:"
echo "    cd $DEST && . .venv/bin/activate && python -m boddos --config config/boddos.yaml"
echo
echo "Then open the app on your phone/computer:  http://<this-machine-ip>:$PORT/"
echo "Your API token is in $CFG (security.api_token) — paste it once per device."
echo "For HTTPS (needed for phone mic/camera/push), set security.tls_enabled: true."
if ask "Start Ori now?"; then
  exec python -m boddos --config config/boddos.yaml
fi
