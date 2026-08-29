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
    print(f"[setup] review {target} before relying on it: mesh.psk is a placeholder, "
          f"safety.trusted_contacts has a placeholder number.")
    return True


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
    parser.add_argument("--join-code", action="store_true",
                        help="print a one-line token + command a second machine can use to "
                             "join this node's mesh with zero manual config editing, then exit")
    args = parser.parse_args(argv)

    if args.join_code:
        from .join import encode
        if not _bootstrap_config(args.config):
            print(f"config not found: {args.config}\n"
                  f"Copy config/boddos.example.yaml and edit it, or run this once the node "
                  f"has been installed.", file=sys.stderr)
            return 2
        cfg = load_config(args.config)
        peer = cfg.node.advertise_url or f"http://<this-machine-ip>:{cfg.node.bind_port}"
        token = encode(cfg.mesh.psk, peer)
        print("On the machine you want to add, run the same install one-liner you used here,")
        print("with this token in front of it — it joins this node's mesh automatically:\n")
        print(f"  BODDOS_JOIN={token} \\")
        print("  curl -fsSL <the install.sh URL you used> | bash -s -- --join $BODDOS_JOIN\n")
        print("(or, from an existing clone: BODDOS_JOIN=" + token + " ./install.sh)")
        return 0

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

    if not _bootstrap_config(args.config):
        print(f"config not found: {args.config}\n"
              f"Copy config/boddos.example.yaml and edit it.", file=sys.stderr)
        return 2
    cfg = load_config(args.config)

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
