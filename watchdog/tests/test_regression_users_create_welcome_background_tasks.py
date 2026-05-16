"""
Copyright (c) 2026 Stefan Kumarasinghe.

Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the
License. You may obtain a copy of the License at
http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import pytest

try:
    from ._env import ensure_test_env
except ImportError:
    from tests._env import ensure_test_env

ensure_test_env()

from models.access.auth_models import Permission, Role
from models.access.user_models import UserCreate
from routers.access.auth_router import users as users_router
from tests._regression_helpers import run_in_threadpool_inline, token_data


@dataclass
class _BackgroundTasksStub:
    tasks: list[tuple[object, dict[str, object]]]

    def add_task(self, fn, **kwargs):
        self.tasks.append((fn, kwargs))


def _admin_user():
    return token_data(
        user_id="admin-1",
        username="admin",
        role=Role.ADMIN,
        permissions=[Permission.CREATE_USERS.value, Permission.MANAGE_USERS.value],
    )


def _user_create_payload() -> UserCreate:
    return UserCreate(username="new-user", email="new@example.com", password="Password123")


@pytest.mark.asyncio
async def test_create_user_schedules_welcome_email_task(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(users_router, "rtp", run_in_threadpool_inline)
    monkeypatch.setattr(
        users_router.auth_service,
        "create_user",
        lambda *_args: SimpleNamespace(
            username="new-user", email="new@example.com", full_name="New User", role=Role.USER
        ),
    )
    monkeypatch.setattr(users_router.auth_service, "build_user_response", lambda *_args: SimpleNamespace(api_keys=[]))
    monkeypatch.setattr(users_router, "invalidate_grafana_proxy_auth_cache", lambda: None)

    tasks = _BackgroundTasksStub(tasks=[])
    await users_router.create_user(_user_create_payload(), tasks, _admin_user())

    assert len(tasks.tasks) == 1
    assert tasks.tasks[0][0] == users_router.notification_service.send_user_welcome_email


@pytest.mark.asyncio
async def test_create_user_scheduled_task_contains_expected_kwargs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(users_router, "rtp", run_in_threadpool_inline)
    monkeypatch.setattr(
        users_router.auth_service,
        "create_user",
        lambda *_args: SimpleNamespace(
            username="new-user", email="new@example.com", full_name="New User", role=Role.USER
        ),
    )
    monkeypatch.setattr(users_router.auth_service, "build_user_response", lambda *_args: SimpleNamespace(api_keys=[]))
    monkeypatch.setattr(users_router, "invalidate_grafana_proxy_auth_cache", lambda: None)

    tasks = _BackgroundTasksStub(tasks=[])
    await users_router.create_user(_user_create_payload(), tasks, _admin_user())

    task_kwargs = tasks.tasks[0][1]
    email_request = task_kwargs["email_request"]
    assert email_request.recipient_email == "new@example.com"
    assert email_request.username == "new-user"
    assert email_request.full_name == "New User"


@pytest.mark.asyncio
async def test_create_user_passes_actor_caps_to_auth_service(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(users_router, "rtp", run_in_threadpool_inline)

    captured = {}

    def _create_user(user_create, tenant_id, actor_caps):
        captured["tenant_id"] = tenant_id
        captured["actor_caps"] = actor_caps
        captured["user_create"] = user_create
        return SimpleNamespace(username="new-user", email="new@example.com", full_name="New User", role=Role.USER)

    monkeypatch.setattr(users_router.auth_service, "create_user", _create_user)
    monkeypatch.setattr(users_router.auth_service, "build_user_response", lambda *_args: SimpleNamespace(api_keys=[]))
    monkeypatch.setattr(users_router, "invalidate_grafana_proxy_auth_cache", lambda: None)

    tasks = _BackgroundTasksStub(tasks=[])
    current_user = _admin_user()
    await users_router.create_user(_user_create_payload(), tasks, current_user)

    assert captured["tenant_id"] == current_user.tenant_id
    assert captured["actor_caps"].user_id == current_user.user_id
    assert captured["actor_caps"].is_superuser is False


@pytest.mark.asyncio
async def test_create_user_invalidates_proxy_cache_once(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(users_router, "rtp", run_in_threadpool_inline)
    monkeypatch.setattr(
        users_router.auth_service,
        "create_user",
        lambda *_args: SimpleNamespace(
            username="new-user", email="new@example.com", full_name="New User", role=Role.USER
        ),
    )
    monkeypatch.setattr(users_router.auth_service, "build_user_response", lambda *_args: SimpleNamespace(api_keys=[]))

    cache_calls = {"count": 0}

    def _invalidate_cache():
        cache_calls["count"] += 1

    monkeypatch.setattr(users_router, "invalidate_grafana_proxy_auth_cache", _invalidate_cache)

    tasks = _BackgroundTasksStub(tasks=[])
    await users_router.create_user(_user_create_payload(), tasks, _admin_user())

    assert cache_calls["count"] == 1


@pytest.mark.asyncio
async def test_create_user_returns_built_response(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(users_router, "rtp", run_in_threadpool_inline)
    monkeypatch.setattr(
        users_router.auth_service,
        "create_user",
        lambda *_args: SimpleNamespace(
            username="new-user", email="new@example.com", full_name="New User", role=Role.USER
        ),
    )
    response_obj = SimpleNamespace(id="user-1", username="new-user", api_keys=[])
    monkeypatch.setattr(users_router.auth_service, "build_user_response", lambda *_args: response_obj)
    monkeypatch.setattr(users_router, "invalidate_grafana_proxy_auth_cache", lambda: None)

    tasks = _BackgroundTasksStub(tasks=[])
    result = await users_router.create_user(_user_create_payload(), tasks, _admin_user())

    assert result is response_obj
