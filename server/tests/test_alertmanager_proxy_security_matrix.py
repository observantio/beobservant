from __future__ import annotations

import asyncio
import json
from collections import Counter
from typing import Any

import pytest
from fastapi import HTTPException
from fastapi.responses import JSONResponse
from starlette.requests import Request

from tests._env import ensure_test_env

ensure_test_env()

from models.access.auth_models import Permission, Role, TokenData
from routers.observability import alertmanager_router


def _user(*, permissions: list[str], user_id: str = "u1") -> TokenData:
    return TokenData(
        user_id=user_id,
        username=f"user-{user_id}",
        tenant_id="tenant-a",
        org_id="tenant-a",
        role=Role.USER,
        permissions=permissions,
        group_ids=["g1"],
        is_superuser=False,
        is_mfa_setup=False,
    )


def _request(
    *,
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
) -> Request:
    headers = [(b"content-type", b"application/json")] if body is not None else []
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": method,
        "path": f"/api/alertmanager/{path}",
        "headers": headers,
        "client": ("127.0.0.1", 12345),
        "scheme": "http",
        "query_string": b"",
    }
    request = Request(scope)
    request._body = json.dumps(body or {}).encode("utf-8")
    return request


PATH_CASES: list[dict[str, Any]] = [
    # Incidents
    {"name": "incidents.list", "method": "GET", "path": "incidents", "perm": Permission.READ_INCIDENTS.value},
    {"name": "incidents.patch", "method": "PATCH", "path": "incidents/inc-1", "perm": Permission.UPDATE_INCIDENTS.value, "body": {"note": "n"}},
    # Silences
    {"name": "silences.list", "method": "GET", "path": "silences", "perm": Permission.READ_SILENCES.value},
    {"name": "silences.create", "method": "POST", "path": "silences", "perm": Permission.CREATE_SILENCES.value, "body": {"visibility": "private"}},
    {"name": "silences.update", "method": "PUT", "path": "silences/s-1", "perm": Permission.UPDATE_SILENCES.value, "body": {"comment": "update", "visibility": "private"}},
    {"name": "silences.delete", "method": "DELETE", "path": "silences/s-1", "perm": Permission.DELETE_SILENCES.value},
    # Rules
    {"name": "rules.list", "method": "GET", "path": "rules", "perm": Permission.READ_RULES.value},
    {"name": "rules.import", "method": "POST", "path": "rules/import", "perm": Permission.CREATE_RULES.value, "body": {"yamlContent": "groups: []", "dryRun": True}},
    {"name": "rules.create", "method": "POST", "path": "rules", "perm": Permission.CREATE_RULES.value, "body": {"name": "r", "expr": "up == 0"}},
    {"name": "rules.update", "method": "PUT", "path": "rules/r-1", "perm": Permission.UPDATE_RULES.value, "body": {"name": "r", "expr": "up == 1"}},
    {"name": "rules.delete", "method": "DELETE", "path": "rules/r-1", "perm": Permission.DELETE_RULES.value},
    {"name": "rules.test", "method": "POST", "path": "rules/r-1/test", "perm": Permission.TEST_RULES.value, "body": {"labels": {}}},
    # Channels
    {"name": "channels.list", "method": "GET", "path": "channels", "perm": Permission.READ_CHANNELS.value},
    {"name": "channels.create", "method": "POST", "path": "channels", "perm": Permission.CREATE_CHANNELS.value, "body": {"name": "c"}},
    {"name": "channels.update", "method": "PUT", "path": "channels/c-1", "perm": Permission.UPDATE_CHANNELS.value, "body": {"name": "c2"}},
    {"name": "channels.delete", "method": "DELETE", "path": "channels/c-1", "perm": Permission.DELETE_CHANNELS.value},
    {"name": "channels.test", "method": "POST", "path": "channels/c-1/test", "perm": Permission.TEST_CHANNELS.value, "body": {"sample": True}},
    # Jira / integrations
    {"name": "jira.config.get", "method": "GET", "path": "jira/config", "perm": Permission.MANAGE_TENANTS.value},
    {"name": "jira.config.put", "method": "PUT", "path": "jira/config", "perm": Permission.MANAGE_TENANTS.value, "body": {"enabled": False}},
    {"name": "jira.integrations.list", "method": "GET", "path": "integrations/jira", "perm": Permission.READ_INCIDENTS.value},
    {"name": "jira.integrations.create", "method": "POST", "path": "integrations/jira", "perm": Permission.UPDATE_INCIDENTS.value, "body": {"name": "j1", "baseUrl": "https://jira.example.com"}},
    {"name": "jira.integrations.update", "method": "PUT", "path": "integrations/jira/j-1", "perm": Permission.UPDATE_INCIDENTS.value, "body": {"name": "j2", "baseUrl": "https://jira.example.com"}},
    {"name": "jira.integrations.delete", "method": "DELETE", "path": "integrations/jira/j-1", "perm": Permission.UPDATE_INCIDENTS.value},
    {"name": "jira.projects.by.integration", "method": "GET", "path": "integrations/jira/j-1/projects", "perm": Permission.READ_INCIDENTS.value},
    {"name": "jira.issue-types.by.integration", "method": "GET", "path": "integrations/jira/j-1/projects/OBS/issue-types", "perm": Permission.READ_INCIDENTS.value},
    {"name": "jira.projects", "method": "GET", "path": "jira/projects", "perm": Permission.READ_INCIDENTS.value},
    {"name": "jira.issue-types", "method": "GET", "path": "jira/projects/OBS/issue-types", "perm": Permission.READ_INCIDENTS.value},
    {"name": "incidents.jira.create", "method": "POST", "path": "incidents/inc-1/jira", "perm": Permission.UPDATE_INCIDENTS.value, "body": {"projectKey": "OBS", "summary": "x"}},
    {"name": "incidents.jira.comments.list", "method": "GET", "path": "incidents/inc-1/jira/comments", "perm": Permission.READ_INCIDENTS.value},
    {"name": "incidents.jira.comments.sync", "method": "POST", "path": "incidents/inc-1/jira/sync-comments", "perm": Permission.UPDATE_INCIDENTS.value, "body": {}},
    {"name": "incidents.jira.comments.create", "method": "POST", "path": "incidents/inc-1/jira/comments", "perm": Permission.UPDATE_INCIDENTS.value, "body": {"comment": "hello"}},
]

_MUTATING = {"POST", "PUT", "PATCH", "DELETE"}


@pytest.mark.asyncio
@pytest.mark.parametrize("case", PATH_CASES, ids=[c["name"] for c in PATH_CASES])
async def test_alertmanager_proxy_endpoint_matrix_enforces_permissions_and_api_key(monkeypatch, case):
    forwarded: list[dict[str, Any]] = []

    async def _forward(*, request, upstream_path, current_user, require_api_key, audit_action):
        forwarded.append(
            {
                "upstream_path": upstream_path,
                "current_user": current_user,
                "require_api_key": require_api_key,
                "audit_action": audit_action,
            }
        )
        return JSONResponse({"ok": True, "path": upstream_path})

    async def _fake_find_silence_for_mutation(*, request, current_user, silence_id):
        return {"id": silence_id, "created_by": current_user.user_id}

    monkeypatch.setattr(alertmanager_router, "apply_scoped_rate_limit", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(alertmanager_router.benotified_proxy_service, "forward", _forward)
    monkeypatch.setattr(alertmanager_router, "_find_silence_for_mutation", _fake_find_silence_for_mutation)

    user = _user(permissions=[case["perm"]])
    req = _request(method=case["method"], path=case["path"], body=case.get("body"))

    resp = await alertmanager_router.alertmanager_proxy(case["path"], req, user)
    assert resp.status_code == 200
    assert len(forwarded) == 1
    assert forwarded[0]["upstream_path"] == f"/internal/v1/api/alertmanager/{case['path']}"
    assert forwarded[0]["current_user"].tenant_id == "tenant-a"
    assert forwarded[0]["require_api_key"] is (case["method"] in _MUTATING)

    denied_user = _user(permissions=[])
    denied_req = _request(method=case["method"], path=case["path"], body=case.get("body"))
    with pytest.raises(HTTPException) as exc:
        await alertmanager_router.alertmanager_proxy(case["path"], denied_req, denied_user)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_alertmanager_proxy_concurrent_burst_across_all_endpoint_families(monkeypatch):
    forwarded: list[tuple[str, str, bool]] = []
    all_perms_user = _user(permissions=[p.value for p in Permission])

    async def _forward(*, request, upstream_path, current_user, require_api_key, audit_action):
        await asyncio.sleep(0.001)
        forwarded.append((request.method.upper(), upstream_path, require_api_key))
        return JSONResponse({"ok": True})

    async def _fake_find_silence_for_mutation(*, request, current_user, silence_id):
        await asyncio.sleep(0)
        return {"id": silence_id, "created_by": current_user.user_id}

    monkeypatch.setattr(alertmanager_router, "apply_scoped_rate_limit", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(alertmanager_router.benotified_proxy_service, "forward", _forward)
    monkeypatch.setattr(alertmanager_router, "_find_silence_for_mutation", _fake_find_silence_for_mutation)

    tasks = []
    repetitions = 4
    for _ in range(repetitions):
        for case in PATH_CASES:
            req = _request(method=case["method"], path=case["path"], body=case.get("body"))
            tasks.append(
                asyncio.create_task(
                    alertmanager_router.alertmanager_proxy(case["path"], req, all_perms_user)
                )
            )

    responses = await asyncio.gather(*tasks)
    assert len(responses) == len(PATH_CASES) * repetitions
    assert all(resp.status_code == 200 for resp in responses)
    assert len(forwarded) == len(PATH_CASES) * repetitions

    expected_counts = Counter(
        f"/internal/v1/api/alertmanager/{case['path']}" for case in PATH_CASES
    )
    for key in list(expected_counts.keys()):
        expected_counts[key] *= repetitions

    actual_counts = Counter(path for _, path, _ in forwarded)
    assert actual_counts == expected_counts

    for case in PATH_CASES:
        target = f"/internal/v1/api/alertmanager/{case['path']}"
        require_api_key_values = [
            req
            for method, path, req in forwarded
            if path == target and method == case["method"].upper()
        ]
        assert require_api_key_values
        assert all(value is (case["method"] in _MUTATING) for value in require_api_key_values)


@pytest.mark.asyncio
async def test_public_rules_proxy_enforces_public_endpoint_security(monkeypatch):
    calls: list[dict[str, Any]] = []
    forwarded: list[str] = []

    def _enforce(request, *, scope, limit, window_seconds, allowlist, fallback_mode=None):
        calls.append(
            {
                "scope": scope,
                "limit": limit,
                "window_seconds": window_seconds,
                "allowlist": allowlist,
            }
        )

    async def _forward(*, request, upstream_path, current_user, require_api_key, audit_action):
        forwarded.append(upstream_path)
        return JSONResponse({"ok": True})

    monkeypatch.setattr(alertmanager_router, "enforce_public_endpoint_security", _enforce)
    monkeypatch.setattr(alertmanager_router.benotified_proxy_service, "forward", _forward)

    req = _request(method="GET", path="public/rules")
    resp = await alertmanager_router.public_rules_proxy(req)

    assert resp.status_code == 200
    assert forwarded == ["/internal/v1/api/alertmanager/public/rules"]
    assert calls and calls[0]["scope"] == "alertmanager_public_rules"


@pytest.mark.asyncio
async def test_public_rules_proxy_denies_when_public_security_fails(monkeypatch):
    def _enforce(*_args, **_kwargs):
        raise HTTPException(status_code=403, detail="blocked")

    async def _forward(*_args, **_kwargs):
        raise AssertionError("forward should not be called when security fails")

    monkeypatch.setattr(alertmanager_router, "enforce_public_endpoint_security", _enforce)
    monkeypatch.setattr(alertmanager_router.benotified_proxy_service, "forward", _forward)

    req = _request(method="GET", path="public/rules")
    with pytest.raises(HTTPException) as exc:
        await alertmanager_router.public_rules_proxy(req)
    assert exc.value.status_code == 403
