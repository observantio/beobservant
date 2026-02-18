"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");

you may not use this file except in compliance with the License.

You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0

Tempo service for trace operations.
"""
import httpx
import logging
import json
import asyncio
import time
from typing import List, Optional, Dict, Any
from models.observability.tempo_models import Trace, TraceQuery, TraceResponse, Span
from config import config
from middleware.resilience import with_retry, with_timeout
from services.common.http_client import create_async_client

logger = logging.getLogger(__name__)


SERVICE_NAME_KEY = "service.name"
SERVICE_ALIAS_KEY = "service"
SERVICE_KEYS = [SERVICE_NAME_KEY, SERVICE_ALIAS_KEY]

class TempoService:
    """Service for interacting with Tempo tracing backend."""
    
    def __init__(self, tempo_url: str = config.TEMPO_URL):
        """Initialize Tempo service.
        
        Args:
            tempo_url: Base URL for Tempo instance
        """
        self.tempo_url = tempo_url.rstrip('/')
        self.timeout = config.DEFAULT_TIMEOUT
        self._client = create_async_client(self.timeout)
        self._cache_ttl_seconds = max(1, int(config.SERVICE_CACHE_TTL_SECONDS))
        self._services_cache: Dict[str, Dict[str, Any]] = {}
        self._metrics: Dict[str, float] = {
            "tempo_search_total": 0,
            "tempo_search_duration_sum_seconds": 0.0,
            "tempo_search_errors_total": 0,
            "tempo_full_trace_fetch_total": 0,
            "tempo_count_traces_calls_total": 0,
            "tempo_metrics_queries_total": 0,
            "tempo_metrics_query_errors_total": 0,
        }
        self._metrics_enabled = True

    def _observe(self, metric: str, value: float = 1.0) -> None:
        self._metrics[metric] = float(self._metrics.get(metric, 0.0) + value)

    async def _timed_get_json(self, url: str, *, params: Optional[Dict[str, Any]] = None, headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        started = time.perf_counter()
        try:
            response = await self._client.get(url, params=params, headers=headers)
            response.raise_for_status()
            return response.json()
        finally:
            elapsed = time.perf_counter() - started
            self._observe("tempo_search_total", 1)
            self._observe("tempo_search_duration_sum_seconds", elapsed)
    
    def _get_headers(self, tenant_id: str = config.DEFAULT_ORG_ID) -> dict:
        """Get headers including tenant ID for multi-tenancy.
        
        Args:
            tenant_id: Organization/tenant ID for data isolation
            
        Returns:
            Dictionary of headers
        """
        return {"X-Scope-OrgID": tenant_id}

    async def _query_metrics_range(
        self,
        promql: str,
        start_us: Optional[int],
        end_us: Optional[int],
        step_s: int = 300,
        tenant_id: str = config.DEFAULT_ORG_ID,
    ) -> Dict[str, Any]:
        """Query Tempo's metrics endpoint (`/api/metrics/query_range`) and fallback to Mimir.

        Returns a Prometheus-style response: {"status": "success", "data": {"result": [...]}}
        On error returns a shape with an empty result so callers can fallback.
        """
        params: Dict[str, Any] = {"query": promql, "step": step_s}
        if start_us:
            params["start"] = int(start_us / 1_000_000)
        if end_us:
            params["end"] = int(end_us / 1_000_000)

        headers = self._get_headers(tenant_id)

        if not getattr(self, "_metrics_enabled", True):
            return {"status": "error", "data": {"result": []}}

        try:
            resp = await self._client.get(f"{self.tempo_url}/api/metrics/query_range", params=params, headers=headers)
            if 400 <= resp.status_code < 500:
                self._metrics_enabled = False
                self._observe("tempo_metrics_query_errors_total", 1)
                logger.debug("Tempo metrics endpoint returned %s, disabling metrics usage", resp.status_code)
                return {"status": "error", "data": {"result": []}}
            resp.raise_for_status()
            self._observe("tempo_metrics_queries_total", 1)
            return resp.json()
        except httpx.HTTPError as e:
            self._observe("tempo_metrics_query_errors_total", 1)
            logger.debug("Tempo metrics query failed, trying Mimir: %s", e)

        try:
            resp = await self._client.get(f"{config.MIMIR_URL.rstrip('/')}/api/v1/query_range", params={"query": promql, "start": params.get("start"), "end": params.get("end"), "step": step_s}, headers=headers)
            if 400 <= resp.status_code < 500:
                self._metrics_enabled = False
                self._observe("tempo_metrics_query_errors_total", 1)
                logger.debug("Mimir metrics endpoint returned %s, disabling metrics usage", resp.status_code)
                return {"status": "error", "data": {"result": []}}
            resp.raise_for_status()
            self._observe("tempo_metrics_queries_total", 1)
            return resp.json()
        except httpx.HTTPError as e:
            self._observe("tempo_metrics_query_errors_total", 1)
            logger.debug("Mimir metrics query failed for promql=%s: %s", promql, e)
            return {"status": "error", "data": {"result": []}}

    def _build_count_promql(self, service: Optional[str], range_s: int) -> str:
        """Build a single PromQL expression that counts traces over `range_s` seconds.

        Uses all candidate selectors and sums their `count_over_time()` results so
        we can request a single metrics response instead of multiple queries.
        """
        selectors = self._build_promql_selector(service)
        parts = [f"count_over_time({sel}[{range_s}s])" for sel in selectors]
        return f"sum({ ' + '.join(parts) })"

    def _extract_metric_values(self, metrics_resp: Dict[str, Any]) -> List[List[Any]]:
        """Normalize a Prometheus-style `query_range` response into a values list.

        Returns a list of [timestamp_seconds, count_str] aggregated across all
        returned series (summing values for matching timestamps).
        """
        if not isinstance(metrics_resp, dict):
            return []
        data = metrics_resp.get("data") or {}
        results = data.get("result") if isinstance(data, dict) else None
        if not results:
            return []

        ts_map: Dict[int, int] = {}
        for series in results:
            vals = series.get("values") or []
            for ts, v in vals:
                try:
                    tsi = int(float(ts))
                    vi = int(float(v))
                except Exception:
                    continue
                ts_map[tsi] = ts_map.get(tsi, 0) + vi

        out = [[ts, str(ts_map[ts])] for ts in sorted(ts_map.keys())]
        return out

    def _build_promql_selector(self, service: Optional[str]) -> List[str]:
        """Return ordered candidate label selectors for a service.

        We try several common label names so the query works across Tempo/ingest
        configurations. Callers should try each selector and accept the first
        that returns non-empty data.
        """
        if not service:
            return ["{}"]

        candidates = [
            f'{{resource.service.name="{service}"}}',
            f'{{service_name="{service}"}}',
            f'{{service="{service}"}}',
            f'{{service.name="{service}"}}',
        ]
        seen = set()
        out: List[str] = []
        for c in candidates:
            if c not in seen:
                seen.add(c)
                out.append(c)
        return out

    @with_retry()
    @with_timeout()
    async def search_traces(
        self,
        query: TraceQuery,
        tenant_id: str = config.DEFAULT_ORG_ID,
        fetch_full_traces: bool = True
    ) -> TraceResponse:
        """Search for traces matching query parameters.
        
        When fetch_full_traces=True (default), fetches complete span data for each trace.
        When fetch_full_traces=False, returns only trace summaries (traceID, duration, etc.)
        which is more efficient for list views. Full trace details can be retrieved later
        via get_trace() when the user clicks on a specific trace.
        
        Args:
            query: TraceQuery with search parameters
            tenant_id: Organization/tenant ID for data isolation
            fetch_full_traces: Whether to fetch full span data or just summaries
            
        Returns:
            TraceResponse with matching traces
        """
        params = self._build_search_params(query)
        headers = self._get_headers(tenant_id)
        try:
            data = await self._timed_get_json(
                f"{self.tempo_url}/api/search",
                params=params,
                headers=headers,
            )
            
            traces = []
            if "traces" in data:
                trace_ids = [trace_data.get("traceID") for trace_data in data["traces"] if trace_data.get("traceID")]

                if fetch_full_traces and trace_ids:
                    semaphore = asyncio.Semaphore(max(1, config.TEMPO_TRACE_FETCH_CONCURRENCY))

                    async def _fetch_full(trace_id: str):
                        async with semaphore:
                            self._observe("tempo_full_trace_fetch_total", 1)
                            full_trace = await self.get_trace(trace_id, tenant_id=tenant_id)
                            if full_trace:
                                return full_trace
                            return Trace(
                                traceID=trace_id,
                                spans=[],
                                processes={},
                                warnings=["Trace details unavailable"],
                            )

                    traces = await asyncio.gather(*[_fetch_full(trace_id) for trace_id in trace_ids])
                else:
                    traces = []
                    for trace_data in data.get("traces", []):
                        trace_id = trace_data.get("traceID")
                        if not trace_id:
                            continue

                        start_ns = None
                        try:
                            if trace_data.get("startTimeUnixNano"):
                                start_ns = int(trace_data.get("startTimeUnixNano"))
                        except Exception:
                            start_ns = None

                        duration_ms = None
                        try:
                            if trace_data.get("durationMs") is not None:
                                duration_ms = int(trace_data.get("durationMs"))
                        except Exception:
                            duration_ms = None

                        root_service = trace_data.get("rootServiceName") or trace_data.get("rootService") or "unknown"
                        operation_name = trace_data.get("rootTraceName") or ""

                        start_us = int(start_ns // 1000) if start_ns else 0
                        duration_us = int(duration_ms * 1000) if duration_ms is not None else 0

                        synthetic_span = {
                            "spanID": "root",
                            "traceID": trace_id,
                            "parentSpanID": None,
                            "operationName": operation_name,
                            "startTime": start_us,
                            "duration": duration_us,
                            "tags": [],
                            "serviceName": root_service,
                            "attributes": {},
                            "processID": root_service,
                        }

                        traces.append(
                            Trace(
                                traceID=trace_id,
                                spans=[synthetic_span],
                                processes={},
                                warnings=["Trace summary only"],
                            )
                        )
            
            return TraceResponse(
                data=traces,
                total=len(traces),
                limit=query.limit,
                offset=0
            )
            
        except httpx.HTTPError as e:
            self._observe("tempo_search_errors_total", 1)
            logger.error("Error searching traces: %s", e)
            return TraceResponse(
                data=[],
                total=0,
                limit=query.limit,
                errors=[str(e)]
            )
    
    @with_retry()
    @with_timeout()
    async def get_trace(self, trace_id: str, tenant_id: str = config.DEFAULT_ORG_ID) -> Optional[Trace]:
        """Get a specific trace by ID.
        
        Args:
            trace_id: Trace identifier
            tenant_id: Organization/tenant ID for data isolation
            
        Returns:
            Trace object or None if not found
        """
        headers = self._get_headers(tenant_id)
        try:
            response = await self._client.get(f"{self.tempo_url}/api/traces/{trace_id}", headers=headers)
            response.raise_for_status()
            if not response.content:
                logger.debug("Tempo returned empty response for trace %s", trace_id)
                return None

            try:
                data = response.json()
            except json.JSONDecodeError:
                logger.debug("Tempo returned non-JSON response for trace %s", trace_id)
                return None
            
            
            if "batches" in data:
                trace = self._parse_tempo_trace(trace_id, data)
                return trace
            
            return None
            
        except httpx.HTTPError as e:
            logger.error("Error fetching trace %s: %s", trace_id, e)
            return None
    
    @with_retry()
    @with_timeout()
    async def get_services(self, tenant_id: str = config.DEFAULT_ORG_ID) -> List[str]:
        """Get list of services that have traces.
        
        Args:
            tenant_id: Organization/tenant ID for data isolation
        
        Returns:
            List of service names
        """
        headers = self._get_headers(tenant_id)
        now = time.monotonic()
        cached = self._services_cache.get(tenant_id)
        if isinstance(cached, dict) and float(cached.get("expires", 0.0)) > now:
            return list(cached.get("data", []))

        try:
            data = await self._timed_get_json(f"{self.tempo_url}/api/search/tags", headers=headers)
            logger.debug("Tempo /api/search/tags response: %s", data)

            services = []

            tag_names = []
            if isinstance(data, dict):
                if "tagNames" in data and isinstance(data["tagNames"], list):
                    tag_names = data["tagNames"]
                elif "data" in data and isinstance(data["data"], dict) and "tagNames" in data["data"]:
                    tag_names = data["data"]["tagNames"]
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and "tagName" in item:
                        tag_names.append(item.get("tagName"))

            for tag in tag_names:
                if tag in SERVICE_KEYS:
                    try:
                        values_resp = await self._client.get(
                            f"{self.tempo_url}/api/search/tag/{tag}/values",
                            headers=headers
                        )
                        values_resp.raise_for_status()
                        values_data = values_resp.json()
                        logger.debug("Tempo /api/search/tag/%s/values response: %s", tag, values_data)

                        if isinstance(values_data, dict):
                            if "tagValues" in values_data and isinstance(values_data["tagValues"], list):
                                services.extend(values_data["tagValues"])
                            elif "values" in values_data and isinstance(values_data["values"], list):
                                services.extend(values_data["values"])
                            elif "data" in values_data and isinstance(values_data["data"], list):
                                services.extend(values_data["data"])
                        elif isinstance(values_data, list):
                            services.extend(values_data)
                    except httpx.HTTPError as ve:
                        logger.warning("Failed to fetch tag values for %s: %s", tag, ve)

            if not services:
                logger.debug("No services found from tag endpoints, attempting to infer from recent traces")
                try:
                    search_resp = await self.search_traces(TraceQuery(limit=50), tenant_id=tenant_id)
                    for trace in search_resp.data:
                        for span in trace.spans:
                            if span.service_name:
                                services.append(span.service_name)
                except Exception as ie:
                    logger.warning("Failed to infer services from traces: %s", ie)

            normalized = [s for s in map(str, services) if s]
            result = sorted(set(normalized))
            self._services_cache[tenant_id] = {
                "expires": now + self._cache_ttl_seconds,
                "data": list(result),
            }
            return result
            
        except httpx.HTTPError as e:
            logger.error("Error fetching services: %s", e)
            return []
    
    async def get_operations(self, service: str, tenant_id: str = config.DEFAULT_ORG_ID) -> List[str]:
        """Get operations for a specific service.
        
        Args:
            service: Service name
            
        Returns:
            List of operation names
        """
        query = TraceQuery(service=service, limit=100)
        response = await self.search_traces(query, tenant_id=tenant_id)
        
        operations = set()
        for trace in response.data:
            for span in trace.spans:
                operations.add(span.operation_name)
        
        return sorted(operations)
    
    async def get_trace_metrics(
        self,
        service: Optional[str] = None,
        start: Optional[int] = None,
        end: Optional[int] = None,
        tenant_id: str = config.DEFAULT_ORG_ID
    ) -> Dict[str, Any]:
        """Get trace metrics/statistics.
        
        Args:
            service: Optional service name filter
            start: Start time in microseconds
            end: End time in microseconds
            
        Returns:
            Dictionary with trace metrics
        """
        safe_limit = min(config.MAX_QUERY_LIMIT, 1000)
        query = TraceQuery(service=service, start=start, end=end, limit=safe_limit)
        response = await self.search_traces(query, tenant_id=tenant_id, fetch_full_traces=False)

        return {
            "total_traces": response.total,
            "total_spans": None,
            "error_count": None,
            "avg_duration_us": None,
            "max_duration_us": None,
            "min_duration_us": None,
            "service": service
        }

    async def get_trace_volume(
        self,
        service: Optional[str] = None,
        start: Optional[int] = None,
        end: Optional[int] = None,
        step: int = 300,
        tenant_id: str = config.DEFAULT_ORG_ID
    ) -> Dict[str, Any]:
        """Return trace counts over time as a Prometheus-style matrix response.

        Time range is in microseconds (matches other Tempo endpoints).
        Buckets the range into `step`-second intervals and counts traces in
        each bucket using `count_traces`. Returns shape compatible with the
        frontend `getVolumeValues` helper (i.e. data.result[0].values).
        """
        import time

        now_us = int(time.time() * 1_000_000)
        if end is None:
            end = now_us
        if start is None:
            start = end - (60 * 60 * 1000000)

        if step <= 0:
            step = 300

        if config.TEMPO_USE_METRICS_FOR_COUNT:
            try:
                # Request a single metrics matrix for the requested step range.
                promql = self._build_count_promql(service, step)
                metrics_resp = await self._query_metrics_range(promql, start, end, step, tenant_id=tenant_id)
                values = self._extract_metric_values(metrics_resp)
                if values:
                    return {"data": {"result": [{"metric": {}, "values": values}]}}
            except Exception:
                logger.debug("Metrics-based volume query failed — falling back to single-search aggregation", exc_info=True)

        # Fallback: perform a single `/api/search` for the entire range and
        # aggregate into buckets server-side. This avoids issuing per-bucket
        # `/api/search` calls which have been observed to flood Tempo.
        max_buckets = 240
        total_seconds = max(0, int((end - start) / 1_000_000))
        num_buckets = int(max(1, min(max_buckets, (total_seconds + step - 1) // step)))

        # Prepare zeroed counts
        counts = [0 for _ in range(num_buckets)]

        try:
            safe_limit = min(config.MAX_QUERY_LIMIT, max(1000, config.MAX_QUERY_LIMIT))
            q = TraceQuery(service=service, start=start, end=end, limit=safe_limit)
            resp = await self.search_traces(q, tenant_id=tenant_id, fetch_full_traces=False)

            for trace in resp.data:
                # Use the first (synthetic) span's startTime as the trace start (microseconds)
                if not trace.spans:
                    continue
                trace_start_us = 0
                try:
                    # traces from search_traces set synthetic span dicts; handle both dict and object
                    s0 = trace.spans[0]
                    if isinstance(s0, dict):
                        trace_start_us = int(s0.get("startTime", 0))
                    else:
                        trace_start_us = int(getattr(s0, "startTime", 0))
                except Exception:
                    trace_start_us = 0

                if trace_start_us < start or trace_start_us >= end:
                    continue

                idx = int((trace_start_us - start) // (step * 1_000_000))
                if 0 <= idx < num_buckets:
                    counts[idx] += 1
        except Exception as e:
            logger.debug("Trace search aggregation failed: %s", e)

        values = []
        for i in range(num_buckets):
            bucket_start = int(start + i * step * 1_000_000)
            ts_seconds = int(bucket_start / 1_000_000)
            values.append([ts_seconds, str(counts[i])])

        return {"data": {"result": [{"metric": {}, "values": values}]}}

    async def count_traces(
        self,
        query: TraceQuery,
        tenant_id: str = config.DEFAULT_ORG_ID
    ) -> int:
        """Count traces without fetching full trace details.

        Prefer metrics-based counting when enabled and a time range is provided
        (this avoids issuing `/api/search` per-bucket). Falls back to existing
        search-based counting when metrics are unavailable or disabled.
        """
        if config.TEMPO_USE_METRICS_FOR_COUNT and query.start and query.end:
            try:
                duration_s = max(1, int((query.end - query.start) / 1_000_000))
                selectors = self._build_promql_selector(query.service)
                for sel in selectors:
                    promql = f"sum(count_over_time({sel}[{duration_s}s]))"
                    metrics_resp = await self._query_metrics_range(promql, query.start, query.end, duration_s, tenant_id=tenant_id)
                    data = metrics_resp.get("data", {}) if isinstance(metrics_resp, dict) else {}
                    result = data.get("result") if isinstance(data, dict) else None
                    if result:
                        vals = result[0].get("values", [])
                        if vals:
                            return int(float(vals[-1][1]))
            except Exception:
                logger.debug("metrics-based count failed, falling back to search_traces", exc_info=True)

        safe_limit = min(query.limit, 1000)
        query_copy = TraceQuery(
            service=query.service,
            operation=query.operation,
            min_duration=query.min_duration,
            max_duration=query.max_duration,
            start=query.start,
            end=query.end,
            tags=query.tags,
            limit=safe_limit
        )
        response = await self.search_traces(query_copy, tenant_id=tenant_id, fetch_full_traces=False)
        self._observe("tempo_count_traces_calls_total", 1)
        return response.total
    
    def _build_search_params(self, query: TraceQuery) -> Dict[str, Any]:
        """Build search query parameters for Tempo API.
        
        Args:
            query: TraceQuery object
            
        Returns:
            Dictionary of query parameters
        """
        params = {
            "limit": query.limit
        }
        
        tags = {}
        if query.service:
            tags[SERVICE_NAME_KEY] = query.service
        if query.operation:
            tags["name"] = query.operation
        if query.tags:
            tags.update(query.tags)
        
        if tags:
            tag_queries = [f'{k}="{v}"' for k, v in tags.items()]
            params["tags"] = " && ".join(tag_queries)
        
        if query.start:
            params["start"] = int(int(query.start) / 1_000_000)
        if query.end:
            params["end"] = int(int(query.end) / 1_000_000)
    
        if query.min_duration:
            params["minDuration"] = query.min_duration
        if query.max_duration:
            params["maxDuration"] = query.max_duration
        
        return params

    def _parse_tempo_trace(self, trace_id: str, data: Dict[str, Any]) -> Trace:
        """Parse Tempo trace format into our Trace model.
        
        Args:
            trace_id: Trace ID
            data: Raw trace data from Tempo
            
        Returns:
            Parsed Trace object
        """
        spans = []
        processes = {}

        for batch in data.get("batches", []):
            resource_attrs = self._parse_attributes(batch.get("resource", {}).get("attributes", []))
            service_name = (
                resource_attrs.get(SERVICE_NAME_KEY)
                or resource_attrs.get(SERVICE_ALIAS_KEY)
                or resource_attrs.get("serviceName")
                or "unknown"
            )
            process_id = str(service_name)
            processes[process_id] = {
                "serviceName": service_name,
                "resource": batch.get("resource", {}),
                "attributes": resource_attrs,
            }

            for span_data in batch.get("scopeSpans", []):
                for span in span_data.get("spans", []):
                    span_obj = self._parse_span(span, trace_id, process_id, service_name, resource_attrs)
                    spans.append(span_obj)
        
        return Trace(
            traceID=trace_id,
            spans=spans,
            processes=processes
        )
    
    def _parse_span(
        self,
        span_data: Dict[str, Any],
        trace_id: str,
        process_id: str,
        service_name: Optional[str],
        resource_attrs: Optional[Dict[str, Any]] = None
    ) -> Span:
        """Parse individual span data.
        
        Args:
            span_data: Raw span data
            trace_id: Trace ID
            process_id: Process ID
            
        Returns:
            Parsed Span object
        """
        tags = []
        attr_map = self._parse_attributes(span_data.get("attributes", []))
        for key, value in attr_map.items():
            tags.append({"key": key, "value": value})

        
        if service_name and SERVICE_NAME_KEY not in attr_map:
            attr_map[SERVICE_NAME_KEY] = service_name
            tags.append({"key": SERVICE_NAME_KEY, "value": service_name})

        if resource_attrs:
            for rk, rv in resource_attrs.items():
                attr_map.setdefault(rk, rv)
        
        start_time = int(span_data.get("startTimeUnixNano", 0)) // 1000 
        end_time = int(span_data.get("endTimeUnixNano", 0)) // 1000
        duration = end_time - start_time
        
        parent_span_id = None
        if "parentSpanId" in span_data and span_data["parentSpanId"]:
            parent_span_id = span_data["parentSpanId"]
        
        return Span(
            spanID=span_data.get("spanId", ""),
            traceID=trace_id,
            parentSpanID=parent_span_id,
            operationName=span_data.get("name", ""),
            startTime=start_time,
            duration=duration,
            tags=tags,
            serviceName=service_name,
            attributes=attr_map,
            processID=process_id
        )

    def _parse_attributes(self, attrs: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Parse OTLP attributes list into a key-value map."""
        parsed: Dict[str, Any] = {}
        for attr in attrs or []:
            key = attr.get("key", "")
            value = attr.get("value", {})
            for val_type in ["stringValue", "intValue", "boolValue", "doubleValue"]:
                if val_type in value:
                    parsed[key] = value[val_type]
                    break
        return parsed
