"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");

you may not use this file except in compliance with the License.

You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""
import asyncio
import logging
import re
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import httpx

from config import config
from middleware.resilience import with_retry, with_timeout
from models.observability.loki_models import (
    LogLabelsResponse,
    LogLabelValuesResponse,
    LogQuery,
    LogResponse,
)
from services.common.http_client import create_async_client

logger = logging.getLogger(__name__)

_SERVICE_NAME_LABEL = "service.name"
_SERVICE_NAME_ALIAS = "service_name"
_LABELSET_PAIR_RE = re.compile(r'([A-Za-z0-9_.:-]+)="([^"]*)"')
_SERVICE_LABEL_EXACT_RE = re.compile(
    r'(?P<label>service_name|service\.name)\s*=\s*"(?P<value>[^"]+)"'
)


class LokiService:
    def __init__(self, loki_url: str = config.LOKI_URL):
        self.loki_url = loki_url.rstrip("/")
        self.timeout = config.DEFAULT_TIMEOUT
        self._client = create_async_client(self.timeout)
        self._cache_ttl_seconds = max(1, int(config.SERVICE_CACHE_TTL_SECONDS))
        self._labels_cache: Dict[str, Any] = {}
        self._metrics: Dict[str, float] = {
            "loki_query_total": 0,
            "loki_query_errors_total": 0,
            "loki_query_fallbacks_total": 0,
            "loki_query_duration_sum_seconds": 0.0,
        }
        logging.getLogger("httpx").setLevel(logging.WARNING)

    def _observe(self, metric: str, value: float = 1.0) -> None:
        self._metrics[metric] = float(self._metrics.get(metric, 0.0) + value)

    async def _timed_get_json(
        self, url: str, *, params: Dict[str, Any], headers: Dict[str, str]
    ) -> Dict[str, Any]:
        started = time.perf_counter()
        try:
            response = await self._client.get(url, params=params, headers=headers)
            response.raise_for_status()
            return response.json()
        finally:
            self._observe("loki_query_total")
            self._observe("loki_query_duration_sum_seconds", time.perf_counter() - started)

    async def _safe_get_json(
        self, url: str, *, params: Dict[str, Any], headers: Dict[str, str], quiet: bool = False
    ) -> Optional[Dict[str, Any]]:
        try:
            return await self._timed_get_json(url, params=params, headers=headers)
        except httpx.HTTPStatusError as e:
            status = getattr(e.response, "status_code", None)
            self._observe("loki_query_errors_total")
            if quiet or (status and 400 <= status < 500):
                logger.debug("Loki error %s for %s", status, url)
            else:
                logger.warning("Loki server error %s for %s", status, url)
            return None
        except httpx.HTTPError as e:
            self._observe("loki_query_errors_total")
            (logger.debug if quiet else logger.warning)("Loki request failed for %s: %s", url, e)
            return None

    def _get_headers(self, tenant_id: str = config.DEFAULT_ORG_ID) -> Dict[str, str]:
        return {"X-Scope-OrgID": tenant_id}

    def _normalize_service_label_query(self, query_str: str) -> str:
        if _SERVICE_NAME_LABEL not in query_str and _SERVICE_NAME_ALIAS not in query_str:
            return query_str

        def replace_in_selector(match: re.Match) -> str:
            content = re.sub(
                rf"(?<![\w.]){_SERVICE_NAME_LABEL}(?=\s*(=|=~))",
                _SERVICE_NAME_ALIAS,
                match.group(1),
            )
            return "{" + content + "}"

        return re.sub(r"\{([^}]*)\}", replace_in_selector, query_str)

    def _expand_service_label_matchers(self, query_str: str) -> str:
        return _SERVICE_LABEL_EXACT_RE.sub(
            lambda m: f'{m.group("label")}=~"{m.group("value")}.*"', query_str
        )

    def _build_service_fallback_queries(self, query_str: str) -> List[str]:
        candidates: List[str] = []
        normalized = self._normalize_service_label_query(query_str)
        if normalized != query_str:
            candidates.append(normalized)
        expanded_original = self._expand_service_label_matchers(query_str)
        if expanded_original != query_str:
            candidates.append(expanded_original)
        expanded_normalized = self._expand_service_label_matchers(normalized)
        if expanded_normalized not in (query_str, expanded_original):
            candidates.append(expanded_normalized)
        return candidates

    def _parse_labelset_value(self, label_key: str, raw_value: str) -> Optional[Dict[str, str]]:
        if not isinstance(raw_value, str) or '="' not in raw_value:
            return None
        candidate = raw_value if f'{label_key}="' in raw_value else f'{label_key}="{raw_value}'
        pairs = _LABELSET_PAIR_RE.findall(candidate)
        return dict(pairs) if pairs else None

    def _normalize_label_value(
        self, label_key: str, value: Any
    ) -> tuple[Optional[str], Optional[Dict[str, str]]]:
        if not isinstance(value, str) or '="' not in value or '",' not in value:
            return None, None
        parsed = self._parse_labelset_value(label_key, value)
        if parsed:
            return parsed.get(label_key, value), parsed
        cut_index = value.find('",')
        return (value[:cut_index], None) if cut_index > 0 else (None, None)

    def _normalize_label_dict(self, labels: Dict[str, Any]) -> Dict[str, str]:
        extra: Dict[str, str] = {}
        for key, value in labels.items():
            normalized_value, parsed = self._normalize_label_value(key, value)
            if normalized_value is not None:
                labels[key] = normalized_value
            if parsed:
                extra.update({k: v for k, v in parsed.items() if k not in labels})
        return extra

    def _normalize_stream_labels(self, data: Dict[str, Any]) -> None:
        for stream in data.get("result", []) if isinstance(data.get("result"), list) else []:
            labels = stream.get("stream")
            if isinstance(labels, dict):
                labels.update(self._normalize_label_dict(labels))

    def _normalize_label_values(self, label: str, values: List[str]) -> List[str]:
        cleaned: List[str] = []
        for value in values:
            if not isinstance(value, str):
                cleaned.append(value)
                continue
            parsed = self._parse_labelset_value(label, value)
            if parsed and label in parsed:
                cleaned.append(parsed[label])
                continue
            cut_index = value.find('",')
            cleaned.append(value[:cut_index] if cut_index > 0 else value)
        return cleaned

    def _build_query_params(self, query: LogQuery) -> Dict[str, Any]:
        params: Dict[str, Any] = {
            "query": query.query,
            "limit": query.limit,
            "direction": query.direction.value,
        }
        for key in ("start", "end", "step"):
            val = getattr(query, key, None)
            if val is not None:
                params[key] = val
        return params

    def _escape_logql_string(self, value: str) -> str:
        if not isinstance(value, str):
            return value
        return (
            value.replace("\\", "\\\\")
            .replace('"', '\\"')
            .replace("\n", "\\n")
            .replace("\r", "\\r")
        )

    def _build_label_selector(self, labels: Dict[str, str]) -> str:
        if not labels:
            return "{}"
        return "{" + ", ".join(f'{k}="{self._escape_logql_string(v)}"' for k, v in labels.items()) + "}"

    def _calculate_stats(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        try:
            result = data.get("result", [])
            if not result:
                return None
            total_entries = sum(len(s.get("values", [])) for s in result)
            total_bytes = sum(
                len(v[1]) for s in result for v in s.get("values", []) if len(v) > 1
            )
            return {
                "total_entries": total_entries,
                "total_bytes": total_bytes,
                "streams": len(result),
                "chunks": 0,
            }
        except Exception as e:
            logger.error("Error calculating stats: %s", e)
            return None

    async def _run_fallback_queries(
        self,
        endpoint: str,
        base_params: Dict[str, Any],
        headers: Dict[str, str],
        query_str: str,
    ) -> Optional[Dict[str, Any]]:
        candidates = self._build_service_fallback_queries(query_str)[
            : max(0, config.LOKI_MAX_FALLBACK_QUERIES)
        ]
        if not candidates:
            return None

        self._observe("loki_query_fallbacks_total", len(candidates))
        semaphore = asyncio.Semaphore(max(1, config.LOKI_FALLBACK_CONCURRENCY))

        async def _query(candidate: str):
            async with semaphore:
                return candidate, await self._safe_get_json(
                    endpoint, params={**base_params, "query": candidate}, headers=headers
                )

        for task in asyncio.as_completed([_query(c) for c in candidates]):
            _, payload = await task
            if isinstance(payload, dict) and payload.get("data", {}).get("result"):
                return payload
        return None

    @with_retry()
    @with_timeout()
    async def query_logs(
        self, query: LogQuery, tenant_id: str = config.DEFAULT_ORG_ID
    ) -> LogResponse:
        params = self._build_query_params(query)
        headers = self._get_headers(tenant_id)
        endpoint = f"{self.loki_url}/loki/api/v1/query_range"

        try:
            data = await self._timed_get_json(endpoint, params=params, headers=headers)
            if query.query and not data.get("data", {}).get("result"):
                fallback = await self._run_fallback_queries(endpoint, params, headers, query.query)
                if fallback:
                    data = fallback
            data_payload = data.get("data", {})
            self._normalize_stream_labels(data_payload)
            return LogResponse(
                status=data.get("status", "success"),
                data=data_payload,
                stats=self._calculate_stats(data_payload),
            )
        except httpx.HTTPError as e:
            self._observe("loki_query_errors_total")
            logger.error("Error querying logs: %s", e)
            return LogResponse(status="error", data={"result": [], "resultType": "streams"}, stats=None)

    @with_retry()
    @with_timeout()
    async def query_logs_instant(
        self,
        query_str: str,
        at_time: Optional[int] = None,
        tenant_id: str = config.DEFAULT_ORG_ID,
    ) -> LogResponse:
        params: Dict[str, Any] = {"query": query_str, "limit": 100}
        if at_time is not None:
            params["time"] = at_time

        headers = self._get_headers(tenant_id)
        endpoint = f"{self.loki_url}/loki/api/v1/query"

        try:
            data = await self._timed_get_json(endpoint, params=params, headers=headers)
            if query_str and not data.get("data", {}).get("result"):
                for candidate in self._build_service_fallback_queries(query_str):
                    payload = await self._safe_get_json(
                        endpoint, params={**params, "query": candidate}, headers=headers
                    )
                    if isinstance(payload, dict) and payload.get("data", {}).get("result"):
                        data = payload
                        break
            data_payload = data.get("data", {})
            self._normalize_stream_labels(data_payload)
            return LogResponse(status=data.get("status", "success"), data=data_payload)
        except httpx.HTTPError as e:
            logger.error("Error querying logs (instant): %s", e)
            return LogResponse(status="error", data={"result": []})

    @with_retry()
    @with_timeout()
    async def get_labels(
        self,
        start: Optional[int] = None,
        end: Optional[int] = None,
        tenant_id: str = config.DEFAULT_ORG_ID,
    ) -> LogLabelsResponse:
        now = time.monotonic()
        cache_key = f"{tenant_id}:{start}:{end}"
        cached = self._labels_cache.get(cache_key)
        if isinstance(cached, dict) and cached.get("expires", 0) > now:
            return LogLabelsResponse(status="success", data=list(cached.get("data", [])))

        params: Dict[str, Any] = {}
        if start:
            params["start"] = start
        if end:
            params["end"] = end

        try:
            payload = await self._safe_get_json(
                f"{self.loki_url}/loki/api/v1/labels",
                params=params,
                headers=self._get_headers(tenant_id),
            )
            if not payload:
                return LogLabelsResponse(status="error", data=[])
            self._labels_cache[cache_key] = {
                "expires": now + self._cache_ttl_seconds,
                "data": list(payload.get("data", [])),
            }
            return LogLabelsResponse(status=payload.get("status", "success"), data=payload.get("data", []))
        except httpx.HTTPError as e:
            logger.error("Error fetching labels: %s", e)
            return LogLabelsResponse(status="error", data=[])

    @with_retry()
    @with_timeout()
    async def get_label_values(
        self,
        label: str,
        start: Optional[int] = None,
        end: Optional[int] = None,
        query: Optional[str] = None,
        tenant_id: str = config.DEFAULT_ORG_ID,
    ) -> LogLabelValuesResponse:
        now_ns = int(datetime.now().timestamp() * 1e9)
        end = end or now_ns
        start = start or int((datetime.now() - timedelta(hours=1)).timestamp() * 1e9)

        max_hours = 24
        try:
            max_hours = int(getattr(config, "LOKI_LABEL_VALUES_MAX_RANGE_HOURS", 24))
        except (TypeError, ValueError):
            pass

        max_range_ns = int(max_hours * 3600 * 1e9)
        if end - start > max_range_ns:
            logger.debug("Label values range capped to last %s hours", max_hours)
            start = int(end - max_range_ns)

        params: Dict[str, Any] = {"start": start, "end": end}
        if query:
            params["query"] = query

        cache_key = f"label_values:{tenant_id}:{label}:{start}:{end}:{query or ''}"
        now = time.monotonic()
        cached = self._labels_cache.get(cache_key)
        if isinstance(cached, dict) and cached.get("expires", 0) > now:
            return LogLabelValuesResponse(status="success", data=list(cached.get("data", [])))

        def _cache_and_return(values: List[str]) -> LogLabelValuesResponse:
            normalized = list(dict.fromkeys(self._normalize_label_values(label, values)))
            self._labels_cache[cache_key] = {"expires": time.monotonic() + self._cache_ttl_seconds, "data": normalized}
            return LogLabelValuesResponse(status="success", data=normalized)

        payload = await self._safe_get_json(
            f"{self.loki_url}/loki/api/v1/label/{label}/values",
            params=params,
            headers=self._get_headers(tenant_id),
            quiet=True,
        )
        if isinstance(payload, dict) and payload.get("data") is not None:
            return _cache_and_return(payload.get("data", []))

        try:
            self._observe("loki_query_fallbacks_total")
            if isinstance(query, str) and query.strip().startswith("{"):
                selector = query
            else:
                selector = '{' + f'{label}=~".+"' + '}'
            log_response = await self.query_logs(
                LogQuery(query=selector, limit=1000, start=start, end=end),
                tenant_id=tenant_id,
            )
            results = log_response.data.get("result") if isinstance(log_response.data, dict) else None
            values = list(dict.fromkeys(
                stream["stream"][label]
                for stream in (results or [])
                if isinstance(stream.get("stream"), dict) and stream["stream"].get(label)
            ))
            return _cache_and_return(values)
        except Exception as e:
            logger.error("Error during label-values fallback: %s", e)
            return LogLabelValuesResponse(status="error", data=[])

    @with_retry()
    @with_timeout()
    async def aggregate_logs(
        self,
        query_str: str,
        start: Optional[int] = None,
        end: Optional[int] = None,
        step: int = 60,
        tenant_id: str = config.DEFAULT_ORG_ID,
    ) -> Dict[str, Any]:
        now = datetime.now()
        params: Dict[str, Any] = {
            "query": query_str,
            "step": step,
            "start": start or int((now - timedelta(hours=1)).timestamp() * 1e9),
            "end": end or int(now.timestamp() * 1e9),
        }
        try:
            data = await self._timed_get_json(
                f"{self.loki_url}/loki/api/v1/query_range",
                params=params,
                headers=self._get_headers(tenant_id),
            )
            return {"status": data.get("status", "success"), "data": data.get("data", {}), "query": query_str, "step": step}
        except httpx.HTTPError as e:
            self._observe("loki_query_errors_total")
            status_code = getattr(getattr(e, "response", None), "status_code", None)
            log_fn = logger.debug if status_code and 400 <= status_code < 500 else logger.error
            log_fn("Error aggregating logs (%s): %s", status_code, e)
            return {"status": "error", "error": str(e), "query": query_str}

    @with_retry()
    @with_timeout()
    async def get_log_volume(
        self,
        query_str: str,
        start: Optional[int] = None,
        end: Optional[int] = None,
        step: int = 300,
        tenant_id: str = config.DEFAULT_ORG_ID,
    ) -> Dict[str, Any]:
        candidates = list(dict.fromkeys([
            query_str,
            *self._build_service_fallback_queries(query_str),
            *(
                [
                    query_str.replace("service.name", "service_name"),
                    query_str.replace("service_name", "service"),
                    '{service=~".+"}',
                ]
                if "service_name" in query_str or "service.name" in query_str
                else []
            ),
        ]))

        semaphore = asyncio.Semaphore(max(1, config.LOKI_FALLBACK_CONCURRENCY))
        last_result: Dict[str, Any] = {"status": "success", "data": {"result": []}, "query": query_str, "step": step}

        async def _aggregate(candidate: str):
            async with semaphore:
                result = await self.aggregate_logs(
                    f"sum(count_over_time({candidate}[{step}s]))", start, end, step, tenant_id=tenant_id
                )
                return result

        for task in asyncio.as_completed(
            [_aggregate(c) for c in candidates[: max(1, config.LOKI_MAX_FALLBACK_QUERIES + 2)]]
        ):
            result = await task
            last_result = result
            if isinstance(result.get("data"), dict) and result["data"].get("result"):
                return result

        return last_result

    @with_retry()
    @with_timeout()
    async def search_logs_by_pattern(
        self,
        pattern: str,
        labels: Optional[Dict[str, str]] = None,
        start: Optional[int] = None,
        end: Optional[int] = None,
        limit: int = 100,
        tenant_id: str = config.DEFAULT_ORG_ID,
    ) -> LogResponse:
        label_selector = self._build_label_selector(labels) if labels else "{}"
        query_str = f'{label_selector} |= "{self._escape_logql_string(pattern)}"'
        return await self.query_logs(LogQuery(query=query_str, limit=limit, start=start, end=end), tenant_id=tenant_id)

    @with_retry()
    @with_timeout()
    async def filter_logs(
        self,
        labels: Dict[str, str],
        filters: Optional[List[str]] = None,
        start: Optional[int] = None,
        end: Optional[int] = None,
        limit: int = 100,
        tenant_id: str = config.DEFAULT_ORG_ID,
    ) -> LogResponse:
        query_str = self._build_label_selector(labels)
        if filters:
            query_str += "".join(f' |= "{self._escape_logql_string(f)}"' for f in filters)
        return await self.query_logs(LogQuery(query=query_str, limit=limit, start=start, end=end), tenant_id=tenant_id)