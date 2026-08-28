"""Join tokens — the "one download, boom, already connected" mechanism.

A running node can print a short token that encodes just enough to let a
second machine join its mesh with zero manual config editing: the shared
PSK and this node's advertise URL. The installer decodes it and writes
both straight into the new node's config instead of generating a fresh
(non-matching) PSK and an empty peer list.

Deliberately not a JWT or anything with expiry/signing — this token's
only job is to save typing a PSK and a URL correctly by hand. Anyone who
already has it could reach your node anyway (it's a URL); the PSK itself
is what actually gates the mesh handshake, and rotating it is just
editing mesh.psk on every node.
"""
from __future__ import annotations

import base64
import json

_PREFIX = "bd1."


def encode(psk: str, peer_url: str) -> str:
    payload = json.dumps({"psk": psk, "peer": peer_url}, separators=(",", ":")).encode()
    return _PREFIX + base64.urlsafe_b64encode(payload).rstrip(b"=").decode()


def decode(token: str) -> dict:
    token = token.strip()
    if not token.startswith(_PREFIX):
        raise ValueError(f"not a boddos join token (expected it to start with {_PREFIX!r})")
    body = token[len(_PREFIX):]
    padded = body + "=" * (-len(body) % 4)
    try:
        payload = json.loads(base64.urlsafe_b64decode(padded))
    except Exception as e:
        raise ValueError(f"malformed join token: {e}") from e
    if not isinstance(payload, dict) or "psk" not in payload or "peer" not in payload:
        raise ValueError("malformed join token: missing psk/peer")
    return {"psk": str(payload["psk"]), "peer": str(payload["peer"])}
