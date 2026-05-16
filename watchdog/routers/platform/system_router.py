"""
Router for system-level operations such as retrieving system metrics, health status, and performing maintenance tasks.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the
License. You may obtain a copy of the License at
http://www.apache.org/licenses/LICENSE-2.0
"""

import asyncio
import time

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.concurrency import run_in_threadpool

from custom_types.json import JSONDict
from middleware.dependencies import auth_service, require_permission_with_scope
from middleware.error_handlers import RouteErrorHandlerOptions, handle_route_errors
from models.access.auth_models import Permission, TokenData
from models.access.quota_models import QuotasResponse
from services.quota_service import quota_service
from services.system_service import SystemService

router = APIRouter(prefix="/api/system", tags=["system"])
system_service = SystemService()
GITHUB_OJO_LATEST_RELEASE_URL = "https://api.github.com/repos/observantio/ojo/releases/latest"
GITHUB_OJO_RELEASES_URL = "https://api.github.com/repos/observantio/ojo/releases"
OJO_RELEASE_CACHE_TTL_SECONDS = 3600
OJO_RELEASE_CACHE_PAYLOAD: JSONDict | None = None
OJO_RELEASE_CACHE_EXPIRES_AT: float = 0.0
ojo_release_cache_lock = asyncio.Lock()


@router.get("/metrics", response_model=JSONDict)
@handle_route_errors(RouteErrorHandlerOptions(internal_detail="Failed to retrieve system metrics"))
async def get_system_metrics(
    _current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_AGENTS, "system")),
) -> JSONDict:
    return system_service.get_all_metrics()


@router.get("/quotas", response_model=QuotasResponse)
@handle_route_errors(RouteErrorHandlerOptions(internal_detail="Failed to retrieve system quotas"))
async def get_system_quotas(
    org_id: str | None = Query(default=None, alias="orgId"),
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_AGENTS, "system")),
) -> QuotasResponse:
    requested_org = org_id if isinstance(org_id, str) else None
    selected_org = str(requested_org or current_user.org_id or "").strip()
    if not selected_org:
        selected_org = str(current_user.tenant_id)

    if requested_org:
        visible_keys = await run_in_threadpool(auth_service.list_api_keys, current_user.user_id, False)
        allowed_org_ids = {
            str(getattr(k, "key", "") or "")
            for k in visible_keys
            if (not bool(getattr(k, "is_shared", False)) or bool(getattr(k, "can_use", False)))
        }
        if selected_org not in allowed_org_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized for requested API key scope",
            )

    return await quota_service.get_quotas(current_user, tenant_scope=selected_org)


@router.get("/ojo/releases", response_model=JSONDict)
@handle_route_errors(RouteErrorHandlerOptions(internal_detail="Failed to retrieve Ojo release metadata"))
async def get_ojo_releases(
    _current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_AGENTS, "system")),
) -> JSONDict:
    def _fallback_payload(*, cached_payload: JSONDict | None = None) -> JSONDict:
        payload: JSONDict = {
            "latest": {},
            "releases": [],
            "latest_ok": False,
            "releases_ok": False,
        }
        if cached_payload:
            payload.update(cached_payload)
            payload["cache_stale"] = True
        return payload

    now = time.monotonic()
    if OJO_RELEASE_CACHE_PAYLOAD is not None and now < OJO_RELEASE_CACHE_EXPIRES_AT:
        return OJO_RELEASE_CACHE_PAYLOAD

    async with ojo_release_cache_lock:
        now = time.monotonic()
        if OJO_RELEASE_CACHE_PAYLOAD is not None and now < OJO_RELEASE_CACHE_EXPIRES_AT:
            return OJO_RELEASE_CACHE_PAYLOAD

        timeout = httpx.Timeout(8.0)
        headers = {"Accept": "application/vnd.github+json"}
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                latest_res, list_res = await asyncio.gather(
                    client.get(
                        GITHUB_OJO_LATEST_RELEASE_URL,
                        headers=headers,
                    ),
                    client.get(
                        GITHUB_OJO_RELEASES_URL,
                        params={"per_page": 2},
                        headers=headers,
                    ),
                )
        except httpx.HTTPError:
            if OJO_RELEASE_CACHE_PAYLOAD is not None:
                return _fallback_payload(cached_payload=OJO_RELEASE_CACHE_PAYLOAD)
            return _fallback_payload()

        latest_payload = latest_res.json() if latest_res.is_success else {}
        list_payload = list_res.json() if list_res.is_success else []
        payload: JSONDict = {
            "latest": latest_payload if isinstance(latest_payload, dict) else {},
            "releases": list_payload if isinstance(list_payload, list) else [],
            "latest_ok": latest_res.is_success,
            "releases_ok": list_res.is_success,
        }
        globals()["OJO_RELEASE_CACHE_PAYLOAD"] = payload
        globals()["OJO_RELEASE_CACHE_EXPIRES_AT"] = now + OJO_RELEASE_CACHE_TTL_SECONDS
        return payload
