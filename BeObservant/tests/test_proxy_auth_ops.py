"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

import os
from types import SimpleNamespace

import pytest
from starlette.requests import Request

os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/observantio_test")
os.environ.setdefault("CORS_ALLOW_CREDENTIALS", "False")
os.environ.setdefault("CORS_ORIGINS", "http://localhost")

from services.grafana import proxy_auth_ops
from models.access.auth_models import Permission, Role, TokenData
from fastapi import HTTPException


class _GrafanaServiceStub:
    def __init__(self, *, datasource=None, datasources=None):
        self._datasource = datasource
        self._datasources = list(datasources or [])

    async def get_datasource(self, uid: str):
        return self._datasource

    async def get_datasources(self):
        return self._datasources


class _ProxyStub:
    def __init__(self, grafana_service):
        self.grafana_service = grafana_service


class _DsObj:
    def __init__(self, *, uid=None, ds_id=None, is_default=False, read_only=False):
        self.uid = uid
        self.id = ds_id
        self.is_default = is_default
        self.read_only = read_only


@pytest.mark.asyncio
async def test_lookup_safe_system_datasource_by_uid_allows_default():
    service = _ProxyStub(_GrafanaServiceStub(datasource=_DsObj(uid="default-prom", is_default=True)))

    allowed = await proxy_auth_ops._lookup_safe_system_datasource(
        service,
        datasource_uid="default-prom",
        datasource_id=None,
    )

    assert allowed is True


@pytest.mark.asyncio
async def test_lookup_safe_system_datasource_by_id_allows_read_only():
    service = _ProxyStub(_GrafanaServiceStub(datasources=[_DsObj(ds_id=12, read_only=True)]))

    allowed = await proxy_auth_ops._lookup_safe_system_datasource(
        service,
        datasource_uid=None,
        datasource_id=12,
    )

    assert allowed is True


@pytest.mark.asyncio
async def test_lookup_safe_system_datasource_rejects_non_system():
    service = _ProxyStub(_GrafanaServiceStub(datasource=_DsObj(uid="private-ds", is_default=False, read_only=False)))

    allowed = await proxy_auth_ops._lookup_safe_system_datasource(
        service,
        datasource_uid="private-ds",
        datasource_id=None,
    )

    assert allowed is False


def test_blocked_proxy_path_disallows_public_dashboards_and_snapshots():
    assert proxy_auth_ops._is_blocked_proxy_path("/grafana/public-dashboards/abcd1234")
    assert proxy_auth_ops._is_blocked_proxy_path("/grafana/dashboard/snapshot/xyz")
    assert proxy_auth_ops._is_blocked_proxy_path("/grafana/api/public/dashboards/uid/abcd")
    assert proxy_auth_ops._is_blocked_proxy_path("/grafana/api/snapshots/abcd")
    assert not proxy_auth_ops._is_blocked_proxy_path("/grafana/d/private-uid/private-dash")


def _request(path: str, *, method: str = "GET", headers: list[tuple[bytes, bytes]] | None = None) -> Request:
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": method,
            "path": path,
            "headers": headers or [],
            "client": ("127.0.0.1", 1234),
            "scheme": "http",
            "query_string": b"",
        }
    )


def _token_data(**overrides) -> TokenData:
    values = {
        "user_id": "u1",
        "username": "alice",
        "tenant_id": "tenant-a",
        "org_id": "org-a",
        "role": Role.USER,
        "permissions": [Permission.READ_DASHBOARDS.value],
        "group_ids": ["g1"],
        "is_superuser": False,
    }
    values.update(overrides)
    return TokenData(**values)


def test_proxy_role_helpers_accept_string_roles():
    assert proxy_auth_ops.is_admin_user(_token_data(role="admin")) is True
    assert proxy_auth_ops.is_admin_user(_token_data(role="user")) is False


def test_proxy_permission_gate_blocks_invalid_paths_and_folder_writes():
    with pytest.raises(HTTPException, match="Public/snapshot dashboard links are disabled"):
        proxy_auth_ops._enforce_proxy_permission_gate(
            _token_data(),
            original_path="/grafana/public-dashboards/uid/abc",
            original_method="GET",
        )

    with pytest.raises(HTTPException, match="Direct Grafana folder write API is disabled"):
        proxy_auth_ops._enforce_proxy_permission_gate(
            _token_data(permissions=[Permission.CREATE_FOLDERS.value]),
            original_path="/grafana/api/folders",
            original_method="POST",
        )

    proxy_auth_ops._enforce_proxy_permission_gate(
        _token_data(role="admin", permissions=[Permission.CREATE_FOLDERS.value]),
        original_path="/grafana/api/folders",
        original_method="POST",
    )


@pytest.mark.asyncio
async def test_authorize_proxy_request_applies_db_context(monkeypatch):
    proxy_auth_ops.clear_proxy_auth_cache()
    token_data = _token_data(permissions=[Permission.READ_DASHBOARDS.value])
    auth_service = SimpleNamespace(decode_token=lambda token: token_data)
    service = _ProxyStub(_GrafanaServiceStub())

    async def fake_run_in_threadpool(func, *args, **kwargs):
        return func(*args, **kwargs)

    context = proxy_auth_ops.ProxyAuthorizationContext(
        org_id="scoped-org",
        permissions=[Permission.READ_DASHBOARDS.value, Permission.READ_FOLDERS.value],
        group_ids=["g9"],
        dashboard=None,
        datasource_by_uid=None,
        datasource_by_id=None,
        folder=None,
    )

    monkeypatch.setattr(proxy_auth_ops, "run_in_threadpool", fake_run_in_threadpool)
    monkeypatch.setattr(proxy_auth_ops, "_db_load_context", lambda *args, **kwargs: (object(), context))

    async def noop_async(*args, **kwargs):
        return None

    monkeypatch.setattr(proxy_auth_ops, "_authorize_dashboard_access", noop_async)
    monkeypatch.setattr(proxy_auth_ops, "_authorize_datasource_access", noop_async)
    monkeypatch.setattr(proxy_auth_ops, "_authorize_folder_access", lambda *args, **kwargs: None)

    request = _request(
        "/grafana/api/search",
        headers=[
            (b"authorization", b"Bearer token-1"),
            (b"x-original-uri", b"/grafana/api/search"),
            (b"x-original-method", b"GET"),
        ],
    )

    headers = await proxy_auth_ops.authorize_proxy_request(service, request, auth_service)

    assert headers["X-WEBAUTH-USER"] == "alice"
    assert headers["X-WEBAUTH-TENANT"] == "tenant-a"
    assert token_data.org_id == "scoped-org"
    assert token_data.permissions == [Permission.READ_DASHBOARDS.value, Permission.READ_FOLDERS.value]
    assert token_data.group_ids == ["g9"]


@pytest.mark.asyncio
async def test_authorize_proxy_request_allows_static_paths_without_db_lookup(monkeypatch):
    proxy_auth_ops.clear_proxy_auth_cache()
    token_data = _token_data(username="bob")
    auth_service = SimpleNamespace(decode_token=lambda token: token_data)
    service = _ProxyStub(_GrafanaServiceStub())

    async def fake_run_in_threadpool(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(proxy_auth_ops, "run_in_threadpool", fake_run_in_threadpool)

    def fail_db(*args, **kwargs):
        raise AssertionError("db lookup should not happen for static paths")

    monkeypatch.setattr(proxy_auth_ops, "_db_load_context", fail_db)

    request = _request(
        "/grafana/public/build/app.js",
        headers=[
            (b"authorization", b"Bearer token-2"),
            (b"x-original-uri", b"/grafana/public/build/app.js"),
            (b"x-original-method", b"GET"),
        ],
    )

    headers = await proxy_auth_ops.authorize_proxy_request(service, request, auth_service)

    assert headers == {
        "X-WEBAUTH-USER": "bob",
        "X-WEBAUTH-TENANT": "tenant-a",
        "X-WEBAUTH-ROLE": "Viewer",
    }
