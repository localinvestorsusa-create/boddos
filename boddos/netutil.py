"""Small real network helpers — no LAN discovery/broadcast here, just
enough to stop asking a human to type their own machine's IP address."""
from __future__ import annotations

import socket


def detect_lan_ip() -> str:
    """This machine's LAN-facing IP address, best-effort.

    Opens a UDP "connection" to a public address — UDP connect() never
    actually sends a packet, it just asks the OS routing table which local
    interface/IP would be used to reach that destination, so this works
    even fully offline and needs no real connectivity. Falls back to
    127.0.0.1 if the OS can't answer (e.g. no network interfaces at all).
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
