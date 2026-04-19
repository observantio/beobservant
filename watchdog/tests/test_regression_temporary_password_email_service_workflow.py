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
async def test_temporary_password_email_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    svc = notification_mod.NotificationService()
    monkeypatch.setattr(notification_mod.config, "get_secret", lambda _key: None)

    result = await svc.send_temporary_password_email(
        notification_mod.TemporaryPasswordEmailRequest(
            recipient_email="user@example.com",
            username="user",
            temporary_password="Temp1234",
        )
    )

    assert result is False


@pytest.mark.asyncio
async def test_temporary_password_email_can_use_user_welcome_flag_as_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
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

    async def _dispatch(*_args, **_kwargs):
        return True

    monkeypatch.setattr(svc, "_dispatch", _dispatch)

    result = await svc.send_temporary_password_email(
        notification_mod.TemporaryPasswordEmailRequest(
            recipient_email="user@example.com",
            username="user",
            temporary_password="Temp1234",
        )
    )

    assert result is True


@pytest.mark.asyncio
async def test_temporary_password_email_returns_false_when_smtp_host_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    svc = notification_mod.NotificationService()

    monkeypatch.setattr(
        notification_mod.config,
        "get_secret",
        lambda key: {
            "PASSWORD_RESET_EMAIL_ENABLED": "true",
            "PASSWORD_RESET_SMTP_HOST": "",
        }.get(key),
    )

    result = await svc.send_temporary_password_email(
        notification_mod.TemporaryPasswordEmailRequest(
            recipient_email="user@example.com",
            username="user",
            temporary_password="Temp1234",
        )
    )

    assert result is False


@pytest.mark.asyncio
async def test_temporary_password_email_includes_password_and_login_url(monkeypatch: pytest.MonkeyPatch) -> None:
    svc = notification_mod.NotificationService()
    captured = {}

    monkeypatch.setattr(notification_mod.config, "DEFAULT_ADMIN_EMAIL", "admin@example.com")
    monkeypatch.setattr(
        notification_mod.config,
        "get_secret",
        lambda key: {
            "PASSWORD_RESET_EMAIL_ENABLED": "true",
            "PASSWORD_RESET_SMTP_HOST": "smtp.reset.example",
            "APP_LOGIN_URL": "https://app.example/login",
        }.get(key),
    )

    async def _dispatch(_cfg, msg, _recipient):
        captured["msg"] = msg
        return True

    monkeypatch.setattr(svc, "_dispatch", _dispatch)

    result = await svc.send_temporary_password_email(
        notification_mod.TemporaryPasswordEmailRequest(
            recipient_email="user@example.com",
            username="user",
            temporary_password="Temp1234",
        )
    )

    assert result is True
    plain_body = captured["msg"].get_body(preferencelist=("plain",))
    assert plain_body is not None
    body_text = plain_body.get_content()
    assert "Temporary password" in body_text
    assert "Temp1234" in body_text
    assert "Login URL: https://app.example/login" in body_text


@pytest.mark.asyncio
async def test_temporary_password_email_omits_login_line_when_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    svc = notification_mod.NotificationService()
    captured = {}

    monkeypatch.setattr(notification_mod.config, "DEFAULT_ADMIN_EMAIL", "admin@example.com")
    monkeypatch.setattr(
        notification_mod.config,
        "get_secret",
        lambda key: {
            "PASSWORD_RESET_EMAIL_ENABLED": "true",
            "PASSWORD_RESET_SMTP_HOST": "smtp.reset.example",
        }.get(key),
    )

    async def _dispatch(_cfg, msg, _recipient):
        captured["msg"] = msg
        return False

    monkeypatch.setattr(svc, "_dispatch", _dispatch)

    result = await svc.send_temporary_password_email(
        notification_mod.TemporaryPasswordEmailRequest(
            recipient_email="user@example.com",
            username="user",
            temporary_password="Temp1234",
        )
    )

    assert result is False
    plain_body = captured["msg"].get_body(preferencelist=("plain",))
    assert plain_body is not None
    assert "Login URL:" not in plain_body.get_content()
