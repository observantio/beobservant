"""
Observability utilities for rate limiting in Watchdog middleware.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the
License. You may obtain a copy of the License at
http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

import logging
import threading

logger = logging.getLogger(__name__)

_fallback_lock = threading.Lock()
_RATE_LIMIT_FALLBACK_TOTAL = 0
_rate_limit_fallback_by_mode: dict[str, int] = {"memory": 0, "deny": 0, "allow": 0}


def record_fallback_event(mode: str, reason: str) -> None:
    with _fallback_lock:
        total = _RATE_LIMIT_FALLBACK_TOTAL + 1
        globals()["_RATE_LIMIT_FALLBACK_TOTAL"] = total
        _rate_limit_fallback_by_mode[mode] = _rate_limit_fallback_by_mode.get(mode, 0) + 1
    logger.warning(
        "rate_limit_fallback_event total=%s mode=%s reason=%s",
        _RATE_LIMIT_FALLBACK_TOTAL,
        mode,
        reason,
    )


def get_rate_limit_observability_snapshot() -> dict[str, int]:
    with _fallback_lock:
        return {
            "fallback_total": _RATE_LIMIT_FALLBACK_TOTAL,
            "fallback_memory": _rate_limit_fallback_by_mode.get("memory", 0),
            "fallback_deny": _rate_limit_fallback_by_mode.get("deny", 0),
            "fallback_allow": _rate_limit_fallback_by_mode.get("allow", 0),
        }
