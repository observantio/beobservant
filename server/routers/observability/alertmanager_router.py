"""
Alertmanager API proxy router for Be Observant, forwarding requests to the internal Benotified Proxy Service which handles authentication, authorization, and forwarding to the Alertmanager API.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""
from __future__ import annotations

from typing import Set

from fastapi import APIRouter, Depends, HTTPException, Request, status

from config import config
from middleware.dependencies import (
    apply_scoped_rate_limit,
    enforce_header_token,
    enforce_public_endpoint_security,
    get_current_user,
)
from models.access.auth_models import Permission, TokenData
from services.benotified_proxy_service import benotified_proxy_service

router = APIRouter(prefix="/api/alertmanager", tags=["alertmanager"])
webhook_router = APIRouter(tags=["alertmanager-webhooks"])

alertmanager_service = benotified_proxy_service
notification_service = None


def _required_permissions(path: str, method: str) -> Set[str]:
    p = f"/{path.strip('/')}" if path else "/"
    m = method.upper()

    if p in {"/alerts", "/alerts/groups", "/status", "/receivers"} and m == "GET":
        return {Permission.READ_ALERTS.value}
    if p == "/alerts" and m == "POST":
        return {Permission.CREATE_ALERTS.value, Permission.WRITE_ALERTS.value}
    if p == "/alerts" and m == "DELETE":
        return {Permission.DELETE_ALERTS.value}

    if p.startswith("/incidents"):
        if m == "GET":
            return {Permission.READ_INCIDENTS.value}
        return {Permission.UPDATE_INCIDENTS.value}

    if p.startswith("/silences"):
        if m == "GET":
            return {Permission.READ_SILENCES.value}
        if m == "POST":
            return {Permission.CREATE_SILENCES.value, Permission.WRITE_ALERTS.value}
        if m == "PUT":
            return {Permission.UPDATE_SILENCES.value, Permission.WRITE_ALERTS.value}
        if m == "DELETE":
            return {Permission.DELETE_SILENCES.value}

    if p.startswith("/rules/import") and m == "POST":
        return {Permission.CREATE_RULES.value, Permission.WRITE_ALERTS.value}
    if p.startswith("/rules"):
        if m == "GET":
            return {Permission.READ_RULES.value}
        if m == "POST":
            return {Permission.CREATE_RULES.value, Permission.WRITE_ALERTS.value, Permission.TEST_RULES.value}
        if m == "PUT":
            return {Permission.UPDATE_RULES.value, Permission.WRITE_ALERTS.value}
        if m == "DELETE":
            return {Permission.DELETE_RULES.value}

    if p.startswith("/channels"):
        if m == "GET":
            return {Permission.READ_CHANNELS.value}
        if m == "POST":
            return {Permission.CREATE_CHANNELS.value, Permission.WRITE_CHANNELS.value, Permission.TEST_CHANNELS.value}
        if m == "PUT":
            return {Permission.UPDATE_CHANNELS.value, Permission.WRITE_CHANNELS.value}
        if m == "DELETE":
            return {Permission.DELETE_CHANNELS.value}

    if p.startswith("/jira") or p.startswith("/integrations"):
        if p == "/jira/config":
            return {Permission.MANAGE_TENANTS.value}
        if m == "GET":
            return {Permission.READ_INCIDENTS.value, Permission.UPDATE_INCIDENTS.value, Permission.READ_CHANNELS.value}
        return {Permission.UPDATE_INCIDENTS.value}

    if p == "/metrics/names":
        return {
            Permission.READ_METRICS.value,
            Permission.CREATE_RULES.value,
            Permission.UPDATE_RULES.value,
            Permission.WRITE_ALERTS.value,
        }

    if p == "/public/rules":
        return set()

    return {Permission.READ_ALERTS.value}


def _check_permissions(current_user: TokenData, required: Set[str]) -> None:
    if not required:
        return
    if current_user.is_superuser:
        return
    perms = set(current_user.permissions or [])
    if perms.intersection(required):
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have permission to perform this action")


def _is_mutating(method: str) -> bool:
    return method.upper() in {"POST", "PUT", "PATCH", "DELETE"}


@webhook_router.post("/alerts/webhook")
async def alert_webhook(request: Request):
    enforce_public_endpoint_security(
        request,
        scope="alertmanager_webhook",
        limit=config.RATE_LIMIT_PUBLIC_PER_MINUTE,
        window_seconds=60,
        allowlist=config.WEBHOOK_IP_ALLOWLIST,
    )
    enforce_header_token(
        request,
        header_name="x-beobservant-webhook-token",
        expected_token=config.INBOUND_WEBHOOK_TOKEN,
        unauthorized_detail="Invalid webhook token",
    )
    return await benotified_proxy_service.forward(
        request=request,
        upstream_path="/internal/v1/alertmanager/alerts/webhook",
        current_user=None,
        require_api_key=False,
        audit_action="alertmanager.webhook",
    )


@webhook_router.post("/alerts/critical")
async def alert_critical(request: Request):
    enforce_public_endpoint_security(
        request,
        scope="alertmanager_critical",
        limit=config.RATE_LIMIT_PUBLIC_PER_MINUTE,
        window_seconds=60,
        allowlist=config.WEBHOOK_IP_ALLOWLIST,
    )
    enforce_header_token(
        request,
        header_name="x-beobservant-webhook-token",
        expected_token=config.INBOUND_WEBHOOK_TOKEN,
        unauthorized_detail="Invalid webhook token",
    )
    return await benotified_proxy_service.forward(
        request=request,
        upstream_path="/internal/v1/alertmanager/alerts/critical",
        current_user=None,
        require_api_key=False,
        audit_action="alertmanager.webhook.critical",
    )


@webhook_router.post("/alerts/warning")
async def alert_warning(request: Request):
    enforce_public_endpoint_security(
        request,
        scope="alertmanager_warning",
        limit=config.RATE_LIMIT_PUBLIC_PER_MINUTE,
        window_seconds=60,
        allowlist=config.WEBHOOK_IP_ALLOWLIST,
    )
    enforce_header_token(
        request,
        header_name="x-beobservant-webhook-token",
        expected_token=config.INBOUND_WEBHOOK_TOKEN,
        unauthorized_detail="Invalid webhook token",
    )
    return await benotified_proxy_service.forward(
        request=request,
        upstream_path="/internal/v1/alertmanager/alerts/warning",
        current_user=None,
        require_api_key=False,
        audit_action="alertmanager.webhook.warning",
    )


@router.get("/public/rules")
async def public_rules_proxy(request: Request):
    return await benotified_proxy_service.forward(
        request=request,
        upstream_path="/internal/v1/api/alertmanager/public/rules",
        current_user=None,
        require_api_key=False,
        audit_action="alertmanager.public_rules.proxy",
    )


@router.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def alertmanager_proxy(
    path: str,
    request: Request,
    current_user: TokenData = Depends(get_current_user),
):
    required = _required_permissions(path, request.method)
    _check_permissions(current_user, required)
    apply_scoped_rate_limit(current_user, "alertmanager")

    return await benotified_proxy_service.forward(
        request=request,
        upstream_path=f"/internal/v1/api/alertmanager/{path}",
        current_user=current_user,
        require_api_key=_is_mutating(request.method),
        audit_action="alertmanager.proxy",
    )


__all__ = ["router", "webhook_router", "alertmanager_service", "notification_service"]
