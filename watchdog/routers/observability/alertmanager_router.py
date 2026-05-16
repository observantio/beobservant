"""
Alertmanager API proxy router for Watchdog, forwarding requests to the internal Notifier Proxy Service which handles
authentication, authorization, and forwarding to the Alertmanager API.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the
License. You may obtain a copy of the License at
http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

import json
from json import JSONDecodeError
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status

from config import config
from custom_types.json import JSONDict
from middleware.dependencies import (
    PublicEndpointSecurityConfig,
    apply_scoped_rate_limit,
    enforce_public_endpoint_security,
    get_current_user_or_mfa_setup,
)
from models.access.auth_models import TokenData
from services.alerts.helpers import (
    assert_silence_owner,
    check_permissions,
    extract_silence_id,
    find_silence_for_mutation,
    is_mutating,
    required_permissions,
    validate_and_normalize_silence_payload,
    webhook_route,
)
from services.notifier_proxy_service import NotifierForwardRequest, notifier_proxy_service

router = APIRouter(prefix="/api/alertmanager", tags=["alertmanager"])
webhook_router = APIRouter(tags=["alertmanager-webhooks"])

webhook_router.add_api_route(
    "/alerts/webhook",
    webhook_route("webhook", "alertmanager.webhook", "alertmanager_webhook"),
    methods=["POST"],
)
webhook_router.add_api_route(
    "/alerts/critical",
    webhook_route("critical", "alertmanager.webhook.critical", "alertmanager_critical"),
    methods=["POST"],
)
webhook_router.add_api_route(
    "/alerts/warning",
    webhook_route("warning", "alertmanager.webhook.warning", "alertmanager_warning"),
    methods=["POST"],
)


@router.get(
    "/public/rules",
    responses={
        200: {
            "description": "OK",
            "content": {"application/json": {"schema": {"$ref": "#/components/schemas/JSONValue-Output"}}},
        }
    },
)
async def public_rules_proxy(request: Request) -> Any:
    enforce_public_endpoint_security(
        request,
        PublicEndpointSecurityConfig(
            scope="alertmanager_public_rules",
            limit=config.RATE_LIMIT_PUBLIC_PER_MINUTE,
            window_seconds=60,
            allowlist=config.AUTH_PUBLIC_IP_ALLOWLIST,
        ),
    )
    return await notifier_proxy_service.forward(
        NotifierForwardRequest(
            request=request,
            upstream_path="/internal/v1/api/alertmanager/public/rules",
            current_user=None,
            require_api_key=False,
            audit_action="alertmanager.public_rules.proxy",
        ),
    )


@router.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def alertmanager_proxy(
    path: str,
    request: Request,
    current_user: TokenData = Depends(get_current_user_or_mfa_setup),
) -> object:
    required = required_permissions(path, request.method)
    if required is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Route is not authorized")
    check_permissions(current_user, required)

    method = request.method.upper()
    payload: JSONDict | None = None
    request_body: bytes | None = None

    if path.strip("/").startswith("silences") and method in {"POST", "PUT"}:
        try:
            payload_raw = await request.json()
        except JSONDecodeError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON body") from exc
        payload = validate_and_normalize_silence_payload(payload_raw, current_user)
        payload.pop("shared_group_ids", None)
        request_body = json.dumps(payload).encode("utf-8")

    if path.strip("/").startswith("silences") and method in {"PUT", "DELETE"}:
        silence_id = extract_silence_id(path, payload)
        if not silence_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Silence id is required")
        existing_silence = await find_silence_for_mutation(
            request=request, current_user=current_user, silence_id=silence_id
        )
        assert_silence_owner(current_user, existing_silence)

    apply_scoped_rate_limit(current_user, "alertmanager")

    return await notifier_proxy_service.forward(
        NotifierForwardRequest(
            request=request,
            upstream_path=f"/internal/v1/api/alertmanager/{path}",
            current_user=current_user,
            require_api_key=is_mutating(request.method),
            audit_action="alertmanager.proxy",
            request_body=request_body,
        ),
    )
