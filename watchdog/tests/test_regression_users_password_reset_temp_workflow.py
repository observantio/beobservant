"""
Copyright (c) 2026 Stefan Kumarasinghe.

Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the
License. You may obtain a copy of the License at
http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

try:
    from ._env import ensure_test_env
except ImportError:
    from tests._env import ensure_test_env

ensure_test_env()

from models.access.auth_models import Permission, Role
from routers.access.auth_router import users as users_router
from tests._regression_helpers import run_in_threadpool_inline, token_data


def _admin_user():
    return token_data(user_id="admin-1", username="admin", role=Role.ADMIN, permissions=[Permission.MANAGE_USERS.value])


@pytest.mark.asyncio
async def test_reset_temp_password_requires_admin_or_manage_permission(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(users_router, "rtp", run_in_threadpool_inline)

    with pytest.raises(HTTPException) as exc:
        await users_router.reset_user_password_temp(
            "target-1",
            token_data(user_id="user-1", username="user", role=Role.USER, permissions=[]),
        )

    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_reset_temp_password_returns_404_for_missing_target(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(users_router, "rtp", run_in_threadpool_inline)
    monkeypatch.setattr(users_router.auth_service, "get_user_by_id_in_tenant", lambda *_args: None)

    with pytest.raises(HTTPException) as exc:
        await users_router.reset_user_password_temp("target-1", _admin_user())

    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_reset_temp_password_rejects_admin_targets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(users_router, "rtp", run_in_threadpool_inline)
    monkeypatch.setattr(
        users_router.auth_service,
        "get_user_by_id_in_tenant",
        lambda *_args: SimpleNamespace(username="target", role=Role.ADMIN),
    )

    with pytest.raises(HTTPException) as exc:
        await users_router.reset_user_password_temp("target-1", _admin_user())

    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_reset_temp_password_sends_email_when_target_email_exists(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(users_router, "rtp", run_in_threadpool_inline)
    monkeypatch.setattr(
        users_router.auth_service,
        "get_user_by_id_in_tenant",
        lambda *_args: SimpleNamespace(username="target", role=Role.USER),
    )
    monkeypatch.setattr(
        users_router.auth_service,
        "reset_user_password_temp",
        lambda *_args: {
            "temporary_password": "Temp1234",
            "target_email": "target@example.com",
            "target_username": "target-user",
        },
    )

    sent = []

    async def _send_temp_email(**kwargs):
        sent.append(kwargs)
        return True

    monkeypatch.setattr(users_router.notification_service, "send_temporary_password_email", _send_temp_email)

    result = await users_router.reset_user_password_temp("target-1", _admin_user())

    assert result.email_sent is True
    assert "delivered by email" in result.message
    assert sent[0]["recipient_email"] == "target@example.com"
    assert sent[0]["temporary_password"] == "Temp1234"


@pytest.mark.asyncio
async def test_reset_temp_password_returns_out_of_band_message_when_email_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(users_router, "rtp", run_in_threadpool_inline)
    monkeypatch.setattr(
        users_router.auth_service,
        "get_user_by_id_in_tenant",
        lambda *_args: SimpleNamespace(username="target", role=Role.USER),
    )
    monkeypatch.setattr(
        users_router.auth_service,
        "reset_user_password_temp",
        lambda *_args: {
            "temporary_password": "Temp1234",
            "target_email": "",
            "target_username": "target-user",
        },
    )

    called = {"email": 0}

    async def _send_temp_email(**_kwargs):
        called["email"] += 1
        return True

    monkeypatch.setattr(users_router.notification_service, "send_temporary_password_email", _send_temp_email)

    result = await users_router.reset_user_password_temp("target-1", _admin_user())

    assert result.email_sent is False
    assert "secure out-of-band channel" in result.message
    assert called["email"] == 0
