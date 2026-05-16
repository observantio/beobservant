"""
Shared query parameter helpers for Grafana router endpoints.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the
License. You may obtain a copy of the License at
http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

import re

UID_QUERY_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,200}$")


def normalize_optional_param(value: object) -> str | None:
    if value is None or not isinstance(value, str):
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if normalized.lower() in {"null", "none", "undefined"}:
        return None
    return normalized


def show_hidden_enabled(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return isinstance(value, str) and value.strip().lower() == "true"


def is_valid_uid_query(value: str) -> bool:
    return bool(UID_QUERY_PATTERN.fullmatch(value))
