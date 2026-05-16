"""
Helper functions for authentication and authorization operations.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the
License. You may obtain a copy of the License at
http://www.apache.org/licenses/LICENSE-2.0
"""

import importlib
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TypeAlias
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from fastapi import Depends, HTTPException, Request, Response, status
from sqlalchemy import String, or_
from sqlalchemy.orm import Session
from sqlalchemy.orm.query import RowReturningQuery

from config import config
from custom_types.json import JSONDict
from db_models import AuditLog, User
from middleware.dependencies import (
    PublicEndpointSecurityConfig,
    enforce_public_endpoint_security,
    require_permission_with_scope,
)
from models.access.auth_models import ROLE_PERMISSIONS, Permission, Role, TokenData
from services.auth.delegation import is_admin_actor as _is_admin_actor
from services.auth.delegation import role_to_text as _role_to_text
from services.common.cookies import cookie_secure

logger = logging.getLogger(__name__)

AuditLogQueryRow: TypeAlias = tuple[AuditLog, str, str]


@dataclass(frozen=True, slots=True)
class AuditLogFilterParams:
    start: object
    end: object
    user_id: str | None
    action: str | None
    resource_type: str | None
    q: str | None = None


AUDIT_SENSITIVE_SUBSTRINGS = (
    "token",
    "secret",
    "password",
    "passcode",
    "authorization",
    "bearer",
    "jwt",
)

AUDIT_SENSITIVE_EXACT_KEYS = {
    "mfa_code",
    "setup_token",
    "auth_code",
    "oauth_code",
    "code",
}


def invalidate_grafana_proxy_auth_cache() -> None:
    try:
        mod = importlib.import_module("services.grafana.proxy_auth_ops")
        mod.clear_proxy_auth_cache()
    except (AttributeError, ImportError) as exc:
        logger.warning("Failed to invalidate Grafana proxy auth cache: %s", exc)


def require_admin_with_audit_permission(
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_AUDIT_LOGS, "auth")),
) -> TokenData:
    if not is_admin_check(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required to view audit logs")
    return current_user


def set_auth_cookie(request: Request, response: Response, token: str) -> None:
    secure_flag = bool(config.FORCE_SECURE_COOKIES) or cookie_secure(request)
    response.set_cookie(
        key="watchdog_token",
        value=token,
        httponly=True,
        secure=secure_flag,
        samesite="lax",
        max_age=config.JWT_EXPIRATION_MINUTES * 60,
        path="/",
    )


def audit_key_is_sensitive(key: str) -> bool:
    lowered = str(key or "").strip().lower()
    if lowered == "status_code":
        return False
    if lowered in AUDIT_SENSITIVE_EXACT_KEYS:
        return True
    return any(marker in lowered for marker in AUDIT_SENSITIVE_SUBSTRINGS)


def redact_query_string(raw: str) -> str:
    if not raw:
        return ""
    pairs = parse_qsl(raw, keep_blank_values=True)
    sanitized = []
    for key, value in pairs:
        sanitized.append((key, "[REDACTED]" if audit_key_is_sensitive(key) else value))
    return urlencode(sanitized, doseq=True)


def sanitize_resource_id(resource_id: str | None) -> str:
    text = str(resource_id or "")
    if not text or "?" not in text:
        return text
    parsed = urlsplit(text)
    if not parsed.query:
        return text
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, redact_query_string(parsed.query), parsed.fragment))


def sanitize_audit_details(details: JSONDict | None) -> JSONDict:
    source = details if isinstance(details, dict) else {}
    sanitized: JSONDict = {}
    for key, value in source.items():
        if audit_key_is_sensitive(key):
            sanitized[key] = "[REDACTED]"
            continue
        if key == "query" and isinstance(value, str):
            sanitized[key] = redact_query_string(value)
            continue
        sanitized[key] = value
    return sanitized


def clear_auth_cookie(request: Request, response: Response) -> None:
    secure_flag = bool(config.FORCE_SECURE_COOKIES) or cookie_secure(request)
    response.set_cookie(
        key="watchdog_token",
        value="",
        httponly=True,
        secure=secure_flag,
        samesite="lax",
        max_age=0,
        expires=0,
        path="/",
    )


def build_audit_log_query(
    db: Session,
    current_user: TokenData,
    tenant_id: str | None,
    actor: type[User],
) -> RowReturningQuery[AuditLogQueryRow]:
    query = db.query(AuditLog, actor.username, actor.email).outerjoin(actor, actor.id == AuditLog.user_id)
    if not getattr(current_user, "is_superuser", False):
        query = query.filter(AuditLog.tenant_id == current_user.tenant_id)
    elif tenant_id:
        query = query.filter(AuditLog.tenant_id == tenant_id)
    return query


def role_permission_strings(role: object) -> list[str]:
    if not isinstance(role, Role):
        return []
    return [p.value for p in ROLE_PERMISSIONS.get(role, [])]


def perms_check(user: TokenData) -> set[str]:
    return {str(permission) for permission in (getattr(user, "permissions", []) or [])}


def is_admin_check(user: TokenData) -> bool:
    return _is_admin_actor(
        actor_role=_role_to_text(getattr(user, "role", None)),
        actor_is_superuser=bool(getattr(user, "is_superuser", False)),
    )


def apply_audit_filters_func(
    query: RowReturningQuery[AuditLogQueryRow],
    params: AuditLogFilterParams,
) -> RowReturningQuery[AuditLogQueryRow]:
    def _normalize_bound(value: object, *, end_of_minute: bool) -> object:
        if not isinstance(value, datetime):
            return value
        normalized = value
        if normalized.tzinfo is not None:
            # Audit timestamps are stored as timezone-naive UTC in the DB.
            normalized = normalized.astimezone(UTC).replace(tzinfo=None)
        if end_of_minute and normalized.second == 0 and normalized.microsecond == 0:
            # Datetime-local inputs are minute precision; make "end" inclusive.
            normalized = normalized.replace(second=59, microsecond=999999)
        return normalized

    start = _normalize_bound(params.start, end_of_minute=False)
    end = _normalize_bound(params.end, end_of_minute=True)

    if start:
        query = query.filter(AuditLog.created_at >= start)
    if end:
        query = query.filter(AuditLog.created_at <= end)
    if params.user_id:
        query = query.filter(AuditLog.user_id == params.user_id)
    if params.action:
        query = query.filter(AuditLog.action == params.action)
    if params.resource_type:
        resource_pattern = audit_text_like_pattern(params.resource_type)
        query = query.filter(AuditLog.resource_type.ilike(resource_pattern, escape="\\"))
    if params.q:
        pattern = audit_text_like_pattern(params.q)
        query = query.filter(
            or_(
                AuditLog.details.cast(String).ilike(pattern, escape="\\"),
                AuditLog.action.ilike(pattern, escape="\\"),
                AuditLog.resource_type.ilike(pattern, escape="\\"),
                AuditLog.resource_id.cast(String).ilike(pattern, escape="\\"),
                AuditLog.ip_address.ilike(pattern, escape="\\"),
                AuditLog.user_agent.ilike(pattern, escape="\\"),
            )
        )
    return query


def audit_text_like_pattern(text: object) -> str:
    raw = str(text or "").strip()
    if not raw:
        return "%"
    wildcard_mode = "*" in raw or "?" in raw
    escaped = []
    for ch in raw:
        if ch == "*":
            escaped.append("%")
        elif ch == "?":
            escaped.append("_")
        elif ch in {"%", "_", "\\"}:
            escaped.append(f"\\{ch}")
        else:
            escaped.append(ch)
    body = "".join(escaped)
    return body if wildcard_mode else f"%{body}%"


def rate_limit_func(request: Request, scope: str, limit: int, window: int) -> None:
    enforce_public_endpoint_security(
        request,
        PublicEndpointSecurityConfig(
            scope=scope,
            limit=limit,
            window_seconds=window,
            allowlist=config.AUTH_PUBLIC_IP_ALLOWLIST,
        ),
    )
