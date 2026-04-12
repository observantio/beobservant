"""
Copyright (c) 2026 Stefan Kumarasinghe.

Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the
License. You may obtain a copy of the License at
http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

try:
    from ._env import ensure_test_env
except ImportError:
    from tests._env import ensure_test_env

ensure_test_env()

from models.access.auth_models import Role
from models.access.user_models import RegisterRequest
from routers.access.auth_router import authentication as auth_router
from tests._regression_helpers import request_obj, run_in_threadpool_inline


@contextmanager
def _tenant_session(tenant_id: str | None):
    class _Query:
        def filter_by(self, **_kwargs):
            return self

        def first(self):
            return SimpleNamespace(id=tenant_id) if tenant_id else None

    class _DB:
        def query(self, *_args, **_kwargs):
            return _Query()

    yield _DB()


def _register_payload() -> RegisterRequest:
    return RegisterRequest(username="new-user", email="new@example.com", password="Password123", full_name="New User")


@pytest.mark.asyncio
async def test_register_rejects_when_external_auth_is_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth_router, "rtp", run_in_threadpool_inline)
    monkeypatch.setattr(auth_router, "rate_limit_func", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(auth_router.auth_service, "is_external_auth_enabled", lambda: True)

    with pytest.raises(HTTPException) as exc:
        await auth_router.register(request_obj(), _register_payload())

    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_register_uses_tenant_id_loaded_from_database(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth_router, "rtp", run_in_threadpool_inline)
    monkeypatch.setattr(auth_router, "rate_limit_func", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(auth_router.auth_service, "is_external_auth_enabled", lambda: False)
    monkeypatch.setattr(auth_router, "get_db_session", lambda: _tenant_session("tenant-from-db"))

    captured = {}

    def _create_user(user_create, tenant_id):
        captured["tenant_id"] = tenant_id
        captured["user_create"] = user_create
        return SimpleNamespace(username="new-user", email="new@example.com", full_name="New User", role=Role.USER)

    monkeypatch.setattr(auth_router.auth_service, "create_user", _create_user)
    monkeypatch.setattr(auth_router.auth_service, "build_user_response", lambda *_args: SimpleNamespace(api_keys=[]))

    async def _send_welcome_email(**_kwargs):
        return True

    monkeypatch.setattr(auth_router.notification_service, "send_user_welcome_email", _send_welcome_email)

    await auth_router.register(request_obj(), _register_payload())

    assert captured["tenant_id"] == "tenant-from-db"


@pytest.mark.asyncio
async def test_register_falls_back_to_default_tenant_name_when_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth_router, "rtp", run_in_threadpool_inline)
    monkeypatch.setattr(auth_router, "rate_limit_func", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(auth_router.auth_service, "is_external_auth_enabled", lambda: False)
    monkeypatch.setattr(auth_router, "get_db_session", lambda: _tenant_session(None))
    monkeypatch.setattr(auth_router.config, "DEFAULT_ADMIN_TENANT", "default-tenant")

    captured = {}

    def _create_user(_user_create, tenant_id):
        captured["tenant_id"] = tenant_id
        return SimpleNamespace(username="new-user", email="new@example.com", full_name="New User", role=Role.USER)

    monkeypatch.setattr(auth_router.auth_service, "create_user", _create_user)
    monkeypatch.setattr(auth_router.auth_service, "build_user_response", lambda *_args: SimpleNamespace(api_keys=[]))

    async def _send_welcome_email(**_kwargs):
        return True

    monkeypatch.setattr(auth_router.notification_service, "send_user_welcome_email", _send_welcome_email)

    await auth_router.register(request_obj(), _register_payload())

    assert captured["tenant_id"] == "default-tenant"


@pytest.mark.asyncio
async def test_register_calls_welcome_email_with_user_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth_router, "rtp", run_in_threadpool_inline)
    monkeypatch.setattr(auth_router, "rate_limit_func", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(auth_router.auth_service, "is_external_auth_enabled", lambda: False)
    monkeypatch.setattr(auth_router, "get_db_session", lambda: _tenant_session("tenant-1"))

    monkeypatch.setattr(
        auth_router.auth_service,
        "create_user",
        lambda *_args: SimpleNamespace(username="new-user", email="new@example.com", full_name="New User", role=Role.USER),
    )
    monkeypatch.setattr(auth_router.auth_service, "build_user_response", lambda *_args: SimpleNamespace(api_keys=[]))

    welcome_calls: list[dict[str, object]] = []

    async def _send_welcome_email(**kwargs):
        welcome_calls.append(kwargs)
        return True

    monkeypatch.setattr(auth_router.notification_service, "send_user_welcome_email", _send_welcome_email)

    await auth_router.register(request_obj(), _register_payload())

    assert welcome_calls[0]["recipient_email"] == "new@example.com"
    assert welcome_calls[0]["username"] == "new-user"
    assert welcome_calls[0]["full_name"] == "New User"


@pytest.mark.asyncio
async def test_register_returns_built_user_response(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth_router, "rtp", run_in_threadpool_inline)
    monkeypatch.setattr(auth_router, "rate_limit_func", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(auth_router.auth_service, "is_external_auth_enabled", lambda: False)
    monkeypatch.setattr(auth_router, "get_db_session", lambda: _tenant_session("tenant-1"))

    user_obj = SimpleNamespace(username="new-user", email="new@example.com", full_name="New User", role=Role.USER)
    response_obj = SimpleNamespace(id="u-1", username="new-user", api_keys=[])

    monkeypatch.setattr(auth_router.auth_service, "create_user", lambda *_args: user_obj)
    monkeypatch.setattr(auth_router.auth_service, "build_user_response", lambda *_args: response_obj)

    async def _send_welcome_email(**_kwargs):
        return True

    monkeypatch.setattr(auth_router.notification_service, "send_user_welcome_email", _send_welcome_email)

    result = await auth_router.register(request_obj(), _register_payload())

    assert result is response_obj
