"""
Loki HTTP client with integrated Prometheus metrics observation.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the
License. You may obtain a copy of the License at
http://www.apache.org/licenses/LICENSE-2.0
"""

import logging
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import httpx
from custom_types.json import JSONDict

logger = logging.getLogger(__name__)

QueryParamScalar = str | int | float | bool
QueryParamValue = QueryParamScalar | Sequence[QueryParamScalar]
QueryParams = Mapping[str, QueryParamValue]


@dataclass(frozen=True, slots=True)
class LokiGetJsonRequest:
    client: httpx.AsyncClient
    url: str
    params: QueryParams
    headers: dict[str, str]
    quiet: bool = False


class LokiHttpClient:
    def __init__(self, metrics: dict[str, float] | None = None) -> None:
        self._metrics: dict[str, float] = metrics if metrics is not None else {}

    def _observe(self, metric: str, value: float = 1.0) -> None:
        self._metrics[metric] = self._metrics.get(metric, 0.0) + value

    async def timed_get_json(
        self,
        client: httpx.AsyncClient,
        url: str,
        *,
        params: QueryParams,
        headers: dict[str, str],
    ) -> JSONDict:
        started = time.perf_counter()
        try:
            response = await client.get(url, params=params, headers=headers)
            response.raise_for_status()
            payload = response.json()
            return payload if isinstance(payload, dict) else {}
        finally:
            self._observe("loki_query_total")
            self._observe("loki_query_duration_sum_seconds", time.perf_counter() - started)

    async def safe_get_json(
        self,
        request: LokiGetJsonRequest,
    ) -> JSONDict | None:
        try:
            return await self.timed_get_json(
                request.client,
                request.url,
                params=request.params,
                headers=request.headers,
            )
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            self._observe("loki_query_errors_total")
            is_client_error = 400 <= status < 500
            if request.quiet or is_client_error:
                logger.debug("Loki %s error for %s", status, request.url)
            else:
                logger.warning("Loki server error %s for %s", status, request.url)
        except httpx.HTTPError as e:
            self._observe("loki_query_errors_total")
            log = logger.debug if request.quiet else logger.warning
            log("Loki request failed for %s: %s", request.url, e)
        return None
