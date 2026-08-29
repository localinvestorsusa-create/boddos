"""BODDOS node entrypoint: `python -m boddos --config config/boddos.yaml`."""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

import uvicorn

from .config import load_config
from .api import build_app


def _bootstrap_config(path: str) -> bool:
    """First run, no config yet: copy the example next to `path` instead of
    hard-failing on something a first-time user wouldn't know to do
    themselves. Returns True if `path` exists (already did, or just got
    created)."""
    target = Path(path)
    if target.exists():
        return True
    example = target.with_name("boddos.example.yaml")
    if not example.exists():
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(example, target)
    print(f"[setup] no {target} yet — created it from {example.name}.")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="boddos", description="Run a BODDOS node.")
    parser.add_argument("--config", "-c", default="config/boddos.yaml",
                        help="path to node config YAML")
    parser.add_argument("--host", default=None, help="override bind host")
    parser.add_argument("--port", type=int, default=None, help="override bind port")
    args = parser.parse_args(argv)

    if not _bootstrap_config(args.config):
        print(f"config not found: {args.config}\n"
              f"Copy config/boddos.example.yaml and edit it.", file=sys.stderr)
        return 2
    cfg = load_config(args.config)

    host = args.host or cfg.node.bind_host
    port = args.port or cfg.node.bind_port
    cfg.node.bind_host = host
    cfg.node.bind_port = port
    app = build_app(cfg)

    print(f"BODDOS node '{cfg.node.id}' on http://{host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
