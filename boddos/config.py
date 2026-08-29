"""Configuration for a bare BODDOS node — minimal skeleton, ready for
whatever gets built on top of it next."""
from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import BaseModel


class NodeCfg(BaseModel):
    id: str
    name: str = ""
    bind_host: str = "0.0.0.0"
    bind_port: int = 8787


class Config(BaseModel):
    node: NodeCfg


def load_config(path: str | os.PathLike) -> Config:
    """Load and validate a config file, applying env overrides.

    Env overrides (handy for containers / CI): BODDOS_NODE_ID, BODDOS_BIND_PORT.
    """
    data = yaml.safe_load(Path(path).read_text()) or {}
    cfg = Config.model_validate(data)

    if v := os.environ.get("BODDOS_NODE_ID"):
        cfg.node.id = v
    if v := os.environ.get("BODDOS_BIND_PORT"):
        cfg.node.bind_port = int(v)
    return cfg
