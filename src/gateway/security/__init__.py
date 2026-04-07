"""Gateway security primitives."""

from .instance_lock import GatewayInstanceLock, GatewayInstanceLockError

__all__ = [
    "GatewayInstanceLock",
    "GatewayInstanceLockError",
]
