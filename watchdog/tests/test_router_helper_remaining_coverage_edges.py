"""
Copyright (c) 2026 Stefan Kumarasinghe.

Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the
License. You may obtain a copy of the License at
http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, Request

from tests._env import ensure_test_env

ensure_test_env()

from config import _slug_token
from middleware.error_handlers import RouteErrorHandlerOptions, handle_route_errors
from middleware import error_handlers as error_handlers_module
from routers.observability import agents_router
from routers.platform import system_router
from services.agent import helpers as agent_helpers
from services.common import encryption as encryption_module


def _request_with_header(request_id: str) -> Request:
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "path": "/",
            "headers": [(b"x-request-id", request_id.encode("utf-8"))],
            "client": ("127.0.0.1", 1234),
            "scheme": "http",
            "query_string": b"",
        }
    )


def test_slug_token_collapses_multiple_hyphens():
    assert _slug_token("A__B---C", "fallback") == "a-b-c"


@pytest.mark.asyncio
async def test_handle_route_errors_reads_request_id_from_kwargs_request():
    @handle_route_errors(RouteErrorHandlerOptions(gateway_timeout_detail="timed-out"))
    async def raises_timeout(*, request: Request):
        _ = request
        raise asyncio.TimeoutError()

    with pytest.raises(HTTPException) as exc:
        await raises_timeout(request=_request_with_header("req-kw"))

    assert exc.value.status_code == 504
    assert exc.value.headers and exc.value.headers.get("X-Request-ID") == "req-kw"


@pytest.mark.asyncio
async def test_agents_router_aggregates_host_names_from_heartbeat_registry(monkeypatch):
    class _Key:
        def __init__(self, key, name, enabled=True):
            self.key = key
            self.name = name
            self.is_enabled = enabled

    monkeypatch.setattr(agents_router.auth_service, "list_api_keys", lambda *_args: [_Key("org-a", "A")])

    async def _activity(_key, _client):
        return {
            "metrics_active": True,
            "metrics_count": 1,
        }

    monkeypatch.setattr(agents_router.agent_service, "key_activity", _activity)
    monkeypatch.setattr(
        agents_router.agent_service,
        "list_agents",
        lambda: [
            SimpleNamespace(
                tenant_id="org-a",
                host_name="host-a",
                attributes={"service.instance.id": "from-attr", "instance_id": " from-attr-2 "},
            )
        ],
    )

    user = SimpleNamespace(user_id="u1")
    active = await agents_router.list_active_agents(user)
    assert active[0]["host_names"] == ["host-a"]


@pytest.mark.asyncio
async def test_agents_router_returns_empty_list_when_no_api_keys(monkeypatch):
    monkeypatch.setattr(agents_router.auth_service, "list_api_keys", lambda *_args: [])
    monkeypatch.setattr(agents_router.agent_service, "list_agents", lambda: [])

    user = SimpleNamespace(user_id="u1")
    active = await agents_router.list_active_agents(user)
    assert active == []


@pytest.mark.asyncio
async def test_system_router_quota_scope_fallback_and_forbidden_paths(monkeypatch):
    captured = []

    async def _fake_get_quotas(current_user, tenant_scope=None):
        captured.append(tenant_scope)
        return {"ok": True, "scope": tenant_scope}

    monkeypatch.setattr(system_router.quota_service, "get_quotas", _fake_get_quotas)

    token = SimpleNamespace(user_id="u1", org_id="", tenant_id="tenant-fallback")
    out = await system_router.get_system_quotas(org_id="", current_user=token)
    assert out["scope"] == "tenant-fallback"

    monkeypatch.setattr(
        system_router.auth_service,
        "list_api_keys",
        lambda *_args, **_kwargs: [SimpleNamespace(key="org-a", is_shared=True, can_use=False)],
    )

    monkeypatch.setattr(
        system_router.auth_service,
        "list_api_keys",
        lambda *_args, **_kwargs: [SimpleNamespace(key="org-allowed", is_shared=False, can_use=False)],
    )
    out_allowed = await system_router.get_system_quotas(
        org_id="org-allowed",
        current_user=SimpleNamespace(user_id="u1", org_id="", tenant_id="tenant-fallback"),
    )
    assert out_allowed["scope"] == "org-allowed"

    monkeypatch.setattr(
        system_router.auth_service,
        "list_api_keys",
        lambda *_args, **_kwargs: [SimpleNamespace(key="org-a", is_shared=True, can_use=False)],
    )

    with pytest.raises(HTTPException) as exc:
        await system_router.get_system_quotas(
            org_id="org-denied", current_user=SimpleNamespace(user_id="u1", org_id="", tenant_id="tenant-fallback")
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_system_router_ojo_releases_returns_cached_inside_lock(monkeypatch):
    class _FailingAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, *args, **kwargs):
            raise AssertionError("Network should not be called when lock-path cache is hot")

    monkeypatch.setattr(system_router.httpx, "AsyncClient", _FailingAsyncClient)

    if system_router.ojo_release_cache_lock.locked():
        system_router.ojo_release_cache_lock.release()

    await system_router.ojo_release_cache_lock.acquire()

    async def _call_release():
        return await system_router.get_ojo_releases(_current_user=SimpleNamespace())

    task = asyncio.create_task(_call_release())
    await asyncio.sleep(0)

    monkeypatch.setattr(
        system_router,
        "OJO_RELEASE_CACHE_PAYLOAD",
        {"latest": {}, "releases": [], "latest_ok": True, "releases_ok": True},
    )
    monkeypatch.setattr(system_router, "OJO_RELEASE_CACHE_EXPIRES_AT", 10_000_000.0)
    monkeypatch.setattr(system_router.time, "monotonic", lambda: 1_000_000.0)

    system_router.ojo_release_cache_lock.release()
    payload = await task
    assert payload["latest_ok"] is True


class _AgentResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _MimirClientMetricsOnly:
    async def get(self, url, params=None, headers=None):
        if url.endswith("/query"):
            return _AgentResponse({"data": {"result": [{"value": [0, "2"]}]}})
        return _AgentResponse({})


@pytest.mark.asyncio
async def test_agent_helpers_query_key_activity_returns_metrics_only(monkeypatch):
    result = await agent_helpers.query_key_activity("org-a", _MimirClientMetricsOnly())
    assert result["metrics_active"] is True
    assert result["metrics_count"] == 2


def test_encryption_non_serializable_and_non_object_payload(monkeypatch):
    class _DummyFernet:
        def encrypt(self, payload: bytes) -> bytes:
            return b"abc"

        def decrypt(self, payload: bytes) -> bytes:
            return json.dumps([1, 2, 3]).encode("utf-8")

    monkeypatch.setattr(encryption_module, "_get_fernet", lambda: _DummyFernet())

    with pytest.raises(ValueError, match="JSON-serializable"):
        encryption_module.encrypt_config({"bad": object()})

    with pytest.raises(ValueError, match="decrypt to an object"):
        encryption_module.decrypt_config({"__encrypted__": "abc"})


def test_request_id_from_route_args_loop_branch():
    req = _request_with_header("req-loop")
    got = error_handlers_module._request_id_from_route_args(("not-request", req), {})
    assert got == "req-loop"
