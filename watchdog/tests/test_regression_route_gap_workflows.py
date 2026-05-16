"""
Copyright (c) 2026 Stefan Kumarasinghe.

Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the
License. You may obtain a copy of the License at
http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi import HTTPException
from starlette.requests import Request

try:
    from ._env import ensure_test_env
except ImportError:
    from tests._env import ensure_test_env

ensure_test_env()

from routers.access.auth_router import api_keys as api_keys_router
from routers.observability import resolver_router
from routers.observability.grafana_router import dashboards
from tests._proxy_stubs import unpack_resolver_json_request
from tests._regression_helpers import run_in_threadpool_inline, token_data

from models.access.auth_models import Permission, Role
from models.observability.grafana_request_models import GrafanaDashboardPayloadRequest


def _request(path: str = "/api/resolver/analyze/jobs/job-1") -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "headers": [],
        "query_string": b"",
    }
    return Request(scope)


def _resolver_user():
    return token_data(
        user_id="u1",
        username="user",
        role=Role.USER,
        permissions=[Permission.READ_RCA.value, Permission.DELETE_RCA.value],
    )


@pytest.mark.asyncio
async def test_remove_api_key_share_forwards_actor_scope_to_service(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api_keys_router, "rtp", run_in_threadpool_inline)
    captured: dict[str, object] = {}

    async def _delete_api_key_share(user_id: str, tenant_id: str, key_id: str, shared_user_id: str) -> bool:
        captured.update(
            {
                "user_id": user_id,
                "tenant_id": tenant_id,
                "key_id": key_id,
                "shared_user_id": shared_user_id,
            }
        )
        return True

    monkeypatch.setattr(api_keys_router.auth_service, "delete_api_key_share", _delete_api_key_share)

    actor = token_data(
        user_id="admin-1",
        username="admin",
        role=Role.ADMIN,
        permissions=[Permission.UPDATE_API_KEYS.value],
    )
    result = await api_keys_router.remove_api_key_share("key-7", "user-9", actor)

    assert result == {"message": "API key share removed"}
    assert captured == {
        "user_id": "admin-1",
        "tenant_id": "tenant-1",
        "key_id": "key-7",
        "shared_user_id": "user-9",
    }


@pytest.mark.asyncio
async def test_save_dashboard_from_grafana_ui_rejects_update_miss_for_existing_uid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(dashboards, "rtp", run_in_threadpool_inline)
    monkeypatch.setattr(dashboards, "scope_context", lambda _user: ("u1", "tenant-1", ["g1"], True))
    monkeypatch.setattr(dashboards, "dashboard_payload", lambda payload: payload.model_dump(exclude_none=True))
    monkeypatch.setattr(dashboards, "dashboard_uid", lambda raw: str(raw.get("dashboard", {}).get("uid") or ""))
    monkeypatch.setattr(dashboards, "parse_dashboard_update_payload", lambda raw: {"update": raw})
    monkeypatch.setattr(dashboards, "parse_dashboard_create_payload", lambda raw: {"create": raw})
    monkeypatch.setattr(
        dashboards.proxy,
        "build_dashboard_search_context",
        lambda *_args, **_kwargs: {"uid_db_dashboard": object()},
    )

    calls = {"update": 0, "create": 0}

    async def _update_dashboard(**_kwargs):
        calls["update"] += 1
        return None

    async def _create_dashboard(**kwargs):
        calls["create"] += 1
        assert kwargs["request"].options.visibility == "private"
        return {"uid": "created-from-fallback", "status": "created"}

    monkeypatch.setattr(dashboards.proxy, "update_dashboard", _update_dashboard)
    monkeypatch.setattr(dashboards.proxy, "create_dashboard", _create_dashboard)

    payload = GrafanaDashboardPayloadRequest.model_validate({"dashboard": {"uid": "dash-1", "title": "Latency"}})
    with pytest.raises(HTTPException) as exc:
        await dashboards.save_dashboard_from_grafana_ui(payload, current_user=_resolver_user(), db="db")

    assert exc.value.status_code == 404
    assert calls == {"update": 1, "create": 0}


@pytest.mark.asyncio
async def test_get_analyze_job_proxies_expected_upstream_request(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    async def _resolve_tenant_id(_request: Request, _current_user):
        return "tenant-a"

    async def _request_json(req, **_kwargs):
        captured.update(unpack_resolver_json_request(req))
        return {
            "job_id": "job-1",
            "report_id": "rep-1",
            "status": "completed",
            "created_at": datetime.now(UTC).isoformat(),
            "tenant_id": "tenant-a",
            "requested_by": "u1",
        }

    monkeypatch.setattr(resolver_router, "resolve_tenant_id", _resolve_tenant_id)
    monkeypatch.setattr(resolver_router, "correlation_id", lambda _request: "corr-1")
    monkeypatch.setattr(resolver_router.resolver_proxy_service, "request_json", _request_json)

    result = await resolver_router.get_analyze_job("job-1", _request(), _resolver_user())

    assert result.job_id == "job-1"
    assert captured["method"] == "GET"
    assert captured["upstream_path"] == "/api/v1/jobs/job-1"
    assert captured["audit_action"] == "resolver.analyze_job.get"


@pytest.mark.asyncio
async def test_get_report_by_id_proxies_expected_upstream_request(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    async def _resolve_tenant_id(_request: Request, _current_user):
        return "tenant-a"

    async def _request_json(req, **_kwargs):
        captured.update(unpack_resolver_json_request(req))
        return {
            "job_id": "job-2",
            "report_id": "rep-2",
            "status": "completed",
            "tenant_id": "tenant-a",
            "requested_by": "u1",
            "result": {"summary": "ok"},
        }

    monkeypatch.setattr(resolver_router, "resolve_tenant_id", _resolve_tenant_id)
    monkeypatch.setattr(resolver_router, "correlation_id", lambda _request: "corr-2")
    monkeypatch.setattr(resolver_router.resolver_proxy_service, "request_json", _request_json)

    result = await resolver_router.get_report_by_id("rep-2", _request(), _resolver_user())

    assert result.report_id == "rep-2"
    assert captured["method"] == "GET"
    assert captured["upstream_path"] == "/api/v1/reports/rep-2"
    assert captured["audit_action"] == "resolver.report.get"


@pytest.mark.asyncio
async def test_delete_report_by_id_proxies_expected_upstream_request(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    async def _resolve_tenant_id(_request: Request, _current_user):
        return "tenant-a"

    async def _request_json(req, **_kwargs):
        captured.update(unpack_resolver_json_request(req))
        return {"report_id": "rep-3", "status": "deleted", "deleted": True}

    monkeypatch.setattr(resolver_router, "resolve_tenant_id", _resolve_tenant_id)
    monkeypatch.setattr(resolver_router, "correlation_id", lambda _request: "corr-3")
    monkeypatch.setattr(resolver_router.resolver_proxy_service, "request_json", _request_json)

    result = await resolver_router.delete_report_by_id("rep-3", _request(), _resolver_user())

    assert result.deleted is True
    assert captured["method"] == "DELETE"
    assert captured["upstream_path"] == "/api/v1/reports/rep-3"
    assert captured["audit_action"] == "resolver.report.delete"
