"""
Copyright (c) 2026 Stefan Kumarasinghe.

Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the
License. You may obtain a copy of the License at
http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

import inspect
from datetime import UTC, datetime
from types import SimpleNamespace

from fastapi import Request

try:
    from ._env import ensure_test_env
except ImportError:
    from tests._env import ensure_test_env

ensure_test_env()

from models.access.auth_models import Role, TokenData


async def run_in_threadpool_inline(func, *args, **kwargs):
    """Execute sync/async callables inline while preserving awaitable behavior."""
    result = func(*args, **kwargs)
    if inspect.isawaitable(result):
        return await result
    return result


def token_data(
    *,
    user_id: str = "admin-1",
    username: str = "admin",
    tenant_id: str = "tenant-1",
    org_id: str = "org-1",
    role: Role = Role.ADMIN,
    permissions: list[str] | None = None,
    is_superuser: bool = False,
) -> TokenData:
    return TokenData(
        user_id=user_id,
        username=username,
        tenant_id=tenant_id,
        org_id=org_id,
        role=role,
        permissions=list(permissions or []),
        group_ids=[],
        is_superuser=is_superuser,
        is_mfa_setup=False,
    )


def request_obj(path: str = "/api/auth/register") -> Request:
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "POST",
        "path": path,
        "headers": [],
        "client": ("127.0.0.1", 1234),
        "scheme": "http",
        "query_string": b"",
    }
    return Request(scope)


def fake_user(
    *,
    user_id: str = "user-1",
    username: str = "user",
    email: str = "user@example.com",
    full_name: str | None = "Example User",
    role: Role = Role.USER,
    tenant_id: str = "tenant-1",
):
    now = datetime.now(UTC)
    return SimpleNamespace(
        id=user_id,
        username=username,
        email=email,
        full_name=full_name,
        role=role,
        tenant_id=tenant_id,
        group_ids=[],
        is_active=True,
        org_id="org-1",
        created_at=now,
        last_login=None,
        permissions=[],
        direct_permissions=[],
        needs_password_change=False,
        mfa_enabled=False,
        must_setup_mfa=False,
        auth_provider="local",
    )
