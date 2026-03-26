"""
Helper functions for OTLP agent management.

This module extracts shared routines from AgentService so that the main
service class remains lightweight and focused on orchestration. Helpers
include ID generation, registry updates, and Mimir query logic.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from datetime import datetime, timezone, timedelta
from typing import TypedDict

import httpx
from config import config
from models.observability.agent_models import AgentHeartbeat, AgentInfo
from custom_types.json import JSONDict


class KeyActivity(TypedDict):
    metrics_active: bool
    metrics_count: int


class KeyVolumePoint(TypedDict):
    ts: int
    value: int


ATTR_HOST_NAME = "host.name"
ATTR_HOST_HOSTNAME = "host.hostname"
METRIC_COUNT_QUERY = "count({__name__=~\".+\"})"


def make_agent_id(name: str, tenant_id: str) -> str:
    return f"{tenant_id}:{name}" if tenant_id else name


def mimir_prometheus_url(base_url: str, path: str) -> str:
    base = str(base_url or "").strip().rstrip("/")
    suffix = str(path or "").strip().lstrip("/")
    if not base:
        return f"/{suffix}" if suffix else "/"
    if base.endswith("/prometheus"):
        return f"{base}/{suffix}"
    return f"{base}/prometheus/{suffix}"


def update_agent_registry(registry: dict[str, AgentInfo], heartbeat: AgentHeartbeat) -> None:
    ts = heartbeat.timestamp or datetime.now(timezone.utc)
    agent_id = make_agent_id(heartbeat.name, heartbeat.tenant_id)
    attributes = heartbeat.attributes or {}
    host_name = attributes.get(ATTR_HOST_NAME) or attributes.get(ATTR_HOST_HOSTNAME)
    info = registry.get(agent_id)
    if not info:
        info = AgentInfo(
            id=agent_id,
            name=heartbeat.name,
            tenant_id=heartbeat.tenant_id,
            host_name=str(host_name) if host_name else None,
            last_seen=ts,
            signals=[heartbeat.signal] if heartbeat.signal else [],
            attributes=attributes,
        )
    else:
        info.last_seen = ts
        if host_name:
            info.host_name = str(host_name)
        if heartbeat.signal and heartbeat.signal not in info.signals:
            info.signals.append(heartbeat.signal)
    registry[agent_id] = info


def extract_metrics_count(payload: JSONDict) -> int:
    data = payload.get("data")
    if not isinstance(data, dict):
        return 0
    result = data.get("result")
    if not isinstance(result, list) or not result:
        return 0
    first = result[0]
    if not isinstance(first, dict):
        return 0
    value = first.get("value")
    if not isinstance(value, list) or len(value) < 2:
        return 0
    count = value[1]
    try:
        return int(float(str(count)))
    except (TypeError, ValueError):
        return 0


async def query_key_activity(key_value: str, mimir_client: httpx.AsyncClient) -> KeyActivity:
    metrics_active = False
    metrics_count = 0

    try:
        response = await mimir_client.get(
            mimir_prometheus_url(config.MIMIR_URL, "api/v1/query"),
            params={"query": METRIC_COUNT_QUERY},
            headers={"X-Scope-OrgID": key_value},
        )
        response.raise_for_status()
        payload_raw = response.json()
        if not isinstance(payload_raw, dict):
            raise ValueError("Unexpected Mimir payload")
        payload: JSONDict = payload_raw
        metrics_count = extract_metrics_count(payload)
        metrics_active = metrics_count > 0
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        metrics_active = False

    return {
        "metrics_active": metrics_active,
        "metrics_count": metrics_count,
    }


def extract_metrics_series(payload: JSONDict) -> list[KeyVolumePoint]:
    data = payload.get("data")
    if not isinstance(data, dict):
        return []
    result = data.get("result")
    if not isinstance(result, list) or not result:
        return []
    first = result[0]
    if not isinstance(first, dict):
        return []
    values = first.get("values")
    if not isinstance(values, list):
        return []

    points: list[KeyVolumePoint] = []
    for entry in values:
        if not isinstance(entry, list) or len(entry) < 2:
            continue
        raw_ts, raw_value = entry[0], entry[1]
        try:
            points.append({
                "ts": int(float(str(raw_ts))),
                "value": int(float(str(raw_value))),
            })
        except (TypeError, ValueError):
            continue
    return points


async def query_key_volume_series(
    key_value: str,
    mimir_client: httpx.AsyncClient,
    *,
    minutes: int = 60,
    step_seconds: int = 300,
) -> list[KeyVolumePoint]:
    now = datetime.now(timezone.utc)
    start = now - timedelta(minutes=max(5, minutes))

    try:
        response = await mimir_client.get(
            mimir_prometheus_url(config.MIMIR_URL, "api/v1/query_range"),
            params={
                "query": METRIC_COUNT_QUERY,
                "start": int(start.timestamp()),
                "end": int(now.timestamp()),
                "step": max(60, step_seconds),
            },
            headers={"X-Scope-OrgID": key_value},
        )
        response.raise_for_status()
        payload_raw = response.json()
        if not isinstance(payload_raw, dict):
            raise ValueError("Unexpected Mimir payload")
        payload: JSONDict = payload_raw
        return extract_metrics_series(payload)
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        return []
