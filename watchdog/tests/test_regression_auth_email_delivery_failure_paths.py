"""
Regression tests for auth workflows when email delivery succeeds or fails.
"""

from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

import pytest

try:
    from ._env import ensure_test_env
except ImportError:
    from tests._env import ensure_test_env

ensure_test_env()

from models.access.auth_models import Permission, Role
from models.access.user_models import RegisterRequest
from routers.access.auth_router import authentication as auth_router
from routers.access.auth_router import users as users_router
from tests._regression_helpers import request_obj, run_in_threadpool_inline, token_data


@contextmanager
def _tenant_session(tenant_id: str | None):
    class _Query:
        def filter_by(self, **_kwargs):
            return self

        def first(self):
            return SimpleNamespace(id=tenant_id) if tenant_id else None

    class _DB:
        def query(self, *_args, **_kwargs):
            return _Query()

    yield _DB()


@pytest.mark.asyncio
async def test_register_returns_user_response_even_when_welcome_email_returns_false(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth_router, "rtp", run_in_threadpool_inline)
    monkeypatch.setattr(auth_router, "rate_limit_func", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(auth_router.auth_service, "is_external_auth_enabled", lambda: False)
    monkeypatch.setattr(auth_router, "get_db_session", lambda: _tenant_session("tenant-1"))

    user_obj = SimpleNamespace(username="new-user", email="new@example.com", full_name="New User", role=Role.USER)
    response_obj = SimpleNamespace(id="user-1", username="new-user", api_keys=[])

    monkeypatch.setattr(auth_router.auth_service, "create_user", lambda *_args: user_obj)
    monkeypatch.setattr(auth_router.auth_service, "build_user_response", lambda *_args: response_obj)

    async def _send_welcome_email(**_kwargs):
        return False

    monkeypatch.setattr(auth_router.notification_service, "send_user_welcome_email", _send_welcome_email)

    result = await auth_router.register(
        request_obj(),
        RegisterRequest(username="new-user", email="new@example.com", password="Password123", full_name="New User"),
    )

    assert result is response_obj


@pytest.mark.asyncio
async def test_reset_temp_password_returns_delivered_message_when_email_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
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

    async def _send_temp_email(**_kwargs):
        return True

    monkeypatch.setattr(users_router.notification_service, "send_temporary_password_email", _send_temp_email)

    actor = token_data(role=Role.ADMIN, permissions=[Permission.MANAGE_USERS.value])
    result = await users_router.reset_user_password_temp("target-1", actor)

    assert result.email_sent is True
    assert "delivered by email" in result.message


@pytest.mark.asyncio
async def test_reset_temp_password_returns_out_of_band_message_on_email_failure(monkeypatch: pytest.MonkeyPatch) -> None:
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

    async def _send_temp_email(**_kwargs):
        return False

    monkeypatch.setattr(users_router.notification_service, "send_temporary_password_email", _send_temp_email)

    actor = token_data(role=Role.ADMIN, permissions=[Permission.MANAGE_USERS.value])
    result = await users_router.reset_user_password_temp("target-1", actor)

    assert result.email_sent is False
    assert "secure out-of-band channel" in result.message


@pytest.mark.asyncio
async def test_reset_temp_password_uses_target_object_username_when_result_username_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(users_router, "rtp", run_in_threadpool_inline)

    target_user = SimpleNamespace(username="fallback-target", role=Role.USER)
    monkeypatch.setattr(users_router.auth_service, "get_user_by_id_in_tenant", lambda *_args: target_user)
    monkeypatch.setattr(
        users_router.auth_service,
        "reset_user_password_temp",
        lambda *_args: {
            "temporary_password": "Temp1234",
            "target_email": "target@example.com",
            "target_username": "",
        },
    )

    captured = {}

    async def _send_temp_email(**kwargs):
        captured.update(kwargs)
        return True

    monkeypatch.setattr(users_router.notification_service, "send_temporary_password_email", _send_temp_email)

    actor = token_data(role=Role.ADMIN, permissions=[Permission.MANAGE_USERS.value])
    await users_router.reset_user_password_temp("target-1", actor)

    assert captured["username"] == "fallback-target"


@pytest.mark.asyncio
async def test_reset_temp_password_skips_email_call_when_target_email_empty(monkeypatch: pytest.MonkeyPatch) -> None:
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

    actor = token_data(role=Role.ADMIN, permissions=[Permission.MANAGE_USERS.value])
    result = await users_router.reset_user_password_temp("target-1", actor)

    assert result.email_sent is False
    assert called["email"] == 0
