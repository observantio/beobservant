"""
Regression tests for permission matrix around temporary-password resets.
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


async def _prepare_success_path(monkeypatch: pytest.MonkeyPatch) -> None:
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
            "target_username": "target",
        },
    )

    async def _send_temp_email(**_kwargs):
        return True

    monkeypatch.setattr(users_router.notification_service, "send_temporary_password_email", _send_temp_email)


@pytest.mark.asyncio
async def test_admin_role_can_reset_user_password(monkeypatch: pytest.MonkeyPatch) -> None:
    await _prepare_success_path(monkeypatch)

    actor = token_data(user_id="admin-1", username="admin", role=Role.ADMIN, permissions=[])
    result = await users_router.reset_user_password_temp("target-1", actor)

    assert result.email_sent is True


@pytest.mark.asyncio
async def test_manage_users_permission_can_reset_user_password(monkeypatch: pytest.MonkeyPatch) -> None:
    await _prepare_success_path(monkeypatch)

    actor = token_data(
        user_id="manager-1",
        username="manager",
        role=Role.USER,
        permissions=[Permission.MANAGE_USERS.value],
    )
    result = await users_router.reset_user_password_temp("target-1", actor)

    assert result.email_sent is True


@pytest.mark.asyncio
async def test_superuser_can_reset_user_password_without_manage_permission(monkeypatch: pytest.MonkeyPatch) -> None:
    await _prepare_success_path(monkeypatch)

    actor = token_data(
        user_id="root-1",
        username="root",
        role=Role.USER,
        permissions=[],
        is_superuser=True,
    )
    result = await users_router.reset_user_password_temp("target-1", actor)

    assert result.email_sent is True


@pytest.mark.asyncio
async def test_manage_tenants_without_manage_users_cannot_reset_password(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(users_router, "rtp", run_in_threadpool_inline)

    actor = token_data(
        user_id="tenant-manager-1",
        username="tenant-manager",
        role=Role.USER,
        permissions=[Permission.MANAGE_TENANTS.value],
    )

    with pytest.raises(HTTPException) as exc:
        await users_router.reset_user_password_temp("target-1", actor)

    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_admin_actor_still_cannot_reset_admin_target(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(users_router, "rtp", run_in_threadpool_inline)
    monkeypatch.setattr(
        users_router.auth_service,
        "get_user_by_id_in_tenant",
        lambda *_args: SimpleNamespace(username="admin-target", role=Role.ADMIN),
    )

    actor = token_data(user_id="admin-1", username="admin", role=Role.ADMIN, permissions=[])

    with pytest.raises(HTTPException) as exc:
        await users_router.reset_user_password_temp("target-admin", actor)

    assert exc.value.status_code == 403
