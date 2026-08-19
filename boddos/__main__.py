"""BODDOS node entrypoint: `python -m boddos --config config/boddos.yaml`."""
from __future__ import annotations

import argparse
import sys

import uvicorn

from .config import load_config
from .api import build_app


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="boddos", description="Run a BODDOS node.")
    parser.add_argument("--config", "-c", default="config/boddos.yaml",
                        help="path to node config YAML")
    parser.add_argument("--host", default=None, help="override bind host")
    parser.add_argument("--port", type=int, default=None, help="override bind port")
    args = parser.parse_args(argv)

    try:
        cfg = load_config(args.config)
    except FileNotFoundError:
        print(f"config not found: {args.config}\n"
              f"Copy config/boddos.example.yaml and edit it.", file=sys.stderr)
        return 2

    host = args.host or cfg.node.bind_host
    port = args.port or cfg.node.bind_port
    app = build_app(cfg)

    print(f"BODDOS node '{cfg.node.id}' ({cfg.node.role}) on http://{host}:{port}")
    print(f"Open the phone UI at http://<this-lan-ip>:{port}/")
    uvicorn.run(app, host=host, port=port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
