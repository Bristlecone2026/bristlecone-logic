"""
Bristlecone Guard (Bark Security Tier)
Deterministic pre-socket DNS pinning and SSRF defense for autonomous agent tooling.
"""

from .socket_guard import SocketGuard

__version__ = "0.5.1"
__all__ = ["SocketGuard"]
