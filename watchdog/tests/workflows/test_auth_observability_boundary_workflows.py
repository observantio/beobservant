"""
Copyright (c) 2026 Stefan Kumarasinghe.

Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the
License. You may obtain a copy of the License at
http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.responses import JSONResponse
from routers import internal_router
from routers.observability import alertmanager_router


def _call(
    client: Any,
    method: str,
    path: str,
    *,
    headers: dict[str, str] | None = None,
    json: dict[str, Any] | list[Any] | None = None,
    params: dict[str, Any] | None = None,
) -> Any:
    fn = getattr(client, method.lower())
    kwargs: dict[str, Any] = {}
    if headers is not None:
        kwargs["headers"] = headers
    if json is not None:
        kwargs["json"] = json
    if params is not None:
        kwargs["params"] = params
    return fn(path, **kwargs)


NO_AUTH_CASES: list[tuple[str, str, str, dict[str, Any] | list[Any] | None, dict[str, Any] | None, int]] = [
    ("auth_me", "GET", "/api/auth/me", None, None, 401),
    ("auth_me_update", "PUT", "/api/auth/me", {"full_name": "X"}, None, 401),
    ("auth_logout", "POST", "/api/auth/logout", None, None, 200),
    ("auth_users_list", "GET", "/api/auth/users", None, None, 401),
    (
        "auth_user_create",
        "POST",
        "/api/auth/users",
        {"username": "u", "email": "u@example.com", "password": "password123"},
        None,
        401,
    ),
    ("auth_user_update", "PUT", "/api/auth/users/u-2", {"full_name": "Changed"}, None, 401),
    ("auth_user_delete", "DELETE", "/api/auth/users/u-2", None, None, 401),
    ("auth_permissions", "GET", "/api/auth/permissions", None, None, 401),
    ("auth_role_defaults", "GET", "/api/auth/role-defaults", None, None, 401),
    ("auth_groups_list", "GET", "/api/auth/groups", None, None, 401),
    ("auth_group_create", "POST", "/api/auth/groups", {"name": "g", "description": "d"}, None, 401),
    ("auth_group_get", "GET", "/api/auth/groups/g-1", None, None, 401),
    ("auth_group_update", "PUT", "/api/auth/groups/g-1", {"description": "new"}, None, 401),
    ("auth_group_delete", "DELETE", "/api/auth/groups/g-1", None, None, 401),
    ("auth_group_members", "PUT", "/api/auth/groups/g-1/members", {"user_ids": []}, None, 401),
    ("auth_group_permissions", "PUT", "/api/auth/groups/g-1/permissions", ["read:logs"], None, 401),
    ("auth_keys_list", "GET", "/api/auth/api-keys", None, None, 401),
    ("auth_key_create", "POST", "/api/auth/api-keys", {"name": "k", "key": "scope-k"}, None, 401),
    ("auth_key_update", "PATCH", "/api/auth/api-keys/key-1", {"name": "k2"}, None, 401),
    ("auth_key_delete", "DELETE", "/api/auth/api-keys/key-1", None, None, 401),
    ("auth_key_rotate", "POST", "/api/auth/api-keys/key-1/otlp-token/regenerate", None, None, 401),
    ("auth_key_shares_list", "GET", "/api/auth/api-keys/key-1/shares", None, None, 401),
    ("auth_key_shares_put", "PUT", "/api/auth/api-keys/key-1/shares", {"user_ids": [], "group_ids": []}, None, 401),
    ("auth_key_shares_delete", "DELETE", "/api/auth/api-keys/key-1/shares/u-2", None, None, 401),
    ("auth_key_hide", "POST", "/api/auth/api-keys/key-1/hide", {"hidden": True}, None, 401),
    ("auth_audit_list", "GET", "/api/auth/audit-logs", None, None, 401),
    ("auth_audit_export", "GET", "/api/auth/audit-logs/export", None, None, 401),
    ("system_metrics", "GET", "/api/system/metrics", None, None, 401),
    ("system_quotas", "GET", "/api/system/quotas", None, None, 401),
    ("grafana_auth", "GET", "/api/grafana/auth", None, {"token": "token-u-admin", "orig": "/grafana"}, 401),
    ("grafana_bootstrap", "POST", "/api/grafana/bootstrap-session", {"next": "/"}, None, 401),
    ("grafana_folders", "GET", "/api/grafana/folders", None, None, 401),
    ("grafana_dashboards", "GET", "/api/grafana/dashboards/search", None, None, 401),
    ("grafana_datasources", "GET", "/api/grafana/datasources", None, None, 401),
    ("loki_query", "GET", "/api/loki/query", None, {"query": '{service="api"}'}, 401),
    ("loki_labels", "GET", "/api/loki/labels", None, None, 401),
    ("tempo_search", "GET", "/api/tempo/traces/search", None, None, 401),
    ("tempo_services", "GET", "/api/tempo/services", None, None, 401),
    (
        "resolver_jobs_create",
        "POST",
        "/api/resolver/analyze/jobs",
        {"start": 1, "end": 2, "services": ["api"], "log_query": '{service="api"}'},
        None,
        401,
    ),
    ("resolver_jobs_list", "GET", "/api/resolver/analyze/jobs", None, None, 401),
    ("resolver_report_get", "GET", "/api/resolver/reports/report-1", None, None, 401),
    ("resolver_report_delete", "DELETE", "/api/resolver/reports/report-1", None, None, 401),
    ("alertmanager_rules", "GET", "/api/alertmanager/rules", None, None, 401),
    ("alertmanager_rule_create", "POST", "/api/alertmanager/rules", {"name": "r", "expr": "up == 0"}, None, 401),
    ("alertmanager_channels", "GET", "/api/alertmanager/channels", None, None, 401),
    (
        "alertmanager_channel_create",
        "POST",
        "/api/alertmanager/channels",
        {"name": "c", "type": "email", "config": {}},
        None,
        401,
    ),
    ("alertmanager_silences", "GET", "/api/alertmanager/silences", None, None, 401),
    (
        "alertmanager_silence_create",
        "POST",
        "/api/alertmanager/silences",
        {"id": "sil-1", "visibility": "private"},
        None,
        401,
    ),
    ("alertmanager_incidents", "GET", "/api/alertmanager/incidents", None, None, 401),
    (
        "alertmanager_incident_patch",
        "PATCH",
        "/api/alertmanager/incidents/inc-1",
        {"status": "acknowledged"},
        None,
        401,
    ),
]


INVALID_TOKEN_CASES: list[tuple[str, str, str, dict[str, Any] | list[Any] | None, dict[str, Any] | None, int]] = [
    ("invalid_auth_me", "GET", "/api/auth/me", None, None, 401),
    ("invalid_auth_users", "GET", "/api/auth/users", None, None, 401),
    ("invalid_auth_groups", "GET", "/api/auth/groups", None, None, 401),
    ("invalid_auth_keys", "GET", "/api/auth/api-keys", None, None, 401),
    ("invalid_auth_audit", "GET", "/api/auth/audit-logs", None, None, 401),
    ("invalid_system_metrics", "GET", "/api/system/metrics", None, None, 401),
    ("invalid_system_quotas", "GET", "/api/system/quotas", None, None, 401),
    ("invalid_grafana_folders", "GET", "/api/grafana/folders", None, None, 401),
    ("invalid_grafana_dashboards", "GET", "/api/grafana/dashboards/search", None, None, 401),
    ("invalid_grafana_datasources", "GET", "/api/grafana/datasources", None, None, 401),
    ("invalid_loki_query", "GET", "/api/loki/query", None, {"query": '{service="api"}'}, 401),
    ("invalid_loki_labels", "GET", "/api/loki/labels", None, None, 401),
    ("invalid_tempo_search", "GET", "/api/tempo/traces/search", None, None, 401),
    ("invalid_tempo_services", "GET", "/api/tempo/services", None, None, 401),
    ("invalid_resolver_jobs", "GET", "/api/resolver/analyze/jobs", None, None, 401),
    (
        "invalid_resolver_create",
        "POST",
        "/api/resolver/analyze/jobs",
        {"start": 1, "end": 2, "services": ["api"], "log_query": '{service="api"}'},
        None,
        401,
    ),
    ("invalid_resolver_report", "GET", "/api/resolver/reports/report-1", None, None, 401),
    ("invalid_alert_rules", "GET", "/api/alertmanager/rules", None, None, 401),
    ("invalid_alert_channels", "GET", "/api/alertmanager/channels", None, None, 401),
    ("invalid_alert_silences", "GET", "/api/alertmanager/silences", None, None, 401),
    ("invalid_alert_incidents", "GET", "/api/alertmanager/incidents", None, None, 401),
    ("invalid_alert_incident_patch", "PATCH", "/api/alertmanager/incidents/inc-1", {"status": "open"}, None, 401),
    (
        "invalid_alert_channel_create",
        "POST",
        "/api/alertmanager/channels",
        {"name": "c", "type": "email", "config": {}},
        None,
        401,
    ),
    ("invalid_alert_rule_create", "POST", "/api/alertmanager/rules", {"name": "r", "expr": "up == 0"}, None, 401),
    (
        "invalid_alert_silence_create",
        "POST",
        "/api/alertmanager/silences",
        {"id": "sil-invalid", "visibility": "private"},
        None,
        401,
    ),
]


INTERNAL_AND_PUBLIC_CASES: list[
    tuple[str, str, str, dict[str, str] | None, dict[str, Any] | list[Any] | None, dict[str, Any] | None, int]
] = [
    ("health_is_public", "GET", "/health", None, None, None, 200),
    ("root_is_public", "GET", "/", None, None, None, 200),
    ("alert_public_rules", "GET", "/api/alertmanager/public/rules", None, None, None, 200),
    ("internal_missing_header", "POST", "/api/internal/otlp/validate", None, {"token": "x"}, None, 422),
    (
        "internal_wrong_header",
        "POST",
        "/api/internal/otlp/validate",
        {"X-Internal-Token": "wrong"},
        {"token": "x"},
        None,
        403,
    ),
    (
        "internal_empty_payload_token",
        "POST",
        "/api/internal/otlp/validate",
        {"X-Internal-Token": "wrong"},
        {"token": ""},
        None,
        403,
    ),
    (
        "internal_whitespace_payload_token",
        "POST",
        "/api/internal/otlp/validate",
        {"X-Internal-Token": "wrong"},
        {"token": "   "},
        None,
        403,
    ),
    ("internal_query_missing_header", "GET", "/api/internal/otlp/validate", None, None, {"token": "x"}, 422),
    (
        "internal_query_wrong_header",
        "GET",
        "/api/internal/otlp/validate",
        {"X-Internal-Token": "wrong"},
        None,
        {"token": "x"},
        403,
    ),
    ("ready_endpoint", "GET", "/ready", None, None, None, 200),
    ("auth_mode_public", "GET", "/api/auth/mode", None, None, None, 200),
    ("auth_login_bad_payload", "POST", "/api/auth/login", None, {"username": "unknown"}, None, 422),
    ("auth_register_missing_fields", "POST", "/api/auth/register", None, {"username": "a"}, None, 422),
    (
        "oidc_authorize_without_oidc",
        "POST",
        "/api/auth/oidc/authorize-url",
        None,
        {"redirect_uri": "https://app.example.com/cb", "state": "s"},
        None,
        400,
    ),
    (
        "oidc_exchange_without_oidc",
        "POST",
        "/api/auth/oidc/exchange",
        None,
        {"code": "c", "redirect_uri": "https://app.example.com/cb"},
        None,
        400,
    ),
]


@pytest.mark.parametrize(
    "case_id,method,path,payload,params,expected_status",
    NO_AUTH_CASES,
    ids=[case[0] for case in NO_AUTH_CASES],
)
def test_workflow_no_auth_protected_matrix(
    client,
    case_id: str,
    method: str,
    path: str,
    payload: dict[str, Any] | list[Any] | None,
    params: dict[str, Any] | None,
    expected_status: int,
) -> None:
    del case_id
    response = _call(client, method, path, json=payload, params=params)
    assert response.status_code == expected_status


@pytest.mark.parametrize(
    "case_id,method,path,payload,params,expected_status",
    INVALID_TOKEN_CASES,
    ids=[case[0] for case in INVALID_TOKEN_CASES],
)
def test_workflow_invalid_token_matrix(
    client,
    case_id: str,
    method: str,
    path: str,
    payload: dict[str, Any] | list[Any] | None,
    params: dict[str, Any] | None,
    expected_status: int,
) -> None:
    del case_id
    headers = {"Authorization": "Bearer token-does-not-exist"}
    response = _call(client, method, path, headers=headers, json=payload, params=params)
    assert response.status_code == expected_status


@pytest.mark.parametrize(
    "case_id,method,path,headers,payload,params,expected_status",
    INTERNAL_AND_PUBLIC_CASES,
    ids=[case[0] for case in INTERNAL_AND_PUBLIC_CASES],
)
def test_workflow_public_and_internal_boundary_matrix(
    client,
    monkeypatch: pytest.MonkeyPatch,
    case_id: str,
    method: str,
    path: str,
    headers: dict[str, str] | None,
    payload: dict[str, Any] | list[Any] | None,
    params: dict[str, Any] | None,
    expected_status: int,
) -> None:
    # Normalize environmental dependencies for endpoints that rely on internal secrets
    # or external upstreams so status assertions are deterministic.
    monkeypatch.setattr(internal_router.internal_service, "_get_internal_token", lambda: "expected-token")
    monkeypatch.setattr(
        internal_router.internal_service._auth_service, "validate_otlp_token", lambda *_args, **_kwargs: "org-x"
    )
    monkeypatch.setattr(alertmanager_router, "enforce_public_endpoint_security", lambda *args, **kwargs: None)

    async def _public_rules_forward(_fwd: object, **_kwargs: Any) -> JSONResponse:
        return JSONResponse({"groups": []})

    monkeypatch.setattr(alertmanager_router.notifier_proxy_service, "forward", _public_rules_forward)

    if case_id == "ready_endpoint":
        ready_endpoint = next(
            route.endpoint
            for route in client.app.routes
            if getattr(route, "path", None) == "/ready" and "GET" in getattr(route, "methods", set())
        )

        monkeypatch.setitem(ready_endpoint.__globals__, "connection_test", lambda: True)

        async def _always_reachable(_url: str) -> bool:
            return True

        monkeypatch.setitem(ready_endpoint.__globals__, "_upstream_reachable", _always_reachable)

    response = _call(client, method, path, headers=headers, json=payload, params=params)
    assert response.status_code == expected_status
