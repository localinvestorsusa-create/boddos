"""Time-based one-time passwords (RFC 6238) — pure stdlib.

Optional second factor for sensitive actions (OS agent, drone, vault writes).
Provision the secret once, add it to an authenticator app (Google Authenticator,
Aegis, 1Password), and BODDOS can require a 6-digit code for those actions.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote


def generate_secret() -> str:
    """Return a base32 secret suitable for authenticator apps."""
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def _hotp(secret_b32: str, counter: int, digits: int = 6) -> str:
    pad = "=" * (-len(secret_b32) % 8)
    key = base64.b32decode(secret_b32.upper() + pad)
    mac = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = mac[-1] & 0x0F
    code = (struct.unpack(">I", mac[offset:offset + 4])[0] & 0x7FFFFFFF) % (10 ** digits)
    return str(code).zfill(digits)


def verify(secret_b32: str, code: str, window: int = 1, step: int = 30) -> bool:
    """Verify a code, allowing +/- `window` steps for clock skew."""
    if not secret_b32 or not code:
        return False
    code = code.strip()
    counter = int(time.time() // step)
    for w in range(-window, window + 1):
        if hmac.compare_digest(_hotp(secret_b32, counter + w), code):
            return True
    return False


def provisioning_uri(secret_b32: str, account: str = "me", issuer: str = "BODDOS") -> str:
    label = quote(f"{issuer}:{account}")
    return (f"otpauth://totp/{label}?secret={secret_b32}"
            f"&issuer={quote(issuer)}&algorithm=SHA1&digits=6&period=30")
    # Provision from the CLI: `python -m boddos --new-totp`
