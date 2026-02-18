"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""
import asyncio
import json
import logging
import time
from typing import Any, Dict, List, Optional

import httpx

from config import config
from middleware.resilience import with_retry, with_timeout
from models.observability.tempo_models import Span, Trace, TraceQuery, TraceResponse
from services.common.http_client import create_async_client

logger = logging.getLogger(__name__)

_SERVICE_NAME_KEY = "service.name"
_SERVICE_ALIAS_KEY = "service"
_SERVICE_KEYS = [_SERVICE_NAME_KEY, _SERVICE_ALIAS_KEY]
_OTLP_VALUE_TYPES = ("stringValue", "intValue", "boolValue", "doubleValue")


class TempoService:
    def __init__(self, tempo_url: str = config.TEMPO_URL):
        self.tempo_url = tempo_url.rstrip("/")
        self.timeout = config.DEFAULT_TIMEOUT
        self._client = create_async_client(self.timeout)
        self._cache_ttl_seconds = max(1, int(config.SERVICE_CACHE_TTL_SECONDS))
        self._services_cache: Dict[str, Dict[str, Any]] = {}
        self._volume_cache: Dict[str, Dict[str, Any]] = {}
        self._metrics_enabled = True
        self._metrics: Dict[str, float] = {
            "tempo_search_total": 0,
            "tempo_search_duration_sum_seconds": 0.0,
            "tempo_search_errors_total": 0,
            "tempo_full_trace_fetch_total": 0,
            "tempo_count_traces_calls_total": 0,
            "tempo_metrics_queries_total": 0,
            "tempo_metrics_query_errors_total": 0,
        }

    def _observe(self, metric: str, value: float = 1.0) -> None:
        self._metrics[metric] = float(self._metrics.get(metric, 0.0) + value)

    async def _timed_get_json(
        self,
        url: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        started = time.perf_counter()
        try:
            response = await self._client.get(url, params=params, headers=headers)
            response.raise_for_status()
            return response.json()
        finally:
            self._observe("tempo_search_total")
            self._observe("tempo_search_duration_sum_seconds", time.perf_counter() - started)

    def _get_headers(self, tenant_id: str = config.DEFAULT_ORG_ID) -> Dict[str, str]:
        return {"X-Scope-OrgID": tenant_id}

    async def _query_metrics_range(
        self,
        promql: str,
        start_us: Optional[int],
        end_us: Optional[int],
        step_s: int = 300,
        tenant_id: str = config.DEFAULT_ORG_ID,
    ) -> Dict[str, Any]:
        _empty = {"status": "error", "data": {"result": []}}
        if not self._metrics_enabled:
            return _empty

        params: Dict[str, Any] = {"query": promql, "step": step_s}
        if start_us:
            params["start"] = int(start_us / 1_000_000)
        if end_us:
            params["end"] = int(end_us / 1_000_000)

        headers = self._get_headers(tenant_id)

        async def _fetch(url: str, req_params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
            try:
                resp = await self._client.get(url, params=req_params, headers=headers)
                if 400 <= resp.status_code < 500:
                    self._metrics_enabled = False
                    self._observe("tempo_metrics_query_errors_total")
                    logger.debug("Metrics endpoint %s returned %s, disabling", url, resp.status_code)
                    return None
                resp.raise_for_status()
                self._observe("tempo_metrics_queries_total")
                return resp.json()
            except httpx.HTTPError as e:
                self._observe("tempo_metrics_query_errors_total")
                logger.debug("Metrics query failed for %s: %s", url, e)
                return None

        result = await _fetch(f"{self.tempo_url}/api/metrics/query_range", params)
        if result is not None:
            return result

        mimir_params = {**params, "start": params.get("start"), "end": params.get("end")}
        result = await _fetch(f"{config.MIMIR_URL.rstrip('/')}/api/v1/query_range", mimir_params)
        return result if result is not None else _empty

    def _build_promql_selector(self, service: Optional[str]) -> List[str]:
        if not service:
            return ["{}"]
        return list(dict.fromkeys([
            f'{{resource.service.name="{service}"}}',
            f'{{service_name="{service}"}}',
            f'{{service="{service}"}}',
            f'{{service.name="{service}"}}',
        ]))

    def _build_count_promql(self, service: Optional[str], range_s: int) -> str:
        parts = [f"count_over_time({sel}[{range_s}s])" for sel in self._build_promql_selector(service)]
        return f"sum({ ' + '.join(parts) })"

    def _extract_metric_values(self, metrics_resp: Dict[str, Any]) -> List[List[Any]]:
        results = (metrics_resp.get("data") or {}).get("result") if isinstance(metrics_resp, dict) else None
        if not results:
            return []
        ts_map: Dict[int, int] = {}
        for series in results:
            for ts, v in series.get("values") or []:
                try:
                    ts_map[int(float(ts))] = ts_map.get(int(float(ts)), 0) + int(float(v))
                except (TypeError, ValueError):
                    continue
        return [[ts, str(ts_map[ts])] for ts in sorted(ts_map)]

    def _parse_attributes(self, attrs: List[Dict[str, Any]]) -> Dict[str, Any]:
        parsed: Dict[str, Any] = {}
        for attr in attrs or []:
            value = attr.get("value", {})
            for val_type in _OTLP_VALUE_TYPES:
                if val_type in value:
                    parsed[attr.get("key", "")] = value[val_type]
                    break
        return parsed

    def _parse_span(
        self,
        span_data: Dict[str, Any],
        trace_id: str,
        process_id: str,
        service_name: Optional[str],
        resource_attrs: Optional[Dict[str, Any]] = None,
    ) -> Span:
        attr_map = self._parse_attributes(span_data.get("attributes", []))
        tags = [{"key": k, "value": v} for k, v in attr_map.items()]

        if service_name and _SERVICE_NAME_KEY not in attr_map:
            attr_map[_SERVICE_NAME_KEY] = service_name
            tags.append({"key": _SERVICE_NAME_KEY, "value": service_name})

        if resource_attrs:
            for k, v in resource_attrs.items():
                attr_map.setdefault(k, v)

        start_time = int(span_data.get("startTimeUnixNano", 0)) // 1000
        end_time = int(span_data.get("endTimeUnixNano", 0)) // 1000
        parent_span_id = span_data.get("parentSpanId") or None

        return Span(
            spanID=span_data.get("spanId", ""),
            traceID=trace_id,
            parentSpanID=parent_span_id,
            operationName=span_data.get("name", ""),
            startTime=start_time,
            duration=end_time - start_time,
            tags=tags,
            serviceName=service_name,
            attributes=attr_map,
            processID=process_id,
        )

    def _parse_tempo_trace(self, trace_id: str, data: Dict[str, Any]) -> Trace:
        spans, processes = [], {}
        for batch in data.get("batches", []):
            resource_attrs = self._parse_attributes(batch.get("resource", {}).get("attributes", []))
            service_name = (
                resource_attrs.get(_SERVICE_NAME_KEY)
                or resource_attrs.get(_SERVICE_ALIAS_KEY)
                or resource_attrs.get("serviceName")
                or "unknown"
            )
            process_id = str(service_name)
            processes[process_id] = {
                "serviceName": service_name,
                "resource": batch.get("resource", {}),
                "attributes": resource_attrs,
            }
            for scope in batch.get("scopeSpans", []):
                spans.extend(
                    self._parse_span(s, trace_id, process_id, service_name, resource_attrs)
                    for s in scope.get("spans", [])
                )
        return Trace(traceID=trace_id, spans=spans, processes=processes)

    def _build_search_params(self, query: TraceQuery) -> Dict[str, Any]:
        params: Dict[str, Any] = {"limit": query.limit}
        tags = {}
        if query.service:
            tags[_SERVICE_NAME_KEY] = query.service
        if query.operation:
            tags["name"] = query.operation
        if query.tags:
            tags.update(query.tags)
        if tags:
            params["tags"] = " && ".join(f'{k}="{v}"' for k, v in tags.items())
        if query.start:
            params["start"] = int(query.start) // 1_000_000
        if query.end:
            params["end"] = int(query.end) // 1_000_000
        if query.min_duration:
            params["minDuration"] = query.min_duration
        if query.max_duration:
            params["maxDuration"] = query.max_duration
        return params

    def _build_summary_trace(self, trace_data: Dict[str, Any]) -> Optional[Trace]:
        trace_id = trace_data.get("traceID")
        if not trace_id:
            return None
        try:
            start_ns = int(trace_data["startTimeUnixNano"]) if trace_data.get("startTimeUnixNano") else None
        except (TypeError, ValueError):
            start_ns = None
        try:
            duration_ms = int(trace_data["durationMs"]) if trace_data.get("durationMs") is not None else None
        except (TypeError, ValueError):
            duration_ms = None

        return Trace(
            traceID=trace_id,
            spans=[{
                "spanID": "root",
                "traceID": trace_id,
                "parentSpanID": None,
                "operationName": trace_data.get("rootTraceName") or "",
                "startTime": int(start_ns // 1000) if start_ns else 0,
                "duration": int(duration_ms * 1000) if duration_ms is not None else 0,
                "tags": [],
                "serviceName": trace_data.get("rootServiceName") or trace_data.get("rootService") or "unknown",
                "attributes": {},
                "processID": trace_data.get("rootServiceName") or "unknown",
            }],
            processes={},
            warnings=["Trace summary only"],
        )

    @with_retry()
    @with_timeout()
    async def search_traces(
        self,
        query: TraceQuery,
        tenant_id: str = config.DEFAULT_ORG_ID,
        fetch_full_traces: bool = True,
    ) -> TraceResponse:
        params = self._build_search_params(query)
        headers = self._get_headers(tenant_id)
        try:
            data = await self._timed_get_json(f"{self.tempo_url}/api/search", params=params, headers=headers)
            raw_traces = data.get("traces", [])

            if fetch_full_traces:
                semaphore = asyncio.Semaphore(max(1, config.TEMPO_TRACE_FETCH_CONCURRENCY))

                async def _fetch_full(trace_id: str) -> Trace:
                    async with semaphore:
                        self._observe("tempo_full_trace_fetch_total")
                        return await self.get_trace(trace_id, tenant_id=tenant_id) or Trace(
                            traceID=trace_id,
                            spans=[],
                            processes={},
                            warnings=["Trace details unavailable"],
                        )

                traces = await asyncio.gather(*[
                    _fetch_full(t["traceID"]) for t in raw_traces if t.get("traceID")
                ])
            else:
                traces = [t for t in map(self._build_summary_trace, raw_traces) if t]

            return TraceResponse(data=list(traces), total=len(traces), limit=query.limit, offset=0)
        except httpx.HTTPError as e:
            self._observe("tempo_search_errors_total")
            logger.error("Error searching traces: %s", e)
            return TraceResponse(data=[], total=0, limit=query.limit, errors=[str(e)])

    @with_retry()
    @with_timeout()
    async def get_trace(self, trace_id: str, tenant_id: str = config.DEFAULT_ORG_ID) -> Optional[Trace]:
        headers = self._get_headers(tenant_id)
        try:
            response = await self._client.get(f"{self.tempo_url}/api/traces/{trace_id}", headers=headers)
            response.raise_for_status()
            if not response.content:
                logger.debug("Empty response for trace %s", trace_id)
                return None
            try:
                data = response.json()
            except json.JSONDecodeError:
                logger.debug("Non-JSON response for trace %s", trace_id)
                return None
            return self._parse_tempo_trace(trace_id, data) if "batches" in data else None
        except httpx.HTTPError as e:
            logger.error("Error fetching trace %s: %s", trace_id, e)
            return None

    @with_retry()
    @with_timeout()
    async def get_services(self, tenant_id: str = config.DEFAULT_ORG_ID) -> List[str]:
        now = time.monotonic()
        cached = self._services_cache.get(tenant_id)
        if isinstance(cached, dict) and float(cached.get("expires", 0.0)) > now:
            return list(cached.get("data", []))

        headers = self._get_headers(tenant_id)
        try:
            data = await self._timed_get_json(f"{self.tempo_url}/api/search/tags", headers=headers)
            logger.debug("Tempo /api/search/tags response: %s", data)

            tag_names: List[str] = []
            if isinstance(data, dict):
                tag_names = (
                    data.get("tagNames")
                    or (data.get("data") or {}).get("tagNames")
                    or []
                )
            elif isinstance(data, list):
                tag_names = [item.get("tagName") for item in data if isinstance(item, dict)]

            services: List[str] = []
            for tag in tag_names:
                if tag not in _SERVICE_KEYS:
                    continue
                try:
                    resp = await self._client.get(
                        f"{self.tempo_url}/api/search/tag/{tag}/values", headers=headers
                    )
                    resp.raise_for_status()
                    vd = resp.json()
                    if isinstance(vd, dict):
                        services.extend(
                            vd.get("tagValues") or vd.get("values") or vd.get("data") or []
                        )
                    elif isinstance(vd, list):
                        services.extend(vd)
                except httpx.HTTPError as e:
                    logger.warning("Failed to fetch tag values for %s: %s", tag, e)

            if not services:
                logger.debug("No services from tags, inferring from recent traces")
                try:
                    resp = await self.search_traces(TraceQuery(limit=50), tenant_id=tenant_id)
                    services = [
                        span.service_name
                        for trace in resp.data
                        for span in trace.spans
                        if span.service_name
                    ]
                except Exception as e:
                    logger.warning("Failed to infer services from traces: %s", e)

            result = sorted(set(filter(None, map(str, services))))
            self._services_cache[tenant_id] = {"expires": now + self._cache_ttl_seconds, "data": result}
            return result
        except httpx.HTTPError as e:
            logger.error("Error fetching services: %s", e)
            return []

    async def get_operations(self, service: str, tenant_id: str = config.DEFAULT_ORG_ID) -> List[str]:
        response = await self.search_traces(TraceQuery(service=service, limit=100), tenant_id=tenant_id)
        return sorted({span.operation_name for trace in response.data for span in trace.spans})

    async def get_trace_metrics(
        self,
        service: Optional[str] = None,
        start: Optional[int] = None,
        end: Optional[int] = None,
        tenant_id: str = config.DEFAULT_ORG_ID,
    ) -> Dict[str, Any]:
        query = TraceQuery(service=service, start=start, end=end, limit=min(config.MAX_QUERY_LIMIT, 1000))
        response = await self.search_traces(query, tenant_id=tenant_id, fetch_full_traces=False)
        return {
            "total_traces": response.total,
            "total_spans": None,
            "error_count": None,
            "avg_duration_us": None,
            "max_duration_us": None,
            "min_duration_us": None,
            "service": service,
        }

    async def get_trace_volume(
        self,
        service: Optional[str] = None,
        start: Optional[int] = None,
        end: Optional[int] = None,
        step: int = 300,
        tenant_id: str = config.DEFAULT_ORG_ID,
    ) -> Dict[str, Any]:
        """Return trace counts over time.

        Implementation strategy (efficient + resilient):
        - Try metrics-based query first (very cheap).
        - If metrics are unavailable, try a single aggregated count (via get_trace_metrics)
          and build an *estimated* evenly-distributed series (cheap) so the UI still
          shows meaningful data.
        - Only fall back to per-trace aggregation (expensive) when we cannot estimate.
        - Cache recent results for a short TTL to avoid repeated heavy queries.
        """
        now_us = int(time.time() * 1_000_000)
        end = end or now_us
        start = start or (end - 60 * 60 * 1_000_000)
        step = max(1, step)
        cache_key = f"{tenant_id}:{service or '__all__'}:{start}:{end}:{step}"
        cached = self._volume_cache.get(cache_key)
        if isinstance(cached, dict) and float(cached.get("expires", 0.0)) > time.monotonic():
            return cached.get("data")
        if config.TEMPO_USE_METRICS_FOR_COUNT:
            try:
                values = self._extract_metric_values(
                    await self._query_metrics_range(
                        self._build_count_promql(service, step), start, end, step, tenant_id=tenant_id
                    )
                )
                if values:
                    result = {"data": {"result": [{"metric": {}, "values": values}]}}
                    self._volume_cache[cache_key] = {"expires": time.monotonic() + self._cache_ttl_seconds, "data": result}
                    return result
            except Exception:
                logger.debug("Metrics-based volume query failed, falling back", exc_info=True)

        total_seconds = max(0, int((end - start) / 1_000_000))
        num_buckets = max(1, min(240, (total_seconds + step - 1) // step))

        try:
            metrics = await self.get_trace_metrics(service=service, start=start, end=end, tenant_id=tenant_id)
            total_traces = int(metrics.get("total_traces") or 0)
            if total_traces > 0:
                base = total_traces // num_buckets
                rem = total_traces % num_buckets
                counts = [str(base + (1 if i < rem else 0)) for i in range(num_buckets)]
                values = [
                    [int((start + i * step * 1_000_000) / 1_000_000), counts[i]]
                    for i in range(num_buckets)
                ]
                result = {"data": {"result": [{"metric": {}, "values": values}]}}
                self._volume_cache[cache_key] = {"expires": time.monotonic() + self._cache_ttl_seconds, "data": result}
                return result
        except Exception:
            logger.debug("Failed to estimate trace volume from totals", exc_info=True)

        counts = [0] * num_buckets
        values = [
            [int((start + i * step * 1_000_000) / 1_000_000), str(counts[i])]
            for i in range(num_buckets)
        ]
        result = {"data": {"result": [{"metric": {}, "values": values}]}}
        self._volume_cache[cache_key] = {"expires": time.monotonic() + self._cache_ttl_seconds, "data": result}
        return result

    async def count_traces(self, query: TraceQuery, tenant_id: str = config.DEFAULT_ORG_ID) -> int:
        if config.TEMPO_USE_METRICS_FOR_COUNT and query.start and query.end:
            try:
                duration_s = max(1, int((query.end - query.start) / 1_000_000))
                for sel in self._build_promql_selector(query.service):
                    resp = await self._query_metrics_range(
                        f"sum(count_over_time({sel}[{duration_s}s]))",
                        query.start, query.end, duration_s, tenant_id=tenant_id,
                    )
                    result = (resp.get("data") or {}).get("result") if isinstance(resp, dict) else None
                    if result:
                        vals = result[0].get("values", [])
                        if vals:
                            return int(float(vals[-1][1]))
            except Exception:
                logger.debug("Metrics-based count failed, falling back", exc_info=True)

        query_copy = TraceQuery(
            service=query.service,
            operation=query.operation,
            min_duration=query.min_duration,
            max_duration=query.max_duration,
            start=query.start,
            end=query.end,
            tags=query.tags,
            limit=min(query.limit, 1000),
        )
        response = await self.search_traces(query_copy, tenant_id=tenant_id, fetch_full_traces=False)
        self._observe("tempo_count_traces_calls_total")
        return response.total