"""Encrypted-at-rest secret vault.

Stores small secrets (contact details, API keys, tokens) encrypted with a key
derived from a passphrase via scrypt. Uses AES-GCM (authenticated encryption) so
tampering is detected on read. The passphrase is supplied at runtime
(env `BODDOS_VAULT_PASSPHRASE`) and never written to disk.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt


class SecretVault:
    MAGIC = b"BODDOSV1"

    def __init__(self, path: str | Path, passphrase: str | None = None):
        self.path = Path(path).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._passphrase = (passphrase or os.environ.get("BODDOS_VAULT_PASSPHRASE") or "").encode()

    @property
    def unlocked(self) -> bool:
        return bool(self._passphrase)

    def _derive(self, salt: bytes) -> bytes:
        kdf = Scrypt(salt=salt, length=32, n=2**15, r=8, p=1)
        return kdf.derive(self._passphrase)

    def save(self, data: dict) -> None:
        if not self.unlocked:
            raise RuntimeError("vault locked: set BODDOS_VAULT_PASSPHRASE")
        salt = os.urandom(16)
        nonce = os.urandom(12)
        key = self._derive(salt)
        ct = AESGCM(key).encrypt(nonce, json.dumps(data).encode(), self.MAGIC)
        self.path.write_bytes(self.MAGIC + salt + nonce + ct)
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass

    def load(self) -> dict:
        if not self.path.exists():
            return {}
        if not self.unlocked:
            raise RuntimeError("vault locked: set BODDOS_VAULT_PASSPHRASE")
        raw = self.path.read_bytes()
        if raw[:8] != self.MAGIC:
            raise ValueError("not a BODDOS vault file")
        salt, nonce, ct = raw[8:24], raw[24:36], raw[36:]
        key = self._derive(salt)
        pt = AESGCM(key).decrypt(nonce, ct, self.MAGIC)
        return json.loads(pt.decode())

    def set(self, name: str, value) -> None:
        data = self.load()
        data[name] = value
        self.save(data)

    def get(self, name: str, default=None):
        return self.load().get(name, default)
