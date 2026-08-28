"""Mesh layer: node identity, peer registry, event bus, and routing."""
from .node import NodeInfo, MeshRegistry
from .router import Router

__all__ = ["NodeInfo", "MeshRegistry", "Router"]
