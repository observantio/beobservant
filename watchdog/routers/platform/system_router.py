"""
Router for system-level operations such as retrieving system metrics, health status, and performing maintenance tasks.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

import asyncio
import time
from typing import Optional
import httpx

from fastapi import APIRouter, Depends, HTTPException, Query, status

from services.system_service import SystemService
from models.access.auth_models import Permission, TokenData
from models.access.quota_models import QuotasResponse
from middleware.dependencies import auth_service, require_permission_with_scope
from middleware.error_handlers import handle_route_errors
from custom_types.json import JSONDict
from services.quota_service import quota_service

router = APIRouter(prefix="/api/system", tags=["system"])
system_service = SystemService()
GITHUB_OJO_LATEST_RELEASE_URL = "https://api.github.com/repos/observantio/ojo/releases/latest"
GITHUB_OJO_RELEASES_URL = "https://api.github.com/repos/observantio/ojo/releases"
OJO_RELEASE_CACHE_TTL_SECONDS = 3600
ojo_release_cache_payload: Optional[JSONDict] = None
ojo_release_cache_expires_at: float = 0.0
ojo_release_cache_lock = asyncio.Lock()


@router.get("/metrics", response_model=JSONDict)
@handle_route_errors(internal_detail="Failed to retrieve system metrics")
async def get_system_metrics(
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_AGENTS, "system"))
) -> JSONDict:
    return system_service.get_all_metrics()


@router.get("/quotas", response_model=QuotasResponse)
@handle_route_errors(internal_detail="Failed to retrieve system quotas")
async def get_system_quotas(
    org_id: Optional[str] = Query(default=None, alias="orgId"),
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_AGENTS, "system"))
) -> QuotasResponse:
    requested_org = org_id if isinstance(org_id, str) else None
    selected_org = str(requested_org or current_user.org_id or "").strip()
    if not selected_org:
        selected_org = str(current_user.tenant_id)

    if requested_org:
        visible_keys = auth_service.list_api_keys(current_user.user_id, show_hidden=False)
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
@handle_route_errors(internal_detail="Failed to retrieve Ojo release metadata")
async def get_ojo_releases(
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_AGENTS, "system"))
) -> JSONDict:
    now = time.monotonic()
    if ojo_release_cache_payload is not None and now < ojo_release_cache_expires_at:
        return ojo_release_cache_payload

    async with ojo_release_cache_lock:
        now = time.monotonic()
        if ojo_release_cache_payload is not None and now < ojo_release_cache_expires_at:
            return ojo_release_cache_payload

        timeout = httpx.Timeout(8.0)
        headers = {"Accept": "application/vnd.github+json"}
        async with httpx.AsyncClient(timeout=timeout) as client:
            latest_res, list_res = await client.get(
                GITHUB_OJO_LATEST_RELEASE_URL,
                headers=headers,
            ), await client.get(
                GITHUB_OJO_RELEASES_URL,
                params={"per_page": 8},
                headers=headers,
            )

        latest_payload = latest_res.json() if latest_res.is_success else {}
        list_payload = list_res.json() if list_res.is_success else []
        payload: JSONDict = {
            "latest": latest_payload if isinstance(latest_payload, dict) else {},
            "releases": list_payload if isinstance(list_payload, list) else [],
            "latest_ok": latest_res.is_success,
            "releases_ok": list_res.is_success,
        }
        globals()["ojo_release_cache_payload"] = payload
        globals()["ojo_release_cache_expires_at"] = now + OJO_RELEASE_CACHE_TTL_SECONDS
        return payload
