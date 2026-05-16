"""
Copyright (c) 2026 Stefan Kumarasinghe.

Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the
License. You may obtain a copy of the License at
http://www.apache.org/licenses/LICENSE-2.0
"""

import sys
from pathlib import Path
from typing import Any

ROOT = str(Path(__file__).resolve().parent.parent)
if ROOT in sys.path:
    sys.path.remove(ROOT)
sys.path.insert(0, ROOT)

from tests._env import ensure_test_env

ensure_test_env()

import pytest
import sqlalchemy
from services.auth.actor_caps import AuthActorCaps
from services.database_auth_service import DatabaseAuthService
from sqlalchemy.engine import Engine

_ORIGINAL_CREATE_ENGINE = sqlalchemy.create_engine
_TRACKED_ENGINES: list[Engine] = []


def _tracking_create_engine(*args: Any, **kwargs: Any) -> Engine:
    engine = _ORIGINAL_CREATE_ENGINE(*args, **kwargs)
    _TRACKED_ENGINES.append(engine)
    return engine


sqlalchemy.create_engine = _tracking_create_engine


@pytest.fixture(autouse=True)
def _default_admin_create_user_actor(monkeypatch: pytest.MonkeyPatch) -> None:
    original_create_user = DatabaseAuthService.create_user

    def _create_user(self, user_create, tenant_id, actor=None, **kwargs):
        legacy_kwargs = dict(kwargs)
        legacy_creator_id = legacy_kwargs.pop("creator_id", None)
        legacy_actor_role = legacy_kwargs.pop("actor_role", None)
        legacy_actor_permissions = legacy_kwargs.pop("actor_permissions", None)
        legacy_actor_is_superuser = legacy_kwargs.pop("actor_is_superuser", False)
        if legacy_kwargs:
            unexpected = ", ".join(sorted(legacy_kwargs))
            raise TypeError(f"Unexpected create_user keyword arguments: {unexpected}")

        if actor is None and (
            legacy_creator_id is not None
            or legacy_actor_role is not None
            or legacy_actor_permissions is not None
            or legacy_actor_is_superuser
        ):
            actor = AuthActorCaps(
                user_id=legacy_creator_id,
                role=legacy_actor_role,
                permissions=list(legacy_actor_permissions) if legacy_actor_permissions is not None else None,
                is_superuser=bool(legacy_actor_is_superuser),
            )

        if actor is None:
            actor = AuthActorCaps(is_superuser=True)

        return original_create_user(self, user_create, tenant_id, actor)

    monkeypatch.setattr(DatabaseAuthService, "create_user", _create_user)


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    del session, exitstatus
    while _TRACKED_ENGINES:
        engine = _TRACKED_ENGINES.pop()
        try:
            engine.dispose()
        except Exception:
            continue
