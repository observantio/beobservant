"""
Copyright (c) 2026 Stefan Kumarasinghe.

Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the
License. You may obtain a copy of the License at
http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

import inspect
from email.message import EmailMessage

import pytest
from fastapi import HTTPException, Request

try:
    from ._env import ensure_test_env
except ImportError:
    from tests._env import ensure_test_env

ensure_test_env()

from config import config
from models.access.auth_models import Role, TokenData
from routers.observability.grafana_router import proxy as proxy_router
from services import notification_service as notification_mod
from services.grafana.grafana_bundles import (
    DashboardSearchParams,
    DatasourceListParams,
    FolderAccessCriteria,
    FolderGetParams,
    GrafanaUserScope,
)
from services.grafana_proxy_service import GrafanaProxyService


def _request(headers: list[tuple[bytes, bytes]] | None = None, cookies: dict[str, str] | None = None) -> Request:
    header_list: list[tuple[bytes, bytes]] = list(headers or [])
    if cookies:
        header_list.append((b"cookie", "; ".join(f"{k}={v}" for k, v in cookies.items()).encode("utf-8")))
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "path": "/grafana",
        "headers": header_list,
        "client": ("127.0.0.1", 1234),
        "scheme": "http",
        "query_string": b"",
    }
    return Request(scope)


async def _maybe_async(func, *args, **kwargs):
    value = func(*args, **kwargs)
    if inspect.isawaitable(value):
        return await value
    return value


def test_notification_service_helpers_and_messages(monkeypatch):
    monkeypatch.setattr(notification_mod.config, "DEFAULT_ADMIN_EMAIL", "admin@example.com")
    secrets = {
        "USER_WELCOME_EMAIL_ENABLED": "yes",
        "USER_WELCOME_SMTP_HOST": "smtp.example.com",
        "USER_WELCOME_SMTP_PORT": "not-a-number",
        "PASSWORD_RESET_EMAIL_ENABLED": "1",
        "PASSWORD_RESET_SMTP_HOST": "smtp-reset.example.com",
        "APP_LOGIN_URL": "https://app/login",
    }
    monkeypatch.setattr(notification_mod.config, "get_secret", lambda key: secrets.get(key))

    assert notification_mod._as_bool(True) is True
    assert notification_mod._as_bool(0) is False
    assert notification_mod._as_bool(" yes ") is True
    assert notification_mod._as_bool(object()) is False
    assert notification_mod._first_secret("missing", "USER_WELCOME_SMTP_HOST") == "smtp.example.com"
    assert notification_mod._is_enabled("USER_WELCOME_EMAIL_ENABLED") is True

    cfg = notification_mod._smtp_config("USER_WELCOME")
    assert cfg["hostname"] == "smtp.example.com"
    assert cfg["port"] == 587
    assert cfg["from_addr"] == "admin@example.com"
    assert cfg["envelope_from"] == "admin@example.com"

    secrets["USER_WELCOME_FROM"] = "Observantio"
    cfg_with_name = notification_mod._smtp_config("USER_WELCOME")
    assert "Observantio" in cfg_with_name["from_addr"]
    assert "admin@example.com" in cfg_with_name["from_addr"]
    assert cfg_with_name["envelope_from"] == "admin@example.com"

    svc = notification_mod.NotificationService()
    message = svc._build_message(subject="Hello", cfg=cfg, recipient="u@example.com", body="Body")
    assert isinstance(message, EmailMessage)
    assert message["To"] == "u@example.com"


@pytest.mark.asyncio
async def test_notification_service_email_flows(monkeypatch):
    svc = notification_mod.NotificationService()

    enabled = {
        "USER_WELCOME_EMAIL_ENABLED": "true",
        "USER_WELCOME_SMTP_HOST": "smtp.welcome",
        "PASSWORD_RESET_EMAIL_ENABLED": "true",
        "PASSWORD_RESET_SMTP_HOST": "smtp.reset",
        "APP_LOGIN_URL": "https://app/login",
    }
    monkeypatch.setattr(notification_mod.config, "DEFAULT_ADMIN_EMAIL", "admin@example.com")
    monkeypatch.setattr(notification_mod.config, "get_secret", lambda key: enabled.get(key))

    sent = []

    async def fake_dispatch(cfg, msg, recipient):
        sent.append((cfg, msg, recipient))
        return True

    monkeypatch.setattr(svc, "_dispatch", fake_dispatch)

    assert await svc.send_user_welcome_email("u@example.com", "user", "User") is True
    assert "Welcome to Watchdog" == sent[-1][1]["Subject"]
    welcome_plain = sent[-1][1].get_body(preferencelist=("plain",))
    assert welcome_plain is not None
    assert "Login URL: https://app/login" in welcome_plain.get_content()

    assert await svc.send_temporary_password_email("u@example.com", "user", "Temp1234") is True
    assert "Temporary Password" in sent[-1][1]["Subject"]
    temp_plain = sent[-1][1].get_body(preferencelist=("plain",))
    assert temp_plain is not None
    assert "Temp1234" in temp_plain.get_content()


@pytest.mark.asyncio
async def test_notification_service_disabled_and_dispatch_failure_paths(monkeypatch):
    svc = notification_mod.NotificationService()
    monkeypatch.setattr(notification_mod.config, "DEFAULT_ADMIN_EMAIL", "admin@example.com")

    monkeypatch.setattr(notification_mod.config, "get_secret", lambda _key: None)
    assert await svc.send_user_welcome_email("u@example.com", "user") is False
    assert await svc.send_temporary_password_email("u@example.com", "user", "Temp1234") is False

    monkeypatch.setattr(
        notification_mod.config,
        "get_secret",
        lambda key: {
            "USER_WELCOME_EMAIL_ENABLED": "true",
            "USER_WELCOME_SMTP_HOST": "smtp.welcome",
        }.get(key),
    )

    async def failing_send(**_kwargs):
        raise ValueError("boom")

    monkeypatch.setattr(svc, "_send_smtp", failing_send)
    cfg = notification_mod._smtp_config("USER_WELCOME")
    msg = svc._build_message(subject="Hello", cfg=cfg, recipient="u@example.com", body="Body")
    assert await svc._dispatch(cfg, msg, "u@example.com") is False


@pytest.mark.asyncio
async def test_grafana_proxy_service_delegates_and_router_branches(monkeypatch):
    svc = GrafanaProxyService()
    assert svc._normalize_group_ids([" g1 ", "g1", "", None, "g2"]) == ["g1", "g2"]

    monkeypatch.setattr(svc, "_effective_group_ids", lambda *_args, **_kwargs: ["live"])

    async def fake_search(*args, **kwargs):
        scope = args[2]
        return [{"uid": "d1", "groups": scope.group_ids}]

    async def fake_get_dashboard(*args, **kwargs):
        return {"uid": args[2], "groups": args[3].group_ids}

    async def fake_get_datasources(*args, **kwargs):
        scope = args[2]
        return ["ds", scope.group_ids]

    async def fake_get_folder(*args, **kwargs):
        scope = args[3]
        return {"uid": args[2], "groups": scope.group_ids}

    monkeypatch.setitem(svc.search_dashboards.__globals__, "search_dashboards", fake_search)
    monkeypatch.setitem(svc.get_dashboard.__globals__, "get_dashboard", fake_get_dashboard)
    monkeypatch.setitem(svc.get_datasources.__globals__, "get_datasources", fake_get_datasources)
    monkeypatch.setitem(svc.get_folder.__globals__, "get_folder", fake_get_folder)
    monkeypatch.setitem(svc.get_dashboard_metadata.__globals__, "get_dashboard_metadata", lambda *_args: {1: "one"})
    monkeypatch.setitem(svc.get_datasource_metadata.__globals__, "get_datasource_metadata", lambda *_args: {2: "two"})
    monkeypatch.setitem(svc.toggle_dashboard_hidden.__globals__, "toggle_dashboard_hidden", lambda *_args: True)
    monkeypatch.setitem(svc.toggle_datasource_hidden.__globals__, "toggle_datasource_hidden", lambda *_args: True)
    monkeypatch.setitem(svc.toggle_folder_hidden.__globals__, "toggle_folder_hidden", lambda *_args: True)
    monkeypatch.setitem(svc.check_folder_access.__globals__, "check_folder_access", lambda *_args, **_kwargs: "folder")
    monkeypatch.setitem(svc.is_folder_accessible.__globals__, "is_folder_accessible", lambda *_args, **_kwargs: True)

    db = "db"
    assert await svc.search_dashboards(
        db,
        GrafanaUserScope("u1", "tenant", ["stale"]),
        DashboardSearchParams(),
    ) == [{"uid": "d1", "groups": ["live"]}]
    assert await svc.get_dashboard(
        db,
        "dash-1",
        GrafanaUserScope("u1", "tenant", ["stale"]),
    ) == {"uid": "dash-1", "groups": ["live"]}
    assert await svc.get_datasources(
        "db",
        GrafanaUserScope("u1", "tenant", ["stale"]),
        DatasourceListParams(),
    ) == ["ds", ["live"]]
    assert await svc.get_folder(
        "db",
        "folder-1",
        GrafanaUserScope("u1", "tenant", ["stale"]),
        FolderGetParams(),
    ) == {"uid": "folder-1", "groups": ["live"]}
    assert svc.get_dashboard_metadata("db", "tenant") == {"1": "one"}
    assert svc.get_datasource_metadata("db", "tenant") == {"2": "two"}
    assert svc.toggle_dashboard_hidden("db", "uid", "u1", "tenant", True) is True
    assert svc.toggle_datasource_hidden("db", "uid", "u1", "tenant", True) is True
    assert svc.toggle_folder_hidden("db", "uid", "u1", "tenant", True) is True
    assert (
        svc.check_folder_access(
            "db",
            "uid",
            GrafanaUserScope("u1", "tenant", ["g1"]),
            FolderAccessCriteria(),
        )
        == "folder"
    )
    assert (
        svc.is_folder_accessible(
            "db",
            "uid",
            GrafanaUserScope("u1", "tenant", ["g1"]),
            FolderAccessCriteria(),
        )
        is True
    )

    token_data = TokenData(
        user_id="u1",
        username="user",
        tenant_id="tenant",
        org_id="org",
        role=Role.ADMIN,
        permissions=[],
    )
    monkeypatch.setattr(proxy_router, "enforce_public_endpoint_security", lambda *_args, **_kwargs: None)

    async def fake_authorize_proxy_request(**_kwargs):
        return {"X-Test": "ok"}

    monkeypatch.setattr(proxy_router.proxy, "authorize_proxy_request", fake_authorize_proxy_request)
    response = await proxy_router.grafana_auth(_request(), token="jwt", orig="/")
    assert response.status_code == 204
    assert response.headers["x-test"] == "ok"

    monkeypatch.setattr(proxy_router, "normalize_grafana_next_path", lambda next_path: next_path or "/")
    monkeypatch.setattr(proxy_router, "cookie_secure", lambda _request: False)
    monkeypatch.setattr(config, "FORCE_SECURE_COOKIES", False)
    monkeypatch.setattr(config, "JWT_EXPIRATION_MINUTES", 5)
    response = await proxy_router.bootstrap_grafana_session(
        _request(headers=[(b"authorization", b"Bearer jwt-1")]),
        proxy_router.GrafanaBootstrapSessionRequest(next="/explore"),
        token_data,
    )
    assert response.status_code == 200
    assert b'"launch_url":"/grafana/explore?org-key=' in response.body
    assert b'"org_key":"' in response.body

    response = await proxy_router.bootstrap_grafana_session(
        _request(cookies={"watchdog_token": "jwt-2"}),
        proxy_router.GrafanaBootstrapSessionRequest(next=None),
        token_data,
    )
    assert response.status_code == 200

    with pytest.raises(HTTPException) as exc:
        await proxy_router.bootstrap_grafana_session(
            _request(), proxy_router.GrafanaBootstrapSessionRequest(), token_data
        )
    assert exc.value.status_code == 401
