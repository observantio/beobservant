"""
Database authentication service utilities for handling password hashing and verification operations.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the
License. You may obtain a copy of the License at
http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
import secrets
import string
import threading
from typing import Callable, Dict, TYPE_CHECKING, TypeVar

import bcrypt
from fastapi import HTTPException, status
from sqlalchemy.orm import Session, joinedload

from config import config
from database import get_db_session
from db_models import User
from models.access.auth_models import Role

from .audit import AuditLogRecord

if TYPE_CHECKING:
    from services.database_auth_service import DatabaseAuthService

T = TypeVar("T")
logger = logging.getLogger(__name__)
_FALLBACK_PASSWORD_LOCK = threading.BoundedSemaphore(1)
_PASSWORD_SEMAPHORE_STATE = {"warned_missing": False}


class PasswordResetResult(dict[str, str]):
    """Mapping with redacted repr to reduce accidental credential disclosure in logs."""

    def __repr__(self) -> str:
        return (
            "{"
            "'temporary_password': '***redacted***', "
            f"'target_email': {self.get('target_email')!r}, "
            f"'target_username': {self.get('target_username')!r}"
            "}"
        )

    __str__ = __repr__


def _with_password_semaphore(service: DatabaseAuthService, fn: Callable[[], T]) -> T:
    sem = getattr(service, "_password_op_semaphore", None)
    if sem:
        with sem:
            return fn()

    if not _PASSWORD_SEMAPHORE_STATE["warned_missing"]:
        logger.warning("Password semaphore missing; using process-wide fallback lock")
        _PASSWORD_SEMAPHORE_STATE["warned_missing"] = True

    with _FALLBACK_PASSWORD_LOCK:
        return fn()


def _bcrypt_rounds() -> int:
    raw = getattr(config, "BCRYPT_ROUNDS", None)
    try:
        rounds = int(raw) if raw is not None else 12
    except (TypeError, ValueError):
        rounds = 12
    return max(12, min(rounds, 15))


def hash_password(service: DatabaseAuthService, password: str) -> str:
    if not isinstance(password, str) or not password:
        raise ValueError("password must be a non-empty string")
    rounds = _bcrypt_rounds()

    def _hash() -> str:
        pw = password.encode("utf-8")
        if len(pw) > 72:
            raise ValueError("password must be 72 bytes or fewer when UTF-8 encoded")
        return bcrypt.hashpw(pw, bcrypt.gensalt(rounds=rounds)).decode("utf-8")

    return _with_password_semaphore(service, _hash)


def verify_password(service: DatabaseAuthService, plain_password: str, hashed_password: str) -> bool:
    if not isinstance(plain_password, str) or not plain_password:
        return False
    if not isinstance(hashed_password, str) or not hashed_password:
        return False

    hpw = hashed_password.encode("utf-8")

    def _verify() -> bool:
        try:
            pw = plain_password.encode("utf-8")
            if len(pw) > 72:
                return False
            return bcrypt.checkpw(pw, hpw)
        except (TypeError, ValueError):
            return False

    return _with_password_semaphore(service, _verify)


def _generate_temp_password(length: int) -> str:
    try:
        n = int(length)
    except (TypeError, ValueError):
        n = 20

    n = max(12, min(n, 64))

    alphabet = string.ascii_letters + string.digits + "!@#$%^&*()-_=+"
    return "".join(secrets.choice(alphabet) for _ in range(n))


def _is_admin_role(role_value: object) -> bool:
    s = str(getattr(role_value, "value", role_value) or "").strip().lower()
    return s in {Role.ADMIN.value, f"role.{Role.ADMIN.value}"}


def _actor_can_reset_password(actor: User) -> bool:
    if getattr(actor, "is_superuser", False):
        return True
    if _is_admin_role(getattr(actor, "role", "")):
        return True
    perms = getattr(actor, "permissions", None) or []
    names = {str(getattr(p, "name", "")).strip() for p in perms}
    return "manage:users" in names


def _require_user_in_tenant(db: Session, user_id: str, tenant_id: str, *, for_update: bool = False) -> User:
    query = db.query(User).filter_by(id=user_id, tenant_id=tenant_id)
    if for_update and hasattr(query, "with_for_update"):
        query = query.with_for_update()
    user = query.first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


def reset_user_password_temp(
    service: DatabaseAuthService, actor_user_id: str, target_user_id: str, tenant_id: str
) -> Dict[str, str]:
    with get_db_session() as db:
        actor_query = (
            db.query(User)
            .options(joinedload(User.permissions))
            .filter_by(id=actor_user_id, tenant_id=tenant_id)
        )
        actor = actor_query.first()
        if not actor:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Actor not permitted")

        if not _actor_can_reset_password(actor):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not permitted to reset passwords")

        target = _require_user_in_tenant(db, target_user_id, tenant_id, for_update=True)

        if _is_admin_role(getattr(target, "role", "")) or getattr(target, "is_superuser", False):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin account passwords cannot be reset",
            )

        previous_auth_provider = str(getattr(target, "auth_provider", "local") or "local")
        if previous_auth_provider != "local" and not getattr(actor, "is_superuser", False):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only superusers can reset externally managed accounts",
            )

        length = getattr(config, "TEMP_PASSWORD_LENGTH", 20)
        temporary_password = _generate_temp_password(length)

        now = datetime.now(timezone.utc)
        target.hashed_password = hash_password(service, temporary_password)
        target.auth_provider = "local"
        target.needs_password_change = True
        target.password_changed_at = now
        target.session_invalid_before = now

        service.log_audit(
            db,
            AuditLogRecord(
                tenant_id=tenant_id,
                user_id=actor_user_id,
                action="password.reset_temp",
                resource_type="users",
                resource_id=target_user_id,
                details={
                    "target_user_id": target_user_id,
                    "target_username": target.username,
                    "target_auth_provider_before": previous_auth_provider,
                    "target_auth_provider_after": target.auth_provider,
                    "temporary_password_issued": True,
                },
            ),
        )

        db.flush()
        db.commit()

        return PasswordResetResult(
            temporary_password=temporary_password,
            target_email=target.email,
            target_username=target.username,
        )
