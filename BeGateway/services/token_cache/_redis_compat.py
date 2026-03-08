"""Optional Redis dependency loader for token cache implementations."""

from __future__ import annotations

try:
    import redis as _redis
except ImportError:
    _redis = None

redis = _redis

__all__ = ["redis"]
