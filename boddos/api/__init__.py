"""HTTP + WebSocket API that wires the whole node together."""
from .server import build_app

__all__ = ["build_app"]
