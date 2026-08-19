"""Node identity and the in-memory registry of known mesh peers."""
from __future__ import annotations

import time
from dataclasses import dataclass, field, asdict


@dataclass
class NodeInfo:
    """What one machine advertises to the rest of the mesh."""

    id: str
    name: str
    role: str                    # "host" | "edge"
    url: str                     # advertise_url other nodes reach it at
    ram_gb: int = 0
    has_gpu: bool = False
    models: list[str] = field(default_factory=list)
    last_seen: float = field(default_factory=time.time)

    def touch(self) -> None:
        self.last_seen = time.time()

    def is_alive(self, ttl: float) -> bool:
        return (time.time() - self.last_seen) <= ttl

    def to_dict(self) -> dict:
        return asdict(self)


class MeshRegistry:
    """Tracks self + peer nodes. Thread-unsafe by design (single event loop)."""

    def __init__(self, me: NodeInfo, ttl: float = 30.0):
        self.me = me
        self.ttl = ttl
        self._peers: dict[str, NodeInfo] = {}

    def upsert(self, info: NodeInfo) -> None:
        if info.id == self.me.id:
            return
        existing = self._peers.get(info.id)
        if existing:
            existing.name = info.name
            existing.role = info.role
            existing.url = info.url
            existing.ram_gb = info.ram_gb
            existing.has_gpu = info.has_gpu
            existing.models = info.models
            existing.touch()
        else:
            self._peers[info.id] = info

    def from_hello(self, payload: dict) -> None:
        self.upsert(
            NodeInfo(
                id=payload["id"],
                name=payload.get("name", ""),
                role=payload.get("role", "edge"),
                url=payload.get("url", ""),
                ram_gb=int(payload.get("ram_gb", 0)),
                has_gpu=bool(payload.get("has_gpu", False)),
                models=list(payload.get("models", [])),
            )
        )

    def alive_peers(self) -> list[NodeInfo]:
        return [p for p in self._peers.values() if p.is_alive(self.ttl)]

    def all_nodes(self) -> list[NodeInfo]:
        return [self.me, *self.alive_peers()]
