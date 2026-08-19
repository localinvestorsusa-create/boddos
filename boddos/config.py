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
    default_model: str = "llama3.1"
    # Multimodal model for camera vision (pull it: `ollama pull llava`).
    vision_model: str = "llava"
    ram_gb: int = 8
    has_gpu: bool = False


class AgentCfg(BaseModel):
    enabled: bool = False
    allowed_commands: list[str] = Field(default_factory=list)
    workdir: str = "~/boddos-agent"
    require_confirm: bool = True


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


class Config(BaseModel):
    node: NodeCfg
    mesh: MeshCfg = Field(default_factory=MeshCfg)
    models: ModelsCfg = Field(default_factory=ModelsCfg)
    agent: AgentCfg = Field(default_factory=AgentCfg)
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
