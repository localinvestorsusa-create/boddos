"""Routing: pick the best node in the mesh to serve a model request.

Policy (in order):
  1. If this node can serve the model locally, prefer it (lowest latency).
  2. Otherwise pick an alive peer that has the model, preferring hosts with
     the most RAM / a GPU.
  3. Fall back to any host peer (it may pull the model on demand).
"""
from __future__ import annotations

from .node import MeshRegistry, NodeInfo


class Router:
    def __init__(self, registry: MeshRegistry):
        self.registry = registry

    def select_model_node(self, model: str, local_models: list[str]) -> NodeInfo:
        me = self.registry.me
        if model in local_models or "*" in local_models:
            return me

        candidates = [p for p in self.registry.alive_peers() if p.role == "host"]

        have_model = [p for p in candidates if model in p.models]
        pool = have_model or candidates
        if not pool:
            # Nobody else can help; try locally anyway (may pull on demand).
            return me

        pool.sort(key=lambda p: (p.has_gpu, p.ram_gb), reverse=True)
        return pool[0]
