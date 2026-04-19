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

try:
    from ._env import ensure_test_env
except ImportError:
    from tests._env import ensure_test_env

ensure_test_env()

from models.access.auth_models import Role
from models.access.user_models import RegisterRequest
from routers.access.auth_router import authentication as auth_router
from tests._regression_helpers import request_obj, run_in_threadpool_inline


class _QueryStub:
    def __init__(self, tenant_obj):
        self.tenant_obj = tenant_obj
        self.filter_calls: list[dict[str, object]] = []

    def filter_by(self, **kwargs):
        self.filter_calls.append(kwargs)
        return self

    def first(self):
        return self.tenant_obj


@contextmanager
def _db_session_for(query_stub: _QueryStub):
    class _DB:
        def query(self, *_args, **_kwargs):
            return query_stub

    yield _DB()


def _register_payload() -> RegisterRequest:
    return RegisterRequest(username="new-user", email="new@example.com", password="Password123", full_name="New User")


async def _configure_register_common(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth_router, "rtp", run_in_threadpool_inline)
    monkeypatch.setattr(auth_router, "rate_limit_func", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(auth_router.auth_service, "is_external_auth_enabled", lambda: False)
    monkeypatch.setattr(
        auth_router.auth_service,
        "create_user",
        lambda *_args: SimpleNamespace(username="new-user", email="new@example.com", full_name="New User", role=Role.USER),
    )
    monkeypatch.setattr(auth_router.auth_service, "build_user_response", lambda *_args: SimpleNamespace(api_keys=[]))

    async def _send_welcome(**_kwargs):
        return True

    monkeypatch.setattr(auth_router.notification_service, "send_user_welcome_email", _send_welcome)


@pytest.mark.asyncio
async def test_register_queries_default_tenant_name(monkeypatch: pytest.MonkeyPatch) -> None:
    await _configure_register_common(monkeypatch)
    monkeypatch.setattr(auth_router.config, "DEFAULT_ADMIN_TENANT", "main-tenant")

    query_stub = _QueryStub(tenant_obj=SimpleNamespace(id="tenant-main"))
    monkeypatch.setattr(auth_router, "get_db_session", lambda: _db_session_for(query_stub))

    await auth_router.register(request_obj(), _register_payload())

    assert query_stub.filter_calls[0] == {"name": "main-tenant"}


@pytest.mark.asyncio
async def test_register_uses_resolved_tenant_id_when_lookup_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    await _configure_register_common(monkeypatch)
    monkeypatch.setattr(auth_router.config, "DEFAULT_ADMIN_TENANT", "main-tenant")

    captured = {}

    def _create_user(_user_create, tenant_id):
        captured["tenant_id"] = tenant_id
        return SimpleNamespace(username="new-user", email="new@example.com", full_name="New User", role=Role.USER)

    monkeypatch.setattr(auth_router.auth_service, "create_user", _create_user)

    query_stub = _QueryStub(tenant_obj=SimpleNamespace(id="tenant-main"))
    monkeypatch.setattr(auth_router, "get_db_session", lambda: _db_session_for(query_stub))

    await auth_router.register(request_obj(), _register_payload())

    assert captured["tenant_id"] == "tenant-main"


@pytest.mark.asyncio
async def test_register_falls_back_to_default_tenant_name_when_lookup_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    await _configure_register_common(monkeypatch)
    monkeypatch.setattr(auth_router.config, "DEFAULT_ADMIN_TENANT", "fallback-tenant")

    captured = {}

    def _create_user(_user_create, tenant_id):
        captured["tenant_id"] = tenant_id
        return SimpleNamespace(username="new-user", email="new@example.com", full_name="New User", role=Role.USER)

    monkeypatch.setattr(auth_router.auth_service, "create_user", _create_user)

    query_stub = _QueryStub(tenant_obj=None)
    monkeypatch.setattr(auth_router, "get_db_session", lambda: _db_session_for(query_stub))

    await auth_router.register(request_obj(), _register_payload())

    assert captured["tenant_id"] == "fallback-tenant"


@pytest.mark.asyncio
async def test_register_honors_runtime_changes_to_default_tenant_name(monkeypatch: pytest.MonkeyPatch) -> None:
    await _configure_register_common(monkeypatch)

    query_stub = _QueryStub(tenant_obj=None)
    monkeypatch.setattr(auth_router, "get_db_session", lambda: _db_session_for(query_stub))

    monkeypatch.setattr(auth_router.config, "DEFAULT_ADMIN_TENANT", "tenant-one")
    await auth_router.register(request_obj(), _register_payload())

    monkeypatch.setattr(auth_router.config, "DEFAULT_ADMIN_TENANT", "tenant-two")
    await auth_router.register(request_obj(), _register_payload())

    assert query_stub.filter_calls[0] == {"name": "tenant-one"}
    assert query_stub.filter_calls[1] == {"name": "tenant-two"}


@pytest.mark.asyncio
async def test_register_tenant_lookup_is_re_evaluated_each_call(monkeypatch: pytest.MonkeyPatch) -> None:
    await _configure_register_common(monkeypatch)
    monkeypatch.setattr(auth_router.config, "DEFAULT_ADMIN_TENANT", "default-tenant")

    captured_tenants: list[str] = []

    def _create_user(_user_create, tenant_id):
        captured_tenants.append(tenant_id)
        return SimpleNamespace(username="new-user", email="new@example.com", full_name="New User", role=Role.USER)

    monkeypatch.setattr(auth_router.auth_service, "create_user", _create_user)

    query_state = {"tenant": SimpleNamespace(id="tenant-a")}

    @contextmanager
    def _dynamic_session():
        yield SimpleNamespace(query=lambda *_args, **_kwargs: _QueryStub(query_state["tenant"]))

    monkeypatch.setattr(auth_router, "get_db_session", _dynamic_session)

    await auth_router.register(request_obj(), _register_payload())
    query_state["tenant"] = SimpleNamespace(id="tenant-b")
    await auth_router.register(request_obj(), _register_payload())

    assert captured_tenants == ["tenant-a", "tenant-b"]
