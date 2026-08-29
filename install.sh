#!/usr/bin/env bash
# BODDOS / Ori one-shot installer for macOS and Linux.
#
#   curl -fsSL https://raw.githubusercontent.com/localinvestorsusa-create/boddos/claude/delete-boddos-folder-t8lh8m/install.sh | bash
#
# One download, boom, running — fully non-interactive by default:
#   1. Checks Python 3.10+.
#   2. Clones/updates the repo into ~/boddos.
#   3. Creates a virtualenv and installs BODDOS (+ push support).
#   4. Detects this machine's hardware and picks a model tier for it.
#   5. Installs Ollama and pulls the right-sized models automatically.
#   6. Generates config/boddos.yaml with fresh secrets (PSK, API token, VAPID)
#      — or, given a join token (--join / $BODDOS_JOIN), joins an existing
#      mesh instead of generating a new one. See `python -m boddos --join-code`.
#   7. Starts Ori.
#
# To add a machine to a mesh you already have running, grab a join token
# from the first machine (`python -m boddos --join-code`) and pass it here:
#   curl -fsSL .../install.sh | bash -s -- --join bd1.XXXXX
#
# Opt out of any step: BODDOS_SKIP_OLLAMA=1, BODDOS_SKIP_MODEL_PULL=1,
# BODDOS_NO_START=1. Force the old interactive prompts: BODDOS_INTERACTIVE=1.
set -euo pipefail

REPO="https://github.com/localinvestorsusa-create/boddos"
BRANCH="${BODDOS_BRANCH:-claude/delete-boddos-folder-t8lh8m}"
DEST="${BODDOS_HOME:-$HOME/boddos}"
PORT="${BODDOS_PORT:-8787}"
JOIN="${BODDOS_JOIN:-}"

# --join <token> as a plain CLI arg, same as $BODDOS_JOIN.
while [[ $# -gt 0 ]]; do
  case "$1" in
    --join) JOIN="$2"; shift 2 ;;
    --join=*) JOIN="${1#--join=}"; shift ;;
    *) shift ;;
  esac
done

say()  { printf "\033[1;36m▶ %s\033[0m\n" "$*"; }
ok()   { printf "\033[1;32m✓ %s\033[0m\n" "$*"; }
warn() { printf "\033[1;33m! %s\033[0m\n" "$*"; }

# Non-interactive by default (this is a `curl | bash` one-liner, not a wizard) —
# every step proceeds with the sensible default unless BODDOS_INTERACTIVE=1 or
# a specific opt-out is set. When forced interactive, ask for real.
INTERACTIVE="${BODDOS_INTERACTIVE:-0}"
ask() {
  if [[ "$INTERACTIVE" != "1" ]]; then return 0; fi
  read -r -p "$1 [Y/n] " a; [[ -z "$a" || "$a" =~ ^[Yy]$ ]]
}

say "BODDOS / Ori installer"
if [[ -n "$JOIN" ]]; then
  say "Joining an existing mesh with the provided token"
fi

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

OLLAMA_OK=0
if command -v ollama >/dev/null; then
  ok "Ollama already installed"
  OLLAMA_OK=1
elif [[ "${BODDOS_SKIP_OLLAMA:-0}" == "1" ]]; then
  warn "Skipping Ollama install (BODDOS_SKIP_OLLAMA=1) — install it later from https://ollama.com"
elif [[ "$(uname)" == "Darwin" || "$(uname)" == "Linux" ]] && ask "Install Ollama now (runs the local AI models)?"; then
  curl -fsSL https://ollama.com/install.sh | sh && OLLAMA_OK=1 || warn "Ollama install failed; install it later from https://ollama.com"
else
  warn "Skipping Ollama — install it later from https://ollama.com, then: ollama pull $DEFAULT_MODEL && ollama pull $VISION_MODEL"
fi

if [[ "$OLLAMA_OK" == "1" && "${BODDOS_SKIP_MODEL_PULL:-0}" != "1" ]] \
   && ask "Pull $DEFAULT_MODEL (advisor) and $VISION_MODEL (vision) now? (several GB, sized to this machine)"; then
  say "Pulling models sized to this machine (this can take a while)"
  ollama pull "$DEFAULT_MODEL" || true
  ollama pull "$VISION_MODEL" || true
fi

# 5. Config: fresh secrets, or join an existing mesh
mkdir -p "$HOME/.boddos"
CFG="config/boddos.yaml"
if [ -f "$CFG" ]; then
  warn "config/boddos.yaml already exists — leaving it untouched"
  if [[ -n "$JOIN" ]]; then
    warn "--join was given but there's already a config here, so it wasn't applied — add the peer manually under mesh.peers (and match mesh.psk) in $CFG"
  fi
else
  say "Generating config"
  TOKEN=$(python3 -c 'import secrets;print(secrets.token_urlsafe(24))')
  # Hostname alone isn't reliably unique — cloned VMs, default "DESKTOP-XXXX"
  # names, and identically-provisioned machines collide often enough that
  # this bit it a random suffix rather than risk two nodes sharing an id
  # (which makes the mesh silently drop one of them as "itself").
  ID="$(hostname | tr 'A-Z' 'a-z' | tr -cd 'a-z0-9' | cut -c1-12)-$(python3 -c 'import secrets;print(secrets.token_hex(3))')"
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

  if [[ -n "$JOIN" ]]; then
    # Decode the join token instead of minting a fresh, non-matching PSK.
    JOIN_JSON=$(python3 -c "
from boddos.join import decode
import json, sys
print(json.dumps(decode(sys.argv[1])))
" "$JOIN")
    PSK=$(python3 -c "import json,sys; print(json.loads(sys.argv[1])['psk'])" "$JOIN_JSON")
    PEER=$(python3 -c "import json,sys; print(json.loads(sys.argv[1])['peer'])" "$JOIN_JSON")
  else
    PSK=$(python3 -c 'import secrets;print(secrets.token_urlsafe(32))')
    PEER=""
  fi

  cp config/boddos.example.yaml "$CFG"
  python3 - "$CFG" "$ID" "$IP" "$PORT" "$PSK" "$TOKEN" "$VPUB" "$VPRIV" "$DEFAULT_MODEL" "$VISION_MODEL" "$PEER" <<'PY'
import sys, yaml
path, nid, ip, port, psk, token, vpub, vpriv, default_model, vision_model, peer = sys.argv[1:12]
d = yaml.safe_load(open(path))
d["node"]["id"] = nid
d["node"]["advertise_url"] = f"http://{ip}:{port}"
d["node"]["bind_port"] = int(port)
d["mesh"]["psk"] = psk
d["mesh"]["peers"] = [peer] if peer else []
d["models"]["default_model"] = default_model
d["models"]["vision_model"] = vision_model
d["security"]["require_auth"] = True
d["security"]["api_token"] = token
if vpub and vpriv:
    d["services"]["push"].update({"enabled": True, "vapid_public": vpub, "vapid_private": vpriv})
yaml.safe_dump(d, open(path, "w"), sort_keys=False)
print(f"NODE_IP={ip}"); print(f"API_TOKEN={token}")
PY
  if [[ -n "$JOIN" ]]; then
    ok "Wrote $CFG, joined to $PEER"
  else
    ok "Wrote $CFG — run \`python -m boddos --join-code\` after starting to add another machine"
  fi
fi

echo
ok "Install complete."
echo "Your API token is in $CFG (security.api_token) — paste it once per device."
echo "For HTTPS (needed for phone mic/camera/push), set security.tls_enabled: true."
echo

if [[ "${BODDOS_NO_START:-0}" == "1" ]]; then
  echo "Start Ori:"
  echo "    cd $DEST && . .venv/bin/activate && python -m boddos --config config/boddos.yaml"
elif ask "Start Ori now?"; then
  say "Starting Ori — open http://<this-machine-ip>:$PORT/ on your phone or computer"
  exec python -m boddos --config config/boddos.yaml
fi
