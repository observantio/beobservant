"""
Grafana datasource payload helpers.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the
License. You may obtain a copy of the License at
http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

import uuid

from custom_types.json import JSONDict
from db_models import GrafanaDatasource


def sanitize_datasource_payload(payload: JSONDict, *, is_owner: bool) -> JSONDict:
    if is_owner:
        return payload
    sanitized = dict(payload)
    for key in ("password", "basicAuthPassword", "secureJsonData"):
        if key in sanitized:
            sanitized[key] = None
    return sanitized


def is_safe_system_datasource(datasource: object) -> bool:
    return bool(
        getattr(datasource, "is_default", False)
        or getattr(datasource, "isDefault", False)
        or getattr(datasource, "read_only", False)
        or getattr(datasource, "readOnly", False)
    )


def normalize_datasource_name(name: str | None) -> str:
    return str(name or "").strip().lower()


def build_internal_datasource_name(display_name: str, user_id: str) -> str:
    suffix = uuid.uuid4().hex[:6]
    return f"{display_name}__bo_{str(user_id)[:8]}_{suffix}"


def merge_json_payload(existing: JSONDict | None, incoming: JSONDict | None) -> JSONDict:
    base = dict(existing or {})
    base.update(dict(incoming or {}))
    return base


def enrich_datasource_payload(
    payload: JSONDict,
    *,
    db_ds: GrafanaDatasource | None,
    user_id: str,
    is_unregistered_safe_system: bool = False,
) -> JSONDict:
    is_owner = bool(db_ds and db_ds.created_by == user_id)
    if db_ds and db_ds.name:
        payload["name"] = db_ds.name
    payload = sanitize_datasource_payload(payload, is_owner=is_owner)
    payload["created_by"] = db_ds.created_by if db_ds else None
    payload["is_hidden"] = bool(db_ds and user_id in (db_ds.hidden_by or []))
    payload["is_owned"] = is_owner
    payload["visibility"] = db_ds.visibility if db_ds else ("system" if is_unregistered_safe_system else "private")
    shared_group_ids = [group.id for group in (db_ds.shared_groups or [])] if db_ds else []
    payload["shared_group_ids"] = shared_group_ids
    payload["sharedGroupIds"] = shared_group_ids
    return payload
