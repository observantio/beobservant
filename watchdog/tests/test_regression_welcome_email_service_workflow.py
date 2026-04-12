"""
Copyright (c) 2026 Stefan Kumarasinghe.

Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the
License. You may obtain a copy of the License at
http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

import pytest

try:
    from ._env import ensure_test_env
except ImportError:
    from tests._env import ensure_test_env

ensure_test_env()

from services import notification_service as notification_mod


@pytest.mark.asyncio
async def test_welcome_email_returns_false_when_feature_is_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    svc = notification_mod.NotificationService()
    monkeypatch.setattr(notification_mod.config, "get_secret", lambda _key: None)

    result = await svc.send_user_welcome_email("user@example.com", "user")

    assert result is False


@pytest.mark.asyncio
async def test_welcome_email_returns_false_when_smtp_host_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    svc = notification_mod.NotificationService()
    monkeypatch.setattr(
        notification_mod.config,
        "get_secret",
        lambda key: {
            "USER_WELCOME_EMAIL_ENABLED": "true",
            "USER_WELCOME_SMTP_HOST": "",
        }.get(key),
    )

    result = await svc.send_user_welcome_email("user@example.com", "user")

    assert result is False


@pytest.mark.asyncio
async def test_welcome_email_uses_login_url_in_plain_body(monkeypatch: pytest.MonkeyPatch) -> None:
    svc = notification_mod.NotificationService()
    captured = {}

    monkeypatch.setattr(notification_mod.config, "DEFAULT_ADMIN_EMAIL", "admin@example.com")
    monkeypatch.setattr(
        notification_mod.config,
        "get_secret",
        lambda key: {
            "USER_WELCOME_EMAIL_ENABLED": "true",
            "USER_WELCOME_SMTP_HOST": "smtp.welcome.example",
            "APP_LOGIN_URL": "https://app.example/login",
        }.get(key),
    )

    async def _dispatch(cfg, msg, recipient):
        captured["cfg"] = cfg
        captured["msg"] = msg
        captured["recipient"] = recipient
        return True

    monkeypatch.setattr(svc, "_dispatch", _dispatch)

    result = await svc.send_user_welcome_email("user@example.com", "user", "Example User")

    assert result is True
    assert captured["recipient"] == "user@example.com"
    plain_body = captured["msg"].get_body(preferencelist=("plain",))
    assert plain_body is not None
    assert "Login URL: https://app.example/login" in plain_body.get_content()


@pytest.mark.asyncio
async def test_welcome_email_falls_back_to_username_when_full_name_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    svc = notification_mod.NotificationService()
    captured = {}

    monkeypatch.setattr(notification_mod.config, "DEFAULT_ADMIN_EMAIL", "admin@example.com")
    monkeypatch.setattr(
        notification_mod.config,
        "get_secret",
        lambda key: {
            "USER_WELCOME_EMAIL_ENABLED": "true",
            "USER_WELCOME_SMTP_HOST": "smtp.welcome.example",
        }.get(key),
    )

    async def _dispatch(_cfg, msg, _recipient):
        captured["msg"] = msg
        return True

    monkeypatch.setattr(svc, "_dispatch", _dispatch)

    result = await svc.send_user_welcome_email("user@example.com", "fallback-user", None)

    assert result is True
    plain_body = captured["msg"].get_body(preferencelist=("plain",))
    assert plain_body is not None
    assert "Hello fallback-user" in plain_body.get_content()


@pytest.mark.asyncio
async def test_welcome_email_propagates_dispatch_failure_as_false(monkeypatch: pytest.MonkeyPatch) -> None:
    svc = notification_mod.NotificationService()

    monkeypatch.setattr(notification_mod.config, "DEFAULT_ADMIN_EMAIL", "admin@example.com")
    monkeypatch.setattr(
        notification_mod.config,
        "get_secret",
        lambda key: {
            "USER_WELCOME_EMAIL_ENABLED": "true",
            "USER_WELCOME_SMTP_HOST": "smtp.welcome.example",
        }.get(key),
    )

    async def _dispatch(_cfg, _msg, _recipient):
        return False

    monkeypatch.setattr(svc, "_dispatch", _dispatch)

    result = await svc.send_user_welcome_email("user@example.com", "user")

    assert result is False
