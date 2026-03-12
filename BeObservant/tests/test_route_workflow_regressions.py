"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from fastapi import HTTPException
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

try:
    from ._env import ensure_test_env
except ImportError:
    from tests._env import ensure_test_env

ensure_test_env()

from config import config

config.SKIP_STARTUP_DB_INIT = True

from database import get_db
from main import app
from middleware import dependencies
from models.access.auth_models import Permission, ROLE_PERMISSIONS, Role, Token, TokenData
from models.access.group_models import Group
from models.access.user_models import UserResponse
from routers.access.auth_router import authentication as auth_routes
from routers.access.auth_router import groups as group_routes
from routers.access.auth_router import users as user_routes
from routers.observability import alertmanager_router, becertain_router, loki_router, tempo_router
from routers.observability.grafana_router import dashboards, proxy as grafana_proxy_router


@dataclass
class _UserState:
    id: str
    username: str
    email: str
    full_name: str
    tenant_id: str
    org_id: str
    role: Role
    permissions: list[str]
    group_ids: list[str] = field(default_factory=list)
    is_active: bool = True
    is_superuser: bool = False
    mfa_enabled: bool = False
    must_setup_mfa: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_runtime_user(self) -> SimpleNamespace:
        return SimpleNamespace(
            id=self.id,
            username=self.username,
            email=self.email,
            full_name=self.full_name,
            tenant_id=self.tenant_id,
            org_id=self.org_id,
            role=self.role,
            group_ids=list(self.group_ids),
            is_active=self.is_active,
            is_superuser=self.is_superuser,
            mfa_enabled=self.mfa_enabled,
            must_setup_mfa=self.must_setup_mfa,
            created_at=self.created_at,
        )


class _WorkflowState:
    def __init__(self, *, admin_requires_mfa: bool) -> None:
        self.tenant_id = "tenant-a"
        self.org_id = "org-a"
        self.users: dict[str, _UserState] = {}
        self.groups: dict[str, Group] = {}
        self.tokens: dict[str, TokenData] = {}
        self.next_user_id = 2
        self.next_group_id = 1
        self.next_dashboard_id = 1
        self.dashboards: dict[str, dict[str, Any]] = {}
        self._add_user(
            user_id="u-admin",
            username="admin",
            email="admin@example.com",
            full_name="Admin",
            role=Role.ADMIN,
            permissions=[permission.value for permission in Permission],
            is_superuser=True,
            must_setup_mfa=admin_requires_mfa,
            mfa_enabled=not admin_requires_mfa,
        )

    def _add_user(
        self,
        *,
        user_id: str,
        username: str,
        email: str,
        full_name: str,
        role: Role,
        permissions: list[str],
        is_superuser: bool = False,
        must_setup_mfa: bool = False,
        mfa_enabled: bool = False,
        group_ids: list[str] | None = None,
    ) -> _UserState:
        user = _UserState(
            id=user_id,
            username=username,
            email=email,
            full_name=full_name,
            tenant_id=self.tenant_id,
            org_id=self.org_id,
            role=role,
            permissions=list(permissions),
            group_ids=list(group_ids or []),
            is_superuser=is_superuser,
            must_setup_mfa=must_setup_mfa,
            mfa_enabled=mfa_enabled,
        )
        self.users[user_id] = user
        self.tokens[f"token-{user_id}"] = self._token_data_for_user(user)
        self.tokens[f"setup-{user_id}"] = self._token_data_for_user(user, is_mfa_setup=True)
        return user

    def _token_data_for_user(self, user: _UserState, *, is_mfa_setup: bool = False) -> TokenData:
        return TokenData(
            user_id=user.id,
            username=user.username,
            tenant_id=user.tenant_id,
            org_id=user.org_id,
            role=user.role,
            is_superuser=user.is_superuser,
            permissions=list(user.permissions),
            group_ids=list(user.group_ids),
            iat=1,
            is_mfa_setup=is_mfa_setup,
        )

    def _permission_enums(self, permission_names: list[str]) -> list[Permission]:
        return [Permission(name) for name in permission_names]

    def decode_token(self, token: str) -> TokenData | None:
        token_data = self.tokens.get(token)
        return token_data.model_copy(deep=True) if token_data else None

    def get_user_by_id(self, user_id: str) -> SimpleNamespace | None:
        user = self.users.get(user_id)
        return user.to_runtime_user() if user else None

    def get_user_by_id_in_tenant(self, user_id: str, tenant_id: str) -> SimpleNamespace | None:
        user = self.users.get(user_id)
        if user is None or user.tenant_id != tenant_id:
            return None
        return user.to_runtime_user()

    def get_user_permissions(self, user: object) -> list[str]:
        user_id = str(getattr(user, "id", "") or getattr(user, "user_id", ""))
        state = self.users.get(user_id)
        return list(state.permissions if state else [])

    def is_external_auth_enabled(self) -> bool:
        return False

    def is_password_auth_enabled(self) -> bool:
        return True

    def login(self, username: str, password: str, mfa_code: str | None = None) -> Token | dict[str, Any] | None:
        del password
        user = next((item for item in self.users.values() if item.username == username), None)
        if user is None:
            return None
        if user.must_setup_mfa and not user.mfa_enabled:
            return {"mfa_setup_required": True, "setup_token": f"setup-{user.id}"}
        if user.mfa_enabled:
            if not mfa_code:
                return {"mfa_required": True}
            if mfa_code != "123456":
                return None
        return Token(access_token=f"token-{user.id}", expires_in=3600)

    def enroll_totp(self, user_id: str) -> dict[str, str]:
        if user_id not in self.users:
            raise ValueError("user not found")
        return {
            "secret": "ABC123",
            "otpauth_url": "otpauth://totp/BeObservant:admin?secret=ABC123",
        }

    def verify_enable_totp(self, user_id: str, code: str) -> list[str]:
        if code != "123456":
            raise ValueError("Invalid TOTP code")
        user = self.users[user_id]
        user.mfa_enabled = True
        user.must_setup_mfa = False
        return ["recovery-1", "recovery-2"]

    def create_user(
        self,
        payload: Any,
        tenant_id: str,
        *_args: Any,
    ) -> SimpleNamespace:
        user_id = f"u-{self.next_user_id}"
        self.next_user_id += 1
        role = getattr(payload, "role", Role.USER)
        permissions = [permission.value for permission in ROLE_PERMISSIONS[role]]
        user = self._add_user(
            user_id=user_id,
            username=payload.username,
            email=payload.email,
            full_name=getattr(payload, "full_name", None) or payload.username,
            role=role,
            permissions=permissions,
            group_ids=list(getattr(payload, "group_ids", []) or []),
        )
        user.tenant_id = tenant_id
        user.org_id = getattr(payload, "org_id", self.org_id) or self.org_id
        self.tokens[f"token-{user.id}"] = self._token_data_for_user(user)
        return user.to_runtime_user()

    def build_user_response(self, user: object, _permissions: list[str]) -> UserResponse:
        user_id = str(getattr(user, "id"))
        state = self.users[user_id]
        return UserResponse(
            id=state.id,
            username=state.username,
            email=state.email,
            full_name=state.full_name,
            role=state.role,
            group_ids=list(state.group_ids),
            is_active=state.is_active,
            org_id=state.org_id,
            tenant_id=state.tenant_id,
            created_at=state.created_at,
            last_login=None,
            permissions=self._permission_enums(state.permissions),
            direct_permissions=[],
            needs_password_change=False,
            api_keys=[],
            mfa_enabled=state.mfa_enabled,
            must_setup_mfa=state.must_setup_mfa,
            auth_provider="local",
        )

    def create_group(self, payload: Any, tenant_id: str, *_args: Any) -> Group:
        group_id = f"g-{self.next_group_id}"
        self.next_group_id += 1
        group = Group(
            id=group_id,
            tenant_id=tenant_id,
            name=payload.name,
            description=getattr(payload, "description", None),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            permissions=[],
        )
        self.groups[group_id] = group
        return group

    def update_group_members(self, group_id: str, user_ids: list[str], *_args: Any) -> bool:
        if group_id not in self.groups:
            return False
        for user in self.users.values():
            user.group_ids = [existing for existing in user.group_ids if existing != group_id]
        for user_id in user_ids:
            if user_id in self.users and group_id not in self.users[user_id].group_ids:
                self.users[user_id].group_ids.append(group_id)
        return True

    async def create_dashboard(
        self,
        *,
        dashboard_create: dict[str, Any],
        user_id: str,
        tenant_id: str,
        visibility: str,
        shared_group_ids: list[str],
        **_kwargs: Any,
    ) -> dict[str, Any]:
        dashboard_data = dashboard_create.get("dashboard", {}) if isinstance(dashboard_create, dict) else {}
        uid = str(dashboard_data.get("uid") or f"dash-{self.next_dashboard_id}")
        title = str(dashboard_data.get("title") or uid)
        item_id = self.next_dashboard_id
        self.next_dashboard_id += 1
        self.dashboards[uid] = {
            "id": item_id,
            "uid": uid,
            "title": title,
            "tenant_id": tenant_id,
            "created_by": user_id,
            "visibility": visibility,
            "shared_group_ids": list(shared_group_ids),
        }
        return {"id": item_id, "uid": uid, "status": "success", "slug": uid}

    def _dashboard_visible(self, item: dict[str, Any], *, user_id: str, tenant_id: str, group_ids: list[str], is_admin: bool) -> bool:
        if is_admin:
            return True
        if item["tenant_id"] != tenant_id:
            return False
        if item["created_by"] == user_id:
            return True
        visibility = item["visibility"]
        if visibility == "tenant":
            return True
        if visibility == "group":
            return bool(set(item["shared_group_ids"]).intersection(group_ids))
        return False

    async def search_dashboards(
        self,
        *,
        user_id: str,
        tenant_id: str,
        group_ids: list[str],
        is_admin: bool,
        **_kwargs: Any,
    ) -> list[dict[str, Any]]:
        visible = []
        for item in self.dashboards.values():
            if not self._dashboard_visible(item, user_id=user_id, tenant_id=tenant_id, group_ids=group_ids, is_admin=is_admin):
                continue
            visible.append(
                {
                    "id": item["id"],
                    "uid": item["uid"],
                    "title": item["title"],
                    "uri": f"db/{item['uid']}",
                    "url": f"/d/{item['uid']}",
                    "slug": item["uid"],
                    "type": "dash-db",
                    "tags": [],
                    "isStarred": False,
                    "folderId": 0,
                    "folderUid": None,
                    "folderTitle": None,
                    "created_by": item["created_by"],
                    "is_hidden": False,
                    "is_owned": item["created_by"] == user_id,
                    "visibility": item["visibility"],
                    "sharedGroupIds": list(item["shared_group_ids"]),
                }
            )
        return sorted(visible, key=lambda item: item["uid"])

    async def get_dashboard(
        self,
        *,
        uid: str,
        user_id: str,
        tenant_id: str,
        group_ids: list[str],
        is_admin: bool,
        **_kwargs: Any,
    ) -> dict[str, Any] | None:
        item = self.dashboards.get(uid)
        if item is None:
            return None
        if not self._dashboard_visible(item, user_id=user_id, tenant_id=tenant_id, group_ids=group_ids, is_admin=is_admin):
            return None
        return {
            "dashboard": {"uid": item["uid"], "title": item["title"]},
            "meta": {"visibility": item["visibility"], "sharedGroupIds": list(item["shared_group_ids"])},
        }


def _auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _patch_auth(monkeypatch: pytest.MonkeyPatch, state: _WorkflowState) -> None:
    monkeypatch.setattr(dependencies.auth_service, "decode_token", state.decode_token)
    monkeypatch.setattr(dependencies.auth_service, "get_user_by_id", state.get_user_by_id)
    monkeypatch.setattr(dependencies.auth_service, "get_user_by_id_in_tenant", state.get_user_by_id_in_tenant)
    monkeypatch.setattr(dependencies.auth_service, "get_user_permissions", state.get_user_permissions)
    monkeypatch.setattr(dependencies.auth_service, "is_external_auth_enabled", state.is_external_auth_enabled)
    monkeypatch.setattr(dependencies.auth_service, "is_password_auth_enabled", state.is_password_auth_enabled)
    monkeypatch.setattr(dependencies.auth_service, "login", state.login)
    monkeypatch.setattr(dependencies.auth_service, "enroll_totp", state.enroll_totp)
    monkeypatch.setattr(dependencies.auth_service, "verify_enable_totp", state.verify_enable_totp)
    monkeypatch.setattr(dependencies.auth_service, "create_user", state.create_user)
    monkeypatch.setattr(dependencies.auth_service, "build_user_response", state.build_user_response)
    monkeypatch.setattr(dependencies.auth_service, "create_group", state.create_group)
    monkeypatch.setattr(dependencies.auth_service, "update_group_members", state.update_group_members)


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    async def _send_user_welcome_email(**kwargs: Any) -> bool:
        del kwargs
        return True

    monkeypatch.setattr(dependencies, "enforce_rate_limit", lambda *args, **kwargs: None)
    monkeypatch.setattr(dependencies, "enforce_ip_rate_limit", lambda *args, **kwargs: None)
    monkeypatch.setattr(auth_routes, "rate_limit_func", lambda *args, **kwargs: None)
    monkeypatch.setattr(grafana_proxy_router, "enforce_public_endpoint_security", lambda *args, **kwargs: None)
    monkeypatch.setattr(user_routes.notification_service, "send_user_welcome_email", _send_user_welcome_email)
    app.dependency_overrides[get_db] = lambda: "db"
    app.dependency_overrides[dashboards.get_db] = lambda: "db"
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_login_mfa_and_observability_workflow(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    state = _WorkflowState(admin_requires_mfa=True)
    _patch_auth(monkeypatch, state)

    tempo_calls: list[dict[str, Any]] = []
    loki_calls: list[dict[str, Any]] = []
    grafana_auth_calls: list[dict[str, Any]] = []

    async def fake_search_traces(query: Any, tenant_id: str | None = None, fetch_full_traces: bool = False) -> dict[str, Any]:
        tempo_calls.append({"tenant_id": tenant_id, "service": query.service, "fetch_full": fetch_full_traces})
        return {
            "data": [
                {
                    "traceID": "trace-1",
                    "spans": [
                        {
                            "spanID": "span-1",
                            "traceID": "trace-1",
                            "operationName": "GET /checkout",
                            "startTime": 1,
                            "duration": 10,
                            "tags": [],
                            "serviceName": "checkout",
                        }
                    ],
                }
            ],
            "total": 1,
            "limit": query.limit,
            "offset": 0,
        }

    async def fake_filter_logs(*, labels: dict[str, str], filters: list[str] | None, start: int | None, end: int | None, limit: int, tenant_id: str | None = None) -> dict[str, Any]:
        loki_calls.append({"tenant_id": tenant_id, "labels": labels, "filters": filters, "limit": limit})
        return {"status": "success", "data": {"resultType": "streams", "result": []}}

    async def fake_authorize_proxy_request(**kwargs: Any) -> dict[str, str]:
        grafana_auth_calls.append(kwargs)
        return {"X-WEBAUTH-USER": "admin"}

    monkeypatch.setattr(tempo_router.tempo_service, "search_traces", fake_search_traces)
    monkeypatch.setattr(loki_router.loki_service, "filter_logs", fake_filter_logs)
    monkeypatch.setattr(grafana_proxy_router.proxy, "authorize_proxy_request", fake_authorize_proxy_request)

    login_response = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "secret-pass"},
    )
    assert login_response.status_code == 401
    setup_token = login_response.json()["detail"]["setup_token"]

    enroll_response = client.post(
        "/api/auth/mfa/enroll",
        headers=_auth_header(setup_token),
    )
    assert enroll_response.status_code == 200
    assert enroll_response.json()["secret"] == "ABC123"

    verify_response = client.post(
        "/api/auth/mfa/verify",
        headers=_auth_header(setup_token),
        json={"code": "123456"},
    )
    assert verify_response.status_code == 200
    assert verify_response.json()["recovery_codes"] == ["recovery-1", "recovery-2"]

    missing_mfa_response = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "secret-pass"},
    )
    assert missing_mfa_response.status_code == 401
    assert missing_mfa_response.json()["detail"] == "MFA required"

    token_response = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "secret-pass", "mfa_code": "123456"},
    )
    assert token_response.status_code == 200
    access_token = token_response.json()["access_token"]
    assert access_token == "token-u-admin"
    assert "beobservant_token=" in token_response.headers["set-cookie"]

    traces_response = client.get(
        "/api/tempo/traces/search",
        params={"service": "checkout", "limit": 5, "fetchFull": True},
        headers=_auth_header(access_token),
    )
    assert traces_response.status_code == 200
    assert traces_response.json()["data"][0]["traceID"] == "trace-1"
    assert tempo_calls == [{"tenant_id": "org-a", "service": "checkout", "fetch_full": True}]

    logs_response = client.post(
        "/api/loki/filter",
        headers=_auth_header(access_token),
        json={"labels": {"service": "checkout"}, "filters": ["error"], "limit": 25},
    )
    assert logs_response.status_code == 200
    assert logs_response.json()["status"] == "success"
    assert loki_calls == [{"tenant_id": "org-a", "labels": {"service": "checkout"}, "filters": ["error"], "limit": 25}]

    bootstrap_response = client.post(
        "/api/grafana/bootstrap-session",
        headers=_auth_header(access_token),
        json={"next": "/explore"},
    )
    assert bootstrap_response.status_code == 200
    assert bootstrap_response.json() == {"launch_url": "/grafana/explore"}

    grafana_auth_response = client.get(
        "/api/grafana/auth",
        params={"token": access_token, "orig": "/grafana/d/latency"},
    )
    assert grafana_auth_response.status_code == 204
    assert grafana_auth_response.headers["x-webauth-user"] == "admin"
    assert grafana_auth_calls[0]["token"] == access_token
    assert grafana_auth_calls[0]["orig"] == "/grafana/d/latency"


def test_rca_and_alerting_proxy_workflow(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    state = _WorkflowState(admin_requires_mfa=False)
    _patch_auth(monkeypatch, state)

    becertain_calls: list[dict[str, Any]] = []
    forward_calls: list[dict[str, Any]] = []

    async def fake_request_json(**kwargs: Any) -> dict[str, Any]:
        becertain_calls.append(kwargs)
        upstream_path = kwargs["upstream_path"]
        if upstream_path == "/api/v1/jobs/analyze":
            payload = kwargs.get("payload") or {}
            return {
                "job_id": "job-1",
                "report_id": "report-1",
                "status": "accepted",
                "created_at": "2024-01-01T00:00:00Z",
                "tenant_id": payload.get("tenant_id"),
                "requested_by": kwargs["current_user"].user_id,
            }
        if upstream_path == "/api/v1/jobs/job-1/result":
            raise HTTPException(status_code=409, detail="pending")
        if upstream_path == "/api/v1/jobs/job-1":
            return {
                "job_id": "job-1",
                "report_id": "report-1",
                "status": "completed",
                "created_at": "2024-01-01T00:00:00Z",
                "tenant_id": kwargs["tenant_id"],
                "requested_by": kwargs["current_user"].user_id,
            }
        return {"ok": True, "path": upstream_path, "tenant_id": kwargs.get("tenant_id")}

    async def fake_forward(**kwargs: Any) -> JSONResponse:
        forward_calls.append(kwargs)
        return JSONResponse(
            {
                "ok": True,
                "path": kwargs["upstream_path"],
                "require_api_key": kwargs["require_api_key"],
            }
        )

    monkeypatch.setattr(becertain_router.becertain_proxy_service, "request_json", fake_request_json)
    monkeypatch.setattr(alertmanager_router.benotified_proxy_service, "forward", fake_forward)

    headers = _auth_header("token-u-admin")

    create_job_response = client.post(
        "/api/becertain/analyze/jobs",
        headers=headers,
        json={"start": 1, "end": 2, "services": ["checkout"]},
    )
    assert create_job_response.status_code == 202
    assert create_job_response.json()["tenant_id"] == "org-a"

    rca_filter_response = client.post(
        "/api/becertain/anomalies/traces",
        headers=headers,
        json={"service": "checkout"},
    )
    assert rca_filter_response.status_code == 200
    assert rca_filter_response.json()["path"] == "/api/v1/anomalies/traces"

    result_response = client.get(
        "/api/becertain/analyze/jobs/job-1/result",
        headers=headers,
    )
    assert result_response.status_code == 200
    assert result_response.json()["status"] == "completed"
    assert result_response.json()["result"] is None

    channels_response = client.post(
        "/api/alertmanager/channels",
        headers=headers,
        json={"name": "slack-main"},
    )
    assert channels_response.status_code == 200
    assert channels_response.json()["path"] == "/internal/v1/api/alertmanager/channels"

    integration_response = client.post(
        "/api/alertmanager/integrations/slack",
        headers=headers,
        json={"enabled": True},
    )
    assert integration_response.status_code == 200
    assert integration_response.json()["path"] == "/internal/v1/api/alertmanager/integrations/slack"

    jira_response = client.post(
        "/api/alertmanager/jira/issues",
        headers=headers,
        json={"title": "CPU spike"},
    )
    assert jira_response.status_code == 200
    assert jira_response.json()["path"] == "/internal/v1/api/alertmanager/jira/issues"

    alerts_response = client.post(
        "/api/alertmanager/alerts",
        headers=headers,
        json={"alerts": []},
    )
    assert alerts_response.status_code == 200
    assert alerts_response.json()["path"] == "/internal/v1/api/alertmanager/alerts"

    assert becertain_calls[0]["payload"]["tenant_id"] == "org-a"
    assert becertain_calls[1]["payload"]["tenant_id"] == "org-a"
    assert [call["upstream_path"] for call in forward_calls] == [
        "/internal/v1/api/alertmanager/channels",
        "/internal/v1/api/alertmanager/integrations/slack",
        "/internal/v1/api/alertmanager/jira/issues",
        "/internal/v1/api/alertmanager/alerts",
    ]
    assert all(call["require_api_key"] is True for call in forward_calls)


def test_group_scoped_visibility_and_live_alerting_context(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    state = _WorkflowState(admin_requires_mfa=False)
    _patch_auth(monkeypatch, state)

    monkeypatch.setattr(dashboards, "parse_dashboard_create_payload", lambda raw: raw)
    monkeypatch.setattr(dashboards, "parse_dashboard_update_payload", lambda raw: raw)
    monkeypatch.setattr(dashboards.proxy, "build_dashboard_search_context", lambda *args, **kwargs: {})
    monkeypatch.setattr(dashboards.proxy, "create_dashboard", state.create_dashboard)
    monkeypatch.setattr(dashboards.proxy, "search_dashboards", state.search_dashboards)
    monkeypatch.setattr(dashboards.proxy, "get_dashboard", state.get_dashboard)

    captured_claims: list[dict[str, Any]] = []

    def fake_encode_jwt(claims: dict[str, Any], _key: str, _algorithm: str) -> str:
        captured_claims.append(dict(claims))
        return "context-token"

    async def fake_upstream_request(*, method: str, url: str, params: Any, content: bytes, headers: dict[str, str]) -> httpx.Response:
        del params, content
        return httpx.Response(
            status_code=200,
            json={"ok": True, "method": method, "url": url, "authorization": headers.get("Authorization")},
            headers={"content-type": "application/json"},
        )

    monkeypatch.setattr(alertmanager_router.benotified_proxy_service, "write_audit", lambda **kwargs: None)
    monkeypatch.setattr(alertmanager_router.benotified_proxy_service, "_resolve_actor_api_key_id", lambda current_user: "api-key-1")
    monkeypatch.setattr(alertmanager_router.benotified_proxy_service, "_encode_jwt", fake_encode_jwt)
    monkeypatch.setattr(alertmanager_router.benotified_proxy_service._client, "request", fake_upstream_request)
    monkeypatch.setattr(
        config,
        "get_secret",
        lambda key: {
            "BENOTIFIED_SERVICE_TOKEN": "service-token",
            "BENOTIFIED_CONTEXT_SIGNING_KEY": "signing-key",
        }.get(key),
    )

    admin_headers = _auth_header("token-u-admin")

    group_response = client.post(
        "/api/auth/groups",
        headers=admin_headers,
        json={"name": "ops-team", "description": "Operations"},
    )
    assert group_response.status_code == 200
    group_id = group_response.json()["id"]

    user2_response = client.post(
        "/api/auth/users",
        headers=admin_headers,
        json={"username": "user2", "email": "user2@example.com", "password": "password123"},
    )
    assert user2_response.status_code == 200
    user2_id = user2_response.json()["id"]

    user3_response = client.post(
        "/api/auth/users",
        headers=admin_headers,
        json={"username": "user3", "email": "user3@example.com", "password": "password123"},
    )
    assert user3_response.status_code == 200
    user3_id = user3_response.json()["id"]

    update_members_response = client.put(
        f"/api/auth/groups/{group_id}/members",
        headers=admin_headers,
        json={"user_ids": [user2_id]},
    )
    assert update_members_response.status_code == 200
    assert update_members_response.json() == {"success": True, "user_ids": [user2_id]}

    user2_channels = client.get("/api/alertmanager/channels", headers=_auth_header(f"token-{user2_id}"))
    user3_channels = client.get("/api/alertmanager/channels", headers=_auth_header(f"token-{user3_id}"))
    assert user2_channels.status_code == 200
    assert user3_channels.status_code == 200
    assert captured_claims[-2]["group_ids"] == [group_id]
    assert captured_claims[-1]["group_ids"] == []

    private_dashboard = client.post(
        "/api/grafana/dashboards?visibility=private",
        headers=admin_headers,
        json={"dashboard": {"uid": "dash-private", "title": "Private"}},
    )
    group_dashboard = client.post(
        f"/api/grafana/dashboards?visibility=group&shared_group_ids={group_id}",
        headers=admin_headers,
        json={"dashboard": {"uid": "dash-group", "title": "Group"}},
    )
    tenant_dashboard = client.post(
        "/api/grafana/dashboards?visibility=tenant",
        headers=admin_headers,
        json={"dashboard": {"uid": "dash-tenant", "title": "Tenant"}},
    )
    assert private_dashboard.status_code == 200
    assert group_dashboard.status_code == 200
    assert tenant_dashboard.status_code == 200

    admin_search = client.get("/api/grafana/dashboards/search", headers=admin_headers)
    user2_search = client.get("/api/grafana/dashboards/search", headers=_auth_header(f"token-{user2_id}"))
    user3_search = client.get("/api/grafana/dashboards/search", headers=_auth_header(f"token-{user3_id}"))
    assert len(admin_search.json()) == 3
    assert len(user2_search.json()) == 2
    assert len(user3_search.json()) == 1

    assert client.get("/api/grafana/dashboards/dash-private", headers=_auth_header(f"token-{user2_id}")).status_code == 404
    assert client.get("/api/grafana/dashboards/dash-group", headers=_auth_header(f"token-{user2_id}")).status_code == 200
    assert client.get("/api/grafana/dashboards/dash-tenant", headers=_auth_header(f"token-{user2_id}")).status_code == 200

    assert client.get("/api/grafana/dashboards/dash-group", headers=_auth_header(f"token-{user3_id}")).status_code == 404
    assert client.get("/api/grafana/dashboards/dash-tenant", headers=_auth_header(f"token-{user3_id}")).status_code == 200