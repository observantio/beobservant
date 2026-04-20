"""
Proxy client for forwarding Resolver API calls through Watchdog.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the
License. You may obtain a copy of the License at
http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import dataclass
from typing import Dict, Optional, TypeAlias
import httpx
from fastapi import HTTPException, status
from config import config
from models.access.auth_models import TokenData
from custom_types.json import JSONDict, JSONValue, is_json_value
from services.common.ttl_cache import TTLCache
from services.proxy.base_proxy import BaseProxyService
from middleware.resilience import with_retry, with_timeout

QueryParamValue: TypeAlias = str | int | float | bool
QueryParams: TypeAlias = dict[str, QueryParamValue]


@dataclass
class ResolverProxyJsonRequest:
    method: str
    upstream_path: str
    current_user: TokenData
    tenant_id: str
    payload: Optional[JSONDict] = None
    params: Optional[QueryParams] = None
    audit_action: str = "resolver.proxy"
    correlation_id: Optional[str] = None
    cache_ttl_seconds: Optional[int] = None


@dataclass(frozen=True)
class ResolverUpstreamRequestContext:
    method_upper: str
    target: str
    headers: dict[str, str]
    params: QueryParams | None
    payload: JSONValue | None
    correlation_id: str
    current_user: TokenData
    audit_action: str
    upstream_path: str


@dataclass(frozen=True)
class ResolverReadCacheContext:
    method_upper: str
    upstream_path: str
    tenant_id: str
    params: QueryParams | None
    payload: JSONDict | None
    effective_cache_ttl: int


@dataclass(frozen=True)
class ResolverFinalizeContext:
    corr: str
    cache_key: str | None
    effective_cache_ttl: int
    owner: bool
    inflight_future: asyncio.Future[JSONValue] | None


class ResolverProxyService(BaseProxyService):
    _resource_type = "resolver_proxy"

    def __init__(self) -> None:
        super().__init__(
            base_url=config.RESOLVER_URL,
            timeout=float(config.RESOLVER_TIMEOUT_SECONDS),
            tls_enabled=bool(config.RESOLVER_TLS_ENABLED),
            ca_cert_path=config.RESOLVER_CA_CERT_PATH,
        )
        self._cache_ttl_seconds = max(0, int(getattr(config, "RESOLVER_PROXY_CACHE_TTL_SECONDS", 15)))
        self._read_cache = TTLCache()
        self._read_inflight: Dict[str, asyncio.Future[JSONValue]] = {}
        self._read_inflight_lock = asyncio.Lock()

    @staticmethod
    def _is_volatile_read(upstream_path: str) -> bool:
        return upstream_path.startswith("/api/v1/jobs") or upstream_path.startswith("/api/v1/reports")

    def _resolve_cache_ttl(
        self,
        *,
        method: str,
        upstream_path: str,
        cache_ttl_seconds: Optional[int],
    ) -> int:
        configured_cache_ttl = self._cache_ttl_seconds if cache_ttl_seconds is None else max(0, int(cache_ttl_seconds))
        if method.upper() == "GET" and self._is_volatile_read(upstream_path):
            return 0
        return configured_cache_ttl

    @staticmethod
    def _cache_key(
        *,
        method: str,
        upstream_path: str,
        tenant_id: str,
        params: Optional[QueryParams],
        payload: Optional[JSONDict],
    ) -> str:
        return json.dumps(
            {
                "m": method.upper(),
                "p": upstream_path,
                "t": tenant_id,
                "q": params or {},
                "b": payload or {},
            },
            sort_keys=True,
            separators=(",", ":"),
        )

    def _sign_context_token(self, *, current_user: TokenData, tenant_id: str) -> str:
        key = config.get_secret("RESOLVER_CONTEXT_SIGNING_KEY")
        if not key:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Missing Resolver signing key",
            )
        claims = self._build_base_jwt_claims(
            current_user=current_user,
            tenant_id=tenant_id,
            issuer=config.RESOLVER_CONTEXT_ISSUER,
            audience=config.RESOLVER_CONTEXT_AUDIENCE,
            ttl_seconds=int(config.RESOLVER_CONTEXT_TTL_SECONDS),
        )
        return self._encode_jwt(
            claims,
            key,
            str(config.RESOLVER_CONTEXT_ALGORITHM or "HS256").strip(),
        )

    def _resolve_inflight_error(
        self,
        owner: bool,
        future: Optional[asyncio.Future[JSONValue]],
        exc: HTTPException,
    ) -> None:
        if owner and future is not None and not future.done():
            future.set_exception(exc)
            _ = future.exception()

    async def _prepare_read_cache(
        self,
        context: ResolverReadCacheContext,
    ) -> tuple[Optional[str], Optional[asyncio.Future[JSONValue]], bool, Optional[JSONValue]]:
        cache_key: Optional[str] = None
        inflight_future: Optional[asyncio.Future[JSONValue]] = None
        owner = False
        cached: Optional[JSONValue] = None
        if context.method_upper == "GET" and context.effective_cache_ttl > 0:
            cache_key = self._cache_key(
                method=context.method_upper,
                upstream_path=context.upstream_path,
                tenant_id=context.tenant_id,
                params=context.params,
                payload=context.payload,
            )
            cached = await self._read_cache.get(cache_key)
            if cached is None:
                async with self._read_inflight_lock:
                    cached = await self._read_cache.get(cache_key)
                    if cached is None:
                        inflight_future = self._read_inflight.get(cache_key)
                        if inflight_future is None:
                            inflight_future = asyncio.get_running_loop().create_future()
                            self._read_inflight[cache_key] = inflight_future
                            owner = True
        return cache_key, inflight_future, owner, cached

    async def _finalize_success_response(
        self,
        response: httpx.Response,
        context: ResolverFinalizeContext,
    ) -> JSONValue:
        try:
            result = response.json()
            if not is_json_value(result):
                raise ValueError("Resolver returned non-JSON data")
            if context.cache_key:
                await self._read_cache.set(context.cache_key, result, context.effective_cache_ttl)
            if context.owner and context.inflight_future is not None and not context.inflight_future.done():
                context.inflight_future.set_result(result)
            return result
        except ValueError as exc:
            err = HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Resolver returned invalid JSON",
                headers={"X-Request-ID": context.corr},
            )
            self._resolve_inflight_error(context.owner, context.inflight_future, err)
            raise err from exc

    async def _request_upstream(
        self,
        context: ResolverUpstreamRequestContext,
        owner: bool,
        inflight_future: Optional[asyncio.Future[JSONValue]],
    ) -> httpx.Response:
        started = time.time()
        try:
            response = await self._client.request(
                method=context.method_upper,
                url=context.target,
                headers=context.headers,
                params=context.params or None,
                json=context.payload if context.payload is not None else None,
            )
        except httpx.TimeoutException as exc:
            err = HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="Resolver request timed out",
                headers={"X-Request-ID": context.correlation_id},
            )
            self._resolve_inflight_error(owner, inflight_future, err)
            await self.write_audit_async(
                current_user=context.current_user,
                action=f"{context.audit_action}.timeout",
                resource_id=context.upstream_path,
                details={
                    "correlation_id": context.correlation_id,
                    "timeout": self.timeout,
                    "method": context.method_upper,
                },
            )
            raise err from exc
        except Exception as exc:
            err = HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Failed to contact Resolver",
                headers={"X-Request-ID": context.correlation_id},
            )
            self._resolve_inflight_error(owner, inflight_future, err)
            await self.write_audit_async(
                current_user=context.current_user,
                action=f"{context.audit_action}.error",
                resource_id=context.upstream_path,
                details={
                    "correlation_id": context.correlation_id,
                    "error": type(exc).__name__,
                    "method": context.method_upper,
                },
            )
            raise err from exc

        elapsed_ms = int((time.time() - started) * 1000)
        await self.write_audit_async(
            current_user=context.current_user,
            action=f"{context.audit_action}.complete",
            resource_id=context.upstream_path,
            details={
                "correlation_id": context.correlation_id,
                "status_code": response.status_code,
                "latency_ms": elapsed_ms,
                "method": context.method_upper,
            },
        )
        return response

    @with_retry()
    @with_timeout()
    async def request_json(self, req: ResolverProxyJsonRequest) -> JSONValue:
        method = req.method
        upstream_path = req.upstream_path
        current_user = req.current_user
        tenant_id = req.tenant_id
        payload = req.payload
        params = req.params
        audit_action = req.audit_action
        correlation_id = req.correlation_id
        cache_ttl_seconds = req.cache_ttl_seconds

        service_token = config.get_secret("RESOLVER_SERVICE_TOKEN")
        if not service_token:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Resolver service token not configured",
            )

        method_upper = method.upper()
        effective_cache_ttl = self._resolve_cache_ttl(
            method=method_upper,
            upstream_path=upstream_path,
            cache_ttl_seconds=cache_ttl_seconds,
        )
        cache_key, inflight_future, owner, cached = await self._prepare_read_cache(
            ResolverReadCacheContext(
                method_upper=method_upper,
                upstream_path=upstream_path,
                tenant_id=tenant_id,
                params=params,
                payload=payload,
                effective_cache_ttl=effective_cache_ttl,
            ),
        )
        if cached is not None:
            return cached
        if inflight_future is not None and not owner:
            return await inflight_future

        context_token = self._sign_context_token(current_user=current_user, tenant_id=tenant_id)
        corr = correlation_id or str(uuid.uuid4())
        target = f"{self.base_url}{upstream_path}"
        headers = {
            "X-Service-Token": service_token,
            "Authorization": f"Bearer {context_token}",
            "X-Correlation-ID": corr,
            "Content-Type": "application/json",
        }
        response = await self._request_upstream(
            ResolverUpstreamRequestContext(
                method_upper=method_upper,
                target=target,
                headers=headers,
                params=params,
                payload=payload,
                correlation_id=corr,
                current_user=current_user,
                audit_action=audit_action,
                upstream_path=upstream_path,
            ),
            owner=owner,
            inflight_future=inflight_future,
        )

        if response.status_code >= 400:
            detail = "Resolver upstream error" if response.status_code >= 500 else self._extract_error_detail(response)
            err = HTTPException(
                status_code=response.status_code,
                detail=detail,
                headers={"X-Request-ID": corr},
            )
            self._resolve_inflight_error(owner, inflight_future, err)
            raise err

        try:
            return await self._finalize_success_response(
                response=response,
                context=ResolverFinalizeContext(
                    corr=corr,
                    cache_key=cache_key,
                    effective_cache_ttl=effective_cache_ttl,
                    owner=owner,
                    inflight_future=inflight_future,
                ),
            )
        finally:
            if owner and cache_key:
                async with self._read_inflight_lock:
                    self._read_inflight.pop(cache_key, None)


resolver_proxy_service = ResolverProxyService()
