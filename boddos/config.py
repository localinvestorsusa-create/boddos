"""Configuration loading and typed models for a BODDOS node."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field


class NodeCfg(BaseModel):
    id: str
    name: str = ""
    role: Literal["host", "edge"] = "edge"
    bind_host: str = "0.0.0.0"
    bind_port: int = 8787
    advertise_url: str = ""


class MeshCfg(BaseModel):
    psk: str = "CHANGE-ME"
    peers: list[str] = Field(default_factory=list)
    heartbeat_seconds: int = 10


class ModelsCfg(BaseModel):
    provider: str = "ollama"
    ollama_url: str = "http://127.0.0.1:11434"
    # Blank means "use whatever this machine's own hardware detection
    # recommends" (boddos/hardware.py, applied in NodeState.__init__) —
    # never trust a hand-edited number, or a hardcoded model name, that
    # drifts the moment you swap machines, add a GPU, or just have less
    # RAM than whoever picked the old default. Set explicitly to pin one.
    default_model: str = ""
    vision_model: str = ""


class AgentCfg(BaseModel):
    enabled: bool = False
    allowed_commands: list[str] = Field(default_factory=list)
    workdir: str = "~/boddos-agent"
    require_confirm: bool = True


class OgunCfg(BaseModel):
    # Ogun 3D's building tools: OpenSCAD modeling, Cantera combustion
    # checks, ngspice circuit simulation. Unlike screen/agent control these
    # don't touch the user's OS or files outside their own workdir, so
    # they're on by default — pure geometry/chemistry/circuit compute in a
    # constrained DSL, not arbitrary code execution.
    enabled: bool = True
    workdir: str = "~/.boddos/ogun"
    max_source_chars: int = 20000
    render_timeout_s: float = 25.0
    chemistry_mechanism: str = "gri30.yaml"
    # Free key from materialsproject.org/api — falls back to $MP_API_KEY.
    materials_api_key: str = ""


class ScreenCfg(BaseModel):
    # Screenshot + click/type control of THIS machine's own display.
    # Off by default; needs a real display (no-op on a headless node).
    enabled: bool = False
    require_confirm: bool = True
    # Vision model used to describe what's on screen; falls back to
    # models.vision_model when unset.
    vision_model: str = ""
    # The autonomous perceive-decide-act loop (`drive`) runs at full speed —
    # no artificial per-step delay — unless the caller explicitly asks to
    # watch it go slow. This does not affect the require_confirm gate above,
    # which still applies to raw click/type/press calls made directly.
    max_drive_steps: int = 12
    # A drive step whose target/text looks financial or destructive (pay,
    # delete, send money, sudo, ...) always pauses for an explicit human
    # "yes" before it executes, regardless of speed.
    require_confirm_for_sensitive: bool = True


class VoiceCfg(BaseModel):
    # Spoken replies via Piper — a real neural TTS engine (boddos/voice/tts.py)
    # instead of the browser's flat default synthesizer. Same split as every
    # other Ogun tool: the chat model only decides what to say; Piper is the
    # external "muscle" that makes it actually sound like something.
    tts_enabled: bool = True
    # Piper voice name, e.g. "en_US-amy-medium" — browse voice samples at
    # https://github.com/OHF-voice/piper1-gpl. Fetch it once with:
    # `python -m piper.download_voices <name> --download-dir <voices_dir>`
    tts_voice: str = "en_US-amy-medium"
    # Where downloaded voice models (<name>.onnx + <name>.onnx.json) live.
    voices_dir: str = "~/.boddos/voices"

    # Wake word + command listening via Vosk — a small, fast, fully offline
    # recognizer (boddos/voice/stt.py) instead of the browser's own
    # SpeechRecognition API, which on Chrome isn't actually local (it
    # streams audio to Google's servers) and doesn't exist at all on
    # Firefox. Same split again: recognition speed never depends on the
    # chat model. Falls back to the browser API automatically if no model
    # is downloaded yet.
    stt_enabled: bool = True
    # Download a model (~40MB for the small English one) from
    # https://alphacephei.com/vosk/models and unzip it here.
    stt_model_dir: str = "~/.boddos/stt/vosk-model-small-en-us-0.15"


class WeatherCfg(BaseModel):
    enabled: bool = True
    lat: float = 0.0
    lon: float = 0.0


class TranslateCfg(BaseModel):
    enabled: bool = True
    model: str = "llama3.1"


class CallingCfg(BaseModel):
    enabled: bool = False
    provider: str = "none"


class RoutingCfg(BaseModel):
    # Esu Pathfinder's wayfinding — geocoding + turn-by-turn directions.
    enabled: bool = True
    nominatim_url: str = "https://nominatim.openstreetmap.org"
    osrm_url: str = "https://router.project-osrm.org"


class FinderCfg(BaseModel):
    # Lost-device finder — BLE proximity for something you already own.
    # Read-only passive scanning, same tier as camera/sensor reads, so on
    # by default; needs a BLE radio (pip install 'boddos[finder]').
    enabled: bool = True


class SkillsCfg(BaseModel):
    # The Skill Portal: fetch -> RepoMix compress -> AST/Bandit gate ->
    # save -> one-click "muscle memory" run. Saving executes an AST/Bandit
    # scan either way, but still requires an explicit confirm — static
    # analysis is a real check, not a guarantee (see boddos/skills/portal.py).
    enabled: bool = True
    require_confirm: bool = True
    workdir: str = "~/.boddos/workspace_skills"
    max_repo_files: int = 400
    max_compressed_chars: int = 60000
    fetch_timeout_s: float = 45.0
    run_timeout_s: float = 20.0


class DroneCfg(BaseModel):
    enabled: bool = False
    endpoint: str = ""


class SmtpCfg(BaseModel):
    host: str = ""
    port: int = 587
    username: str = ""
    password: str = ""
    from_addr: str = ""
    use_tls: bool = True


class NotifyCfg(BaseModel):
    enabled: bool = True
    # SMS gateway URL template you control; {target} and {body} are substituted.
    sms_webhook: str = ""
    smtp: SmtpCfg = Field(default_factory=SmtpCfg)


class PushCfg(BaseModel):
    # Web Push (VAPID) so alerts reach the phone lock screen.
    # Generate keys with: `python -m boddos --new-vapid`
    enabled: bool = False
    vapid_public: str = ""
    vapid_private: str = ""
    subject: str = "mailto:you@example.com"
    store_file: str = "~/.boddos/push_subs.json"


class ServicesCfg(BaseModel):
    weather: WeatherCfg = Field(default_factory=WeatherCfg)
    translate: TranslateCfg = Field(default_factory=TranslateCfg)
    calling: CallingCfg = Field(default_factory=CallingCfg)
    routing: RoutingCfg = Field(default_factory=RoutingCfg)
    finder: FinderCfg = Field(default_factory=FinderCfg)
    drone: DroneCfg = Field(default_factory=DroneCfg)
    notify: NotifyCfg = Field(default_factory=NotifyCfg)
    push: PushCfg = Field(default_factory=PushCfg)


class TrustedContact(BaseModel):
    name: str
    channel: Literal["sms", "email", "webhook"] = "sms"
    target: str = ""


class GeoZone(BaseModel):
    name: str
    lat: float
    lon: float
    radius_m: float = 150.0
    kind: Literal["safe", "danger"] = "safe"


class SafetyCfg(BaseModel):
    trusted_contacts: list[TrustedContact] = Field(default_factory=list)
    broadcast: bool = True
    tracker_follow_threshold: int = 3
    geofences: list[GeoZone] = Field(default_factory=list)


class SecurityCfg(BaseModel):
    # Client (phone/UI) bearer-token auth. If require_auth and no api_token is
    # set, a token is generated at startup and printed once.
    require_auth: bool = False
    api_token: str = ""
    # TLS: serve HTTPS with a self-signed cert (generated if missing).
    tls_enabled: bool = False
    tls_cert: str = "~/.boddos/cert.pem"
    tls_key: str = "~/.boddos/key.pem"
    # Rate limiting.
    rate_per_sec: float = 5.0
    rate_burst: float = 20.0
    lockout_threshold: int = 8
    lockout_seconds: float = 300.0
    # Audit log location.
    audit_log: str = "~/.boddos/audit.log"
    # Encrypted vault file (unlocked via BODDOS_VAULT_PASSPHRASE).
    vault_file: str = "~/.boddos/vault.bin"
    # Optional TOTP 2FA on sensitive actions (agent, drone, vault writes).
    require_2fa: bool = False
    totp_secret: str = ""   # base32; provision via `python -m boddos.security.totp`


class AssistantCfg(BaseModel):
    # The assistant's spoken name and wake phrases (lowercase).
    name: str = "Ori"
    wake_words: list[str] = Field(default_factory=lambda: ["ori", "hey ori"])
    # Voice persona for text-to-speech greetings.
    greeting: str = "Yes?"


class Config(BaseModel):
    node: NodeCfg
    assistant: AssistantCfg = Field(default_factory=AssistantCfg)
    mesh: MeshCfg = Field(default_factory=MeshCfg)
    models: ModelsCfg = Field(default_factory=ModelsCfg)
    voice: VoiceCfg = Field(default_factory=VoiceCfg)
    agent: AgentCfg = Field(default_factory=AgentCfg)
    screen: ScreenCfg = Field(default_factory=ScreenCfg)
    ogun: OgunCfg = Field(default_factory=OgunCfg)
    skills: SkillsCfg = Field(default_factory=SkillsCfg)
    services: ServicesCfg = Field(default_factory=ServicesCfg)
    safety: SafetyCfg = Field(default_factory=SafetyCfg)
    security: SecurityCfg = Field(default_factory=SecurityCfg)

    @property
    def agent_workdir(self) -> Path:
        return Path(os.path.expanduser(self.agent.workdir))


def load_config(path: str | os.PathLike) -> Config:
    """Load and validate a config file, applying env overrides.

    Env overrides (handy for containers / CI):
      BODDOS_NODE_ID, BODDOS_BIND_PORT, BODDOS_MESH_PSK.
    """
    data = yaml.safe_load(Path(path).read_text()) or {}
    cfg = Config.model_validate(data)

    if v := os.environ.get("BODDOS_NODE_ID"):
        cfg.node.id = v
    if v := os.environ.get("BODDOS_BIND_PORT"):
        cfg.node.bind_port = int(v)
    if v := os.environ.get("BODDOS_MESH_PSK"):
        cfg.mesh.psk = v
    if v := os.environ.get("BODDOS_API_TOKEN"):
        cfg.security.api_token = v
    if v := os.environ.get("BODDOS_TOTP_SECRET"):
        cfg.security.totp_secret = v
    return cfg
