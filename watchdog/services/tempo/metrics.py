"""
Tempo metrics queries and processing logic, providing functions to query Mimir for trace metrics derived from Tempo and
to extract aggregated values for alert evaluation.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the
License. You may obtain a copy of the License at
http://www.apache.org/licenses/LICENSE-2.0
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field

import httpx

from config import config
from custom_types.json import JSONDict

logger = logging.getLogger(__name__)


QueryParams = dict[str, str | int | float | bool]


def _empty_response() -> JSONDict:
    return {"status": "error", "data": {"result": []}}


def _default_scope_headers(tenant_id: str) -> dict[str, str]:
    return {"X-Scope-OrgID": tenant_id}


@dataclass
class QueryMetricsRangeParams:
    promql: str
    start_us: int | None = None
    end_us: int | None = None
    step_s: int = 300
    tenant_id: str = field(default_factory=lambda: config.DEFAULT_ORG_ID)
    mimir_url: str = field(default_factory=lambda: config.MIMIR_URL)
    get_headers: Callable[[str], dict[str, str]] | None = None
    observe: Callable[[str, float], None] | None = None
    metrics_enabled: bool = True


async def query_metrics_range(
    client: httpx.AsyncClient,
    params: QueryMetricsRangeParams,
) -> tuple[JSONDict, bool]:
    if not params.metrics_enabled:
        return _empty_response(), False

    headers_fn = params.get_headers or _default_scope_headers
    observe = params.observe or (lambda _m, _v: None)

    qparams: QueryParams = {"query": params.promql, "step": params.step_s}
    if params.start_us:
        qparams["start"] = int(params.start_us / 1_000_000)
    if params.end_us:
        qparams["end"] = int(params.end_us / 1_000_000)

    try:
        resp = await client.get(
            f"{params.mimir_url.rstrip('/')}/api/v1/query_range",
            params=qparams,
            headers=headers_fn(params.tenant_id),
        )
        resp.raise_for_status()
        observe("tempo_metrics_queries_total", 1.0)
        payload = resp.json()
        return (payload if isinstance(payload, dict) else _empty_response()), True
    except httpx.HTTPError as e:
        observe("tempo_metrics_query_errors_total", 1.0)
        logger.debug("Mimir metrics query failed: %s", e)
        return _empty_response(), False


def extract_metric_values(metrics_resp: object) -> list[list[object]]:
    if not isinstance(metrics_resp, dict):
        return []
    results = (metrics_resp.get("data") or {}).get("result")
    if not results:
        return []

    ts_map: dict[int, int] = {}
    for series in results:
        for ts, v in series.get("values") or []:
            try:
                key = int(float(ts))
                ts_map[key] = ts_map.get(key, 0) + int(float(v))
            except (TypeError, ValueError):
                continue

    return [[ts, str(ts_map[ts])] for ts in sorted(ts_map)]
