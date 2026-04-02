"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.responses import JSONResponse

from models.access.auth_models import Permission
from routers import internal_router
from routers.observability import resolver_router
from routers.observability.grafana_router import dashboards, datasources, folders

from .helpers import WorkflowState, patch_auth_service


def _patch_grafana_folder_proxy(monkeypatch: pytest.MonkeyPatch, state: WorkflowState) -> None:
    monkeypatch.setattr(folders.proxy, "create_folder", state.create_folder)
    monkeypatch.setattr(folders.proxy, "get_folders", state.get_folders)
    monkeypatch.setattr(folders.proxy, "get_folder", state.get_folder)


def _patch_grafana_dashboard_proxy(monkeypatch: pytest.MonkeyPatch, state: WorkflowState) -> None:
    monkeypatch.setattr(dashboards, "parse_dashboard_create_payload", lambda raw: raw)
    monkeypatch.setattr(dashboards.proxy, "create_dashboard", state.create_dashboard)
    monkeypatch.setattr(dashboards.proxy, "search_dashboards", state.search_dashboards)
    monkeypatch.setattr(dashboards.proxy, "get_dashboard", state.get_dashboard)
    monkeypatch.setattr(dashboards.proxy, "build_dashboard_search_context", state.build_dashboard_search_context)


def _patch_grafana_datasource_proxy(monkeypatch: pytest.MonkeyPatch, state: WorkflowState) -> None:
    monkeypatch.setattr(datasources.proxy, "create_datasource", state.create_datasource)
    monkeypatch.setattr(datasources.proxy, "get_datasources", state.get_datasources)
    monkeypatch.setattr(datasources.proxy, "get_datasource_by_name", state.get_datasource_by_name)
    monkeypatch.setattr(datasources.proxy, "build_datasource_list_context", state.build_datasource_list_context)


def _patch_resolver_proxy(monkeypatch: pytest.MonkeyPatch, calls: list[dict[str, Any]]) -> None:
    async def fake_request_json(**kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs)
        path = kwargs["upstream_path"]
        if path == "/api/v1/jobs/analyze":
            return {
                "job_id": "job-1",
                "report_id": "report-1",
                "status": "accepted",
                "created_at": "2024-01-01T00:00:00Z",
                "tenant_id": kwargs["payload"]["tenant_id"],
                "requested_by": kwargs["current_user"].user_id,
            }
        if path == "/api/v1/jobs":
            return {
                "items": [
                    {
                        "job_id": "job-1",
                        "report_id": "report-1",
                        "status": "running",
                        "created_at": "2024-01-01T00:00:00Z",
                        "tenant_id": kwargs["tenant_id"],
                        "requested_by": kwargs["current_user"].user_id,
                    }
                ],
                "next_cursor": None,
            }
        if path == "/api/v1/reports/report-1":
            if kwargs["method"] == "DELETE":
                return {
                    "report_id": "report-1",
                    "status": "deleted",
                    "deleted": True,
                }
            return {
                "job_id": "job-1",
                "report_id": "report-1",
                "status": "completed",
                "tenant_id": kwargs["tenant_id"],
                "requested_by": kwargs["current_user"].user_id,
                "result": {"summary": "ok"},
            }
        return {"ok": True}

    monkeypatch.setattr(resolver_router.resolver_proxy_service, "request_json", fake_request_json)


def test_ready_not_ready_when_upstream_is_down_workflow(client, monkeypatch: pytest.MonkeyPatch) -> None:
    state = WorkflowState()
    patch_auth_service(monkeypatch, state)

    ready_endpoint = next(
        route.endpoint
        for route in client.app.routes
        if getattr(route, "path", None) == "/ready" and "GET" in getattr(route, "methods", set())
    )

    monkeypatch.setitem(ready_endpoint.__globals__, "connection_test", lambda: True)

    async def _always_unreachable(_url: str) -> bool:
        return False

    monkeypatch.setitem(ready_endpoint.__globals__, "_upstream_reachable", _always_unreachable)

    ready_response = client.get("/ready")
    assert ready_response.status_code == 503
    assert ready_response.json()["status"] == "not_ready"


def test_internal_otlp_validation_rejects_invalid_service_token_workflow(client, monkeypatch: pytest.MonkeyPatch) -> None:
    state = WorkflowState()
    patch_auth_service(monkeypatch, state)

    monkeypatch.setattr(internal_router.internal_service, "_get_internal_token", lambda: "expected-token")
    monkeypatch.setattr(internal_router.internal_service._auth_service, "validate_otlp_token", state.validate_otlp_token)

    key = state.create_api_key("u-admin", state.tenant_id, SimpleNamespace(name="gateway", key="scope-gateway"))

    denied = client.post(
        "/api/internal/otlp/validate",
        headers={"X-Internal-Token": "wrong-token"},
        json={"token": key.otlp_token},
    )
    assert denied.status_code == 403


def test_deleted_user_token_cannot_access_profile_workflow(client, monkeypatch: pytest.MonkeyPatch) -> None:
    state = WorkflowState()
    patch_auth_service(monkeypatch, state)
    admin_headers = state.auth_header("token-u-admin")

    created_user = client.post(
        "/api/auth/users",
        headers=admin_headers,
        json={"username": "temp-user", "email": "temp-user@example.com", "password": "password123"},
    )
    assert created_user.status_code == 200
    user_id = created_user.json()["id"]
    user_headers = state.auth_header(f"token-{user_id}")

    assert client.get("/api/auth/me", headers=user_headers).status_code == 200

    delete_response = client.delete(f"/api/auth/users/{user_id}", headers=admin_headers)
    assert delete_response.status_code == 200

    profile_after_delete = client.get("/api/auth/me", headers=user_headers)
    assert profile_after_delete.status_code == 401


def test_group_deletion_revokes_group_shared_api_key_access_workflow(client, monkeypatch: pytest.MonkeyPatch) -> None:
    state = WorkflowState()
    patch_auth_service(monkeypatch, state)
    admin_headers = state.auth_header("token-u-admin")

    group_response = client.post(
        "/api/auth/groups",
        headers=admin_headers,
        json={"name": "share-group-delete", "description": "Share revocation via group delete"},
    )
    assert group_response.status_code == 200
    group_id = group_response.json()["id"]

    user_response = client.post(
        "/api/auth/users",
        headers=admin_headers,
        json={"username": "group-member", "email": "group-member@example.com", "password": "password123"},
    )
    assert user_response.status_code == 200
    user_id = user_response.json()["id"]
    user_headers = state.auth_header(f"token-{user_id}")

    add_member = client.put(
        f"/api/auth/groups/{group_id}/members",
        headers=admin_headers,
        json={"user_ids": [user_id]},
    )
    assert add_member.status_code == 200

    key_response = client.post(
        "/api/auth/api-keys",
        headers=admin_headers,
        json={"name": "group-shared", "key": "scope-group-shared"},
    )
    assert key_response.status_code == 200
    key_id = key_response.json()["id"]

    share_response = client.put(
        f"/api/auth/api-keys/{key_id}/shares",
        headers=admin_headers,
        json={"user_ids": [], "group_ids": [group_id]},
    )
    assert share_response.status_code == 200

    before_delete = client.get("/api/auth/api-keys", headers=user_headers)
    assert before_delete.status_code == 200
    assert {item["id"] for item in before_delete.json()} == {key_id}

    delete_group_response = client.delete(f"/api/auth/groups/{group_id}", headers=admin_headers)
    assert delete_group_response.status_code == 204

    after_delete = client.get("/api/auth/api-keys", headers=user_headers)
    assert after_delete.status_code == 200
    assert after_delete.json() == []


def test_group_deletion_revokes_group_folder_access_workflow(client, monkeypatch: pytest.MonkeyPatch) -> None:
    state = WorkflowState()
    patch_auth_service(monkeypatch, state)
    _patch_grafana_folder_proxy(monkeypatch, state)
    admin_headers = state.auth_header("token-u-admin")

    group_response = client.post(
        "/api/auth/groups",
        headers=admin_headers,
        json={"name": "folder-group-delete", "description": "Folder visibility revocation"},
    )
    assert group_response.status_code == 200
    group_id = group_response.json()["id"]

    user_response = client.post(
        "/api/auth/users",
        headers=admin_headers,
        json={"username": "folder-member", "email": "folder-member@example.com", "password": "password123"},
    )
    assert user_response.status_code == 200
    user_id = user_response.json()["id"]
    user_headers = state.auth_header(f"token-{user_id}")

    permission_response = client.put(
        f"/api/auth/users/{user_id}/permissions",
        headers=admin_headers,
        json=[Permission.READ_FOLDERS.value],
    )
    assert permission_response.status_code == 200

    add_member = client.put(
        f"/api/auth/groups/{group_id}/members",
        headers=admin_headers,
        json={"user_ids": [user_id]},
    )
    assert add_member.status_code == 200

    folder_response = client.post(
        f"/api/grafana/folders?visibility=group&shared_group_ids={group_id}",
        headers=admin_headers,
        json={"title": "Group Folder", "allowDashboardWrites": True},
    )
    assert folder_response.status_code == 200
    folder_uid = folder_response.json()["uid"]

    before_delete = client.get("/api/grafana/folders", headers=user_headers)
    assert before_delete.status_code == 200
    assert any(item["uid"] == folder_uid for item in before_delete.json())

    delete_group_response = client.delete(f"/api/auth/groups/{group_id}", headers=admin_headers)
    assert delete_group_response.status_code == 204

    after_delete = client.get("/api/grafana/folders", headers=user_headers)
    assert after_delete.status_code == 200
    assert all(item["uid"] != folder_uid for item in after_delete.json())

    direct_get_after_delete = client.get(f"/api/grafana/folders/{folder_uid}", headers=user_headers)
    assert direct_get_after_delete.status_code == 404


def test_group_deletion_revokes_group_dashboard_access_workflow(client, monkeypatch: pytest.MonkeyPatch) -> None:
    state = WorkflowState()
    patch_auth_service(monkeypatch, state)
    _patch_grafana_dashboard_proxy(monkeypatch, state)
    admin_headers = state.auth_header("token-u-admin")

    group_response = client.post(
        "/api/auth/groups",
        headers=admin_headers,
        json={"name": "dashboard-group-delete", "description": "Dashboard visibility revocation"},
    )
    assert group_response.status_code == 200
    group_id = group_response.json()["id"]

    user_response = client.post(
        "/api/auth/users",
        headers=admin_headers,
        json={"username": "dash-member", "email": "dash-member@example.com", "password": "password123"},
    )
    assert user_response.status_code == 200
    user_id = user_response.json()["id"]
    user_headers = state.auth_header(f"token-{user_id}")

    permission_response = client.put(
        f"/api/auth/users/{user_id}/permissions",
        headers=admin_headers,
        json=[Permission.READ_DASHBOARDS.value],
    )
    assert permission_response.status_code == 200

    add_member = client.put(
        f"/api/auth/groups/{group_id}/members",
        headers=admin_headers,
        json={"user_ids": [user_id]},
    )
    assert add_member.status_code == 200

    dashboard_response = client.post(
        f"/api/grafana/dashboards?visibility=group&shared_group_ids={group_id}",
        headers=admin_headers,
        json={"dashboard": {"uid": "dash-group-delete", "title": "Group Dashboard"}},
    )
    assert dashboard_response.status_code == 200

    before_delete = client.get("/api/grafana/dashboards/search", headers=user_headers)
    assert before_delete.status_code == 200
    assert any(item["uid"] == "dash-group-delete" for item in before_delete.json())

    delete_group_response = client.delete(f"/api/auth/groups/{group_id}", headers=admin_headers)
    assert delete_group_response.status_code == 204

    after_delete = client.get("/api/grafana/dashboards/search", headers=user_headers)
    assert after_delete.status_code == 200
    assert all(item["uid"] != "dash-group-delete" for item in after_delete.json())

    direct_get_after_delete = client.get("/api/grafana/dashboards/dash-group-delete", headers=user_headers)
    assert direct_get_after_delete.status_code == 404


def test_group_deletion_revokes_group_datasource_access_workflow(client, monkeypatch: pytest.MonkeyPatch) -> None:
    state = WorkflowState()
    patch_auth_service(monkeypatch, state)
    _patch_grafana_datasource_proxy(monkeypatch, state)
    admin_headers = state.auth_header("token-u-admin")

    group_response = client.post(
        "/api/auth/groups",
        headers=admin_headers,
        json={"name": "datasource-group-delete", "description": "Datasource visibility revocation"},
    )
    assert group_response.status_code == 200
    group_id = group_response.json()["id"]

    user_response = client.post(
        "/api/auth/users",
        headers=admin_headers,
        json={"username": "ds-member", "email": "ds-member@example.com", "password": "password123"},
    )
    assert user_response.status_code == 200
    user_id = user_response.json()["id"]
    user_headers = state.auth_header(f"token-{user_id}")

    permission_response = client.put(
        f"/api/auth/users/{user_id}/permissions",
        headers=admin_headers,
        json=[Permission.READ_DATASOURCES.value],
    )
    assert permission_response.status_code == 200

    add_member = client.put(
        f"/api/auth/groups/{group_id}/members",
        headers=admin_headers,
        json={"user_ids": [user_id]},
    )
    assert add_member.status_code == 200

    datasource_response = client.post(
        f"/api/grafana/datasources?visibility=group&shared_group_ids={group_id}",
        headers=admin_headers,
        json={"name": "group-ds-delete", "type": "tempo", "url": "http://tempo-group"},
    )
    assert datasource_response.status_code == 200
    datasource_uid = datasource_response.json()["uid"]

    before_delete = client.get("/api/grafana/datasources/name/group-ds-delete", headers=user_headers)
    assert before_delete.status_code == 200

    delete_group_response = client.delete(f"/api/auth/groups/{group_id}", headers=admin_headers)
    assert delete_group_response.status_code == 204

    after_delete_by_name = client.get("/api/grafana/datasources/name/group-ds-delete", headers=user_headers)
    assert after_delete_by_name.status_code == 404

    after_delete_list = client.get("/api/grafana/datasources", headers=user_headers)
    assert after_delete_list.status_code == 200
    assert all(item["uid"] != datasource_uid for item in after_delete_list.json())


def test_resolver_create_job_requires_create_rca_permission_workflow(client, monkeypatch: pytest.MonkeyPatch) -> None:
    state = WorkflowState()
    patch_auth_service(monkeypatch, state)
    resolver_calls: list[dict[str, Any]] = []
    _patch_resolver_proxy(monkeypatch, resolver_calls)
    admin_headers = state.auth_header("token-u-admin")

    user_response = client.post(
        "/api/auth/users",
        headers=admin_headers,
        json={"username": "resolver-create", "email": "resolver-create@example.com", "password": "password123"},
    )
    assert user_response.status_code == 200
    user_id = user_response.json()["id"]
    user_headers = state.auth_header(f"token-{user_id}")

    set_none_permissions = client.put(
        f"/api/auth/users/{user_id}/permissions",
        headers=admin_headers,
        json=[],
    )
    assert set_none_permissions.status_code == 200

    denied_create = client.post(
        "/api/resolver/analyze/jobs",
        headers=user_headers,
        json={"start": 1, "end": 2, "services": ["checkout"], "log_query": "{service=\"checkout\"}"},
    )
    assert denied_create.status_code == 403

    set_create_permission = client.put(
        f"/api/auth/users/{user_id}/permissions",
        headers=admin_headers,
        json=[Permission.CREATE_RCA.value],
    )
    assert set_create_permission.status_code == 200

    allowed_create = client.post(
        "/api/resolver/analyze/jobs",
        headers=user_headers,
        json={"start": 1, "end": 2, "services": ["checkout"], "log_query": "{service=\"checkout\"}"},
    )
    assert allowed_create.status_code == 202
    assert allowed_create.json()["job_id"] == "job-1"
    assert any(call["upstream_path"] == "/api/v1/jobs/analyze" for call in resolver_calls)


def test_resolver_read_jobs_requires_read_rca_permission_workflow(client, monkeypatch: pytest.MonkeyPatch) -> None:
    state = WorkflowState()
    patch_auth_service(monkeypatch, state)
    resolver_calls: list[dict[str, Any]] = []
    _patch_resolver_proxy(monkeypatch, resolver_calls)
    admin_headers = state.auth_header("token-u-admin")

    user_response = client.post(
        "/api/auth/users",
        headers=admin_headers,
        json={"username": "resolver-read", "email": "resolver-read@example.com", "password": "password123"},
    )
    assert user_response.status_code == 200
    user_id = user_response.json()["id"]
    user_headers = state.auth_header(f"token-{user_id}")

    set_create_only_permissions = client.put(
        f"/api/auth/users/{user_id}/permissions",
        headers=admin_headers,
        json=[Permission.CREATE_RCA.value],
    )
    assert set_create_only_permissions.status_code == 200

    create_job = client.post(
        "/api/resolver/analyze/jobs",
        headers=user_headers,
        json={"start": 1, "end": 2, "services": ["checkout"], "log_query": "{service=\"checkout\"}"},
    )
    assert create_job.status_code == 202

    denied_list = client.get("/api/resolver/analyze/jobs", headers=user_headers)
    assert denied_list.status_code == 403

    set_create_and_read_permissions = client.put(
        f"/api/auth/users/{user_id}/permissions",
        headers=admin_headers,
        json=[Permission.CREATE_RCA.value, Permission.READ_RCA.value],
    )
    assert set_create_and_read_permissions.status_code == 200

    allowed_list = client.get("/api/resolver/analyze/jobs", headers=user_headers)
    assert allowed_list.status_code == 200
    assert allowed_list.json()["items"][0]["job_id"] == "job-1"


def test_resolver_delete_report_requires_delete_rca_permission_workflow(client, monkeypatch: pytest.MonkeyPatch) -> None:
    state = WorkflowState()
    patch_auth_service(monkeypatch, state)
    resolver_calls: list[dict[str, Any]] = []
    _patch_resolver_proxy(monkeypatch, resolver_calls)
    admin_headers = state.auth_header("token-u-admin")

    user_response = client.post(
        "/api/auth/users",
        headers=admin_headers,
        json={"username": "resolver-delete", "email": "resolver-delete@example.com", "password": "password123"},
    )
    assert user_response.status_code == 200
    user_id = user_response.json()["id"]
    user_headers = state.auth_header(f"token-{user_id}")

    set_read_only_permissions = client.put(
        f"/api/auth/users/{user_id}/permissions",
        headers=admin_headers,
        json=[Permission.READ_RCA.value],
    )
    assert set_read_only_permissions.status_code == 200

    denied_delete = client.delete("/api/resolver/reports/report-1", headers=user_headers)
    assert denied_delete.status_code == 403

    set_read_and_delete_permissions = client.put(
        f"/api/auth/users/{user_id}/permissions",
        headers=admin_headers,
        json=[Permission.READ_RCA.value, Permission.DELETE_RCA.value],
    )
    assert set_read_and_delete_permissions.status_code == 200

    allowed_delete = client.delete("/api/resolver/reports/report-1", headers=user_headers)
    assert allowed_delete.status_code == 200
    assert allowed_delete.json()["deleted"] is True
    assert any(call["upstream_path"] == "/api/v1/reports/report-1" and call["method"] == "DELETE" for call in resolver_calls)
