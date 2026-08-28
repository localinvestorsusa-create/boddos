"""Tiny in-process event bus with WebSocket fan-out.

Nodes and the phone UI subscribe over a WebSocket; safety alerts, sensor updates,
and mesh changes are published to everyone. Cross-node delivery is handled by the
server forwarding events to peers' /mesh/event endpoint.
"""
from __future__ import annotations

import asyncio
from typing import Any


class EventBus:
    def __init__(self) -> None:
        self._subs: set[asyncio.Queue] = set()

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._subs.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subs.discard(q)

    async def publish(self, event: dict[str, Any]) -> None:
        for q in list(self._subs):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass
