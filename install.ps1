# BODDOS / Ori installer for Windows (PowerShell).
#
#   irm https://raw.githubusercontent.com/localinvestorsusa-create/boddos/claude/delete-boddos-folder-t8lh8m/install.ps1 | iex
#
# Installs BODDOS into %USERPROFILE%\boddos, sets up a venv, generates config
# with fresh secrets, and tells you how to start Ori. Install Ollama separately
# from https://ollama.com (then: ollama pull llama3.1 ; ollama pull llava).
$ErrorActionPreference = "Stop"
$Repo   = "https://github.com/localinvestorsusa-create/boddos"
$Branch = if ($env:BODDOS_BRANCH) { $env:BODDOS_BRANCH } else { "claude/delete-boddos-folder-t8lh8m" }
$Dest   = if ($env:BODDOS_HOME)   { $env:BODDOS_HOME }   else { Join-Path $env:USERPROFILE "boddos" }
$Port   = if ($env:BODDOS_PORT)   { $env:BODDOS_PORT }   else { "8787" }

function Say($m)  { Write-Host "▶ $m" -ForegroundColor Cyan }
function Ok($m)   { Write-Host "✓ $m" -ForegroundColor Green }
function Warn($m) { Write-Host "! $m" -ForegroundColor Yellow }

Say "BODDOS / Ori installer"

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
  Write-Host "Python 3.10+ is required. Install from https://python.org (check 'Add to PATH') and re-run."
  exit 1
}
Ok ("Python " + (python -c "import sys;print('%d.%d'%sys.version_info[:2])"))

if (Test-Path (Join-Path $Dest ".git")) {
  Say "Updating existing checkout at $Dest"
  git -C $Dest fetch --quiet origin $Branch
  git -C $Dest checkout --quiet $Branch
  git -C $Dest pull --quiet origin $Branch
} else {
  Say "Cloning into $Dest"
  git clone --quiet --branch $Branch $Repo $Dest
}
Set-Location $Dest
Ok "Source ready"

Say "Installing Python packages (this can take a minute)"
python -m venv .venv
& .\.venv\Scripts\python.exe -m pip install --quiet --upgrade pip
& .\.venv\Scripts\python.exe -m pip install --quiet -e ".[push]"
Ok "BODDOS installed"

if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
  Warn "Ollama not found. Install it from https://ollama.com, then: ollama pull llama3.1 ; ollama pull llava"
}

$Cfg = "config\boddos.yaml"
if (Test-Path $Cfg) {
  Warn "config\boddos.yaml already exists — leaving it untouched"
} else {
  Say "Generating config with fresh secrets"
  $psk   = python -c "import secrets;print(secrets.token_urlsafe(32))"
  $token = python -c "import secrets;print(secrets.token_urlsafe(24))"
  $id    = ($env:COMPUTERNAME).ToLower() -replace '[^a-z0-9]',''
  $ip    = python -c "import socket;s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.connect(('8.8.8.8',80));print(s.getsockname()[0]);s.close()"
  $vapid = & .\.venv\Scripts\python.exe -m boddos --new-vapid 2>$null
  $vpub  = ($vapid | Select-String 'vapid_public')  -replace '.*: *"(.*)"','$1'
  $vpriv = ($vapid | Select-String 'vapid_private') -replace '.*: *"(.*)"','$1'
  Copy-Item config\boddos.example.yaml $Cfg
  & .\.venv\Scripts\python.exe - $Cfg $id $ip $Port $psk $token $vpub $vpriv @'
import sys, yaml
path, nid, ip, port, psk, token, vpub, vpriv = sys.argv[1:9]
d = yaml.safe_load(open(path))
d["node"]["id"] = nid
d["node"]["advertise_url"] = f"http://{ip}:{port}"
d["node"]["bind_port"] = int(port)
d["mesh"]["psk"] = psk
d["mesh"]["peers"] = []
d["security"]["require_auth"] = True
d["security"]["api_token"] = token
if vpub and vpriv:
    d["services"]["push"].update({"enabled": True, "vapid_public": vpub, "vapid_private": vpriv})
yaml.safe_dump(d, open(path, "w"), sort_keys=False)
'@
  Ok "Wrote $Cfg (edit it to add peer machines + trusted contacts)"
}

Write-Host ""
Ok "Install complete."
Write-Host "Start Ori:"
Write-Host "    cd $Dest ; .\.venv\Scripts\python.exe -m boddos --config config\boddos.yaml"
Write-Host ""
Write-Host "Then open on your phone/computer:  http://<this-machine-ip>:$Port/"
Write-Host "Your API token is in $Cfg (security.api_token) — paste it once per device."
