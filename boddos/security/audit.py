"""Append-only, tamper-evident audit log for sensitive actions.

Every sensitive event (OS-agent run, duress trigger, call placed, auth failure)
is written as one JSON line. Each entry carries a hash chain: `prev_hash` links
to the previous entry so silent deletion/edit of history is detectable
(`verify_chain`). The log lives on the node's disk only.
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
from pathlib import Path


class AuditLog:
    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _last_hash(self) -> str:
        if not self.path.exists():
            return "0" * 64
        last = ""
        with self.path.open("rb") as f:
            for line in f:
                if line.strip():
                    last = line.decode(errors="replace")
        if not last:
            return "0" * 64
        try:
            return json.loads(last).get("hash", "0" * 64)
        except Exception:
            return "0" * 64

    def record(self, action: str, detail: dict | None = None, actor: str = "node") -> dict:
        with self._lock:
            prev = self._last_hash()
            entry = {
                "ts": time.time(),
                "actor": actor,
                "action": action,
                "detail": detail or {},
                "prev_hash": prev,
            }
            body = json.dumps(entry, sort_keys=True, separators=(",", ":"))
            entry["hash"] = hashlib.sha256((prev + body).encode()).hexdigest()
            with self.path.open("a") as f:
                f.write(json.dumps(entry, separators=(",", ":")) + "\n")
            return entry

    def verify_chain(self) -> tuple[bool, int]:
        """Return (intact, entries_checked)."""
        if not self.path.exists():
            return True, 0
        prev = "0" * 64
        count = 0
        for line in self.path.read_text().splitlines():
            if not line.strip():
                continue
            entry = json.loads(line)
            stored = entry.pop("hash", "")
            if entry.get("prev_hash") != prev:
                return False, count
            body = json.dumps(entry, sort_keys=True, separators=(",", ":"))
            if hashlib.sha256((prev + body).encode()).hexdigest() != stored:
                return False, count
            prev = stored
            count += 1
        return True, count

    def tail(self, n: int = 50) -> list[dict]:
        if not self.path.exists():
            return []
        lines = [l for l in self.path.read_text().splitlines() if l.strip()]
        return [json.loads(l) for l in lines[-n:]]
