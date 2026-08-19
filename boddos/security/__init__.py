"""Security layer: mesh request signing, client auth, audit, rate limiting,
encrypted secret vault, and TLS helpers.

Defense in depth for a system that runs on your own network but holds sensitive
capabilities (OS agent, location, contacts). Nothing here reaches the public
internet; it hardens the trust boundaries you already own.
"""
from .auth import MeshAuth, ClientAuth, constant_time_eq
from .audit import AuditLog
from .ratelimit import RateLimiter
from .vault import SecretVault
from . import totp

__all__ = [
    "MeshAuth",
    "ClientAuth",
    "constant_time_eq",
    "AuditLog",
    "RateLimiter",
    "SecretVault",
    "totp",
]
