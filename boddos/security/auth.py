"""Authentication for mesh-to-mesh and client-to-node traffic.

Mesh auth (node <-> node): every inter-node request is HMAC-signed with the
shared PSK over (timestamp + nonce + body). The receiver verifies the signature,
rejects stale timestamps (replay window), and remembers recently-seen nonces to
block replays inside the window. This is a real improvement over sending the PSK
in a header — the secret never travels on the wire, and captured requests can't
be replayed.

Client auth (phone/UI -> node): optional bearer token. When enabled, /api/*
requires `Authorization: Bearer <token>` (or `?token=` for the WebSocket).
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import time


def constant_time_eq(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())


class MeshAuth:
    """HMAC-SHA256 request signing with replay protection."""

    def __init__(self, psk: str, max_skew_s: int = 30, nonce_ttl_s: int = 120):
        self._key = psk.encode()
        self.max_skew_s = max_skew_s
        self.nonce_ttl_s = nonce_ttl_s
        self._seen: dict[str, float] = {}

    def _mac(self, ts: str, nonce: str, body: bytes) -> str:
        msg = ts.encode() + b"." + nonce.encode() + b"." + body
        return hmac.new(self._key, msg, hashlib.sha256).hexdigest()

    def sign(self, body: bytes) -> dict[str, str]:
        ts = str(int(time.time()))
        nonce = secrets.token_hex(16)
        return {
            "X-Boddos-Timestamp": ts,
            "X-Boddos-Nonce": nonce,
            "X-Boddos-Sig": self._mac(ts, nonce, body),
        }

    def _gc(self, now: float) -> None:
        if len(self._seen) > 4096:
            for k, exp in list(self._seen.items()):
                if exp < now:
                    self._seen.pop(k, None)

    def verify(self, headers: dict, body: bytes) -> tuple[bool, str]:
        ts = headers.get("x-boddos-timestamp") or headers.get("X-Boddos-Timestamp")
        nonce = headers.get("x-boddos-nonce") or headers.get("X-Boddos-Nonce")
        sig = headers.get("x-boddos-sig") or headers.get("X-Boddos-Sig")
        if not (ts and nonce and sig):
            return False, "missing signature headers"
        now = time.time()
        try:
            if abs(now - int(ts)) > self.max_skew_s:
                return False, "stale timestamp"
        except ValueError:
            return False, "bad timestamp"
        expected = self._mac(ts, nonce, body)
        if not hmac.compare_digest(expected, sig):
            return False, "bad signature"
        if nonce in self._seen:
            return False, "replayed nonce"
        self._gc(now)
        self._seen[nonce] = now + self.nonce_ttl_s
        return True, "ok"


class ClientAuth:
    """Optional bearer-token gate for the phone/UI API."""

    def __init__(self, token: str | None, require: bool):
        self.token = token
        self.require = require and bool(token)

    @staticmethod
    def generate_token() -> str:
        return secrets.token_urlsafe(32)

    def check(self, authorization: str | None, query_token: str | None = None) -> bool:
        if not self.require:
            return True
        supplied = query_token
        if authorization and authorization.lower().startswith("bearer "):
            supplied = authorization[7:].strip()
        return bool(supplied) and constant_time_eq(supplied, self.token or "")
