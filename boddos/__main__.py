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
    parser.add_argument("--new-totp", action="store_true",
                        help="generate a TOTP 2FA secret + provisioning URI, then exit")
    parser.add_argument("--new-vapid", action="store_true",
                        help="generate Web Push VAPID keys for services.push, then exit")
    args = parser.parse_args(argv)

    if args.new_totp:
        from .security import totp
        secret = totp.generate_secret()
        print("Add to config security.totp_secret (or env BODDOS_TOTP_SECRET):")
        print(f"  {secret}\n")
        print("Scan in your authenticator app:")
        print(f"  {totp.provisioning_uri(secret)}")
        return 0

    if args.new_vapid:
        try:
            from py_vapid import Vapid  # bundled with pywebpush
            import base64
        except Exception:
            print("Install push support first: pip install 'boddos[push]'", file=sys.stderr)
            return 2
        v = Vapid()
        v.generate_keys()

        def b64(raw: bytes) -> str:
            return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

        priv = b64(v.private_key.private_numbers().private_value.to_bytes(32, "big"))
        pub = v.public_key.public_bytes(
            __import__("cryptography").hazmat.primitives.serialization.Encoding.X962,
            __import__("cryptography").hazmat.primitives.serialization.PublicFormat.UncompressedPoint,
        )
        print("Add to config under services.push:")
        print(f"  enabled: true")
        print(f"  vapid_public: \"{b64(pub)}\"")
        print(f"  vapid_private: \"{priv}\"")
        return 0

    try:
        cfg = load_config(args.config)
    except FileNotFoundError:
        print(f"config not found: {args.config}\n"
              f"Copy config/boddos.example.yaml and edit it.", file=sys.stderr)
        return 2

    host = args.host or cfg.node.bind_host
    port = args.port or cfg.node.bind_port
    app = build_app(cfg)

    ssl_kw = {}
    scheme = "http"
    if cfg.security.tls_enabled:
        from .security.tls import ensure_self_signed
        cert, key = ensure_self_signed(
            cfg.security.tls_cert, cfg.security.tls_key,
            ips=["127.0.0.1"],
        )
        ssl_kw = {"ssl_certfile": str(cert), "ssl_keyfile": str(key)}
        scheme = "https"

    print(f"BODDOS node '{cfg.node.id}' ({cfg.node.role}) on {scheme}://{host}:{port}")
    print(f"Open the phone UI at {scheme}://<this-lan-ip>:{port}/")
    if cfg.security.require_auth:
        print("[security] client auth required — enter your API token in the UI.")
    uvicorn.run(app, host=host, port=port, log_level="info", **ssl_kw)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
