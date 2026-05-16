"""
User operations for managing user accounts, including creating, updating, deleting users, and managing user permissions
and group memberships.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the
License. You may obtain a copy of the License at
http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from fastapi import HTTPException, status
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session, joinedload

from config import config
from database import get_db_session
from db_models import Group, Permission, User
from models.access.auth_models import ROLE_PERMISSIONS, Role
from models.access.user_models import User as UserSchema
from models.access.user_models import UserCreate, UserUpdate
from services.auth.actor_caps import AuthActorCaps
from services.auth.delegation import (
    is_admin_actor as _is_admin_actor,
)
from services.auth.delegation import (
    is_admin_user as _is_admin_user,
)
from services.auth.delegation import (
    normalize_permissions as _normalize_permissions,
)
from services.auth.delegation import (
    permission_is_admin_only as _permission_is_admin_only,
)
from services.auth.delegation import (
    resolve_actor_permissions as _resolve_actor_permissions,
)
from services.auth.delegation import (
    role_rank as _shared_role_rank,
)
from services.auth.delegation import (
    role_to_text as _role_to_text,
)
from services.auth.group_ops import (
    _load_usernames_for_ids,
    _propagate_removed_member_group_shares,
    _prune_removed_member_grafana_group_shares,
)
from services.database_auth.audit import AuditLogRecord

if TYPE_CHECKING:
    from services.database_auth_service import DatabaseAuthService


MUTABLE_USER_FIELDS = {
    "username",
    "full_name",
    "email",
    "is_active",
    "role",
    "org_id",
    "must_setup_mfa",
    "needs_password_change",
}
SENSITIVE_USER_FIELDS = {"role", "org_id", "group_ids"}

ROLE_RANK = {
    Role.PROVISIONING.value: 0,
    Role.VIEWER.value: 1,
    Role.USER.value: 2,
    Role.ADMIN.value: 3,
}


@dataclass(frozen=True, slots=True)
class UserLoadOptions:
    with_groups: bool = False
    with_permissions: bool = False
    with_api_keys: bool = False


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _role_rank(value: object) -> int:
    return _shared_role_rank(value, ROLE_RANK)


def _get_user(
    db: Session,
    *,
    user_id: str,
    tenant_id: str,
    load: UserLoadOptions | None = None,
) -> User | None:
    options = load or UserLoadOptions()
    opts = []
    if options.with_groups:
        opts.append(joinedload(User.groups))
    if options.with_permissions:
        opts.append(joinedload(User.permissions))
    if options.with_api_keys:
        opts.append(joinedload(User.api_keys))
    q = db.query(User).filter_by(id=user_id, tenant_id=tenant_id)
    if opts:
        q = q.options(*opts)
    return q.first()


def _enforce_permission_delegation(
    *,
    requested_permissions: set[str],
    actor_permissions: set[str],
    actor_role: str | None,
    actor_is_superuser: bool,
) -> None:
    if actor_is_superuser:
        return

    actor_is_admin = _is_admin_actor(actor_role=actor_role, actor_is_superuser=False)

    if not requested_permissions.issubset(actor_permissions):
        forbidden = sorted(requested_permissions - actor_permissions)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Cannot grant permissions outside your own scope: {forbidden}",
        )

    if actor_is_admin:
        return

    privileged = sorted(p for p in requested_permissions if _permission_is_admin_only(p))
    if privileged:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Only administrators can grant privileged permissions: {privileged}",
        )


def _role_default_permissions(role_value: str) -> set[str]:
    role_text = _role_to_text(role_value)
    try:
        role_enum = Role(role_text)
    except ValueError:
        return set()
    return {
        str(getattr(perm, "value", perm)).strip()
        for perm in (ROLE_PERMISSIONS.get(role_enum) or [])
        if str(getattr(perm, "value", perm)).strip()
    }


def _resolve_create_user_actor_context(
    service: DatabaseAuthService,
    db: Session,
    *,
    user_create: UserCreate,
    tenant_id: str,
    actor: AuthActorCaps,
) -> tuple[str, str, bool, set[str]]:
    creator_id = actor.user_id
    actor_role = actor.role
    actor_permissions = actor.permissions
    actor_is_superuser = actor.is_superuser
    requested_role = _role_to_text(getattr(user_create, "role", None) or Role.USER.value)
    actor_role_text = _role_to_text(actor_role)

    if creator_id:
        creator = _get_user(db, user_id=creator_id, tenant_id=tenant_id)
        if not creator:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Creator account is not valid for this tenant",
            )
        if not actor_role_text:
            actor_role_text = _role_to_text(getattr(creator, "role", None))
        actor_is_superuser = bool(actor_is_superuser or getattr(creator, "is_superuser", False))
        actor_perm_set = _resolve_actor_permissions(
            service,
            db=db,
            actor_user_id=creator_id,
            tenant_id=tenant_id,
            actor_permissions=actor_permissions,
        )
    else:
        requested_role = Role.USER.value
        actor_role_text = Role.USER.value
        actor_perm_set = set()

    return requested_role, actor_role_text, actor_is_superuser, actor_perm_set


def _enforce_create_user_policy(
    *,
    user_create: UserCreate,
    requested_role: str,
    actor_role_text: str,
    actor_perm_set: set[str],
    actor_is_superuser: bool,
) -> None:
    actor_is_admin = _is_admin_actor(actor_role=actor_role_text, actor_is_superuser=actor_is_superuser)
    if actor_is_admin:
        return

    if _role_rank(requested_role) > _role_rank(actor_role_text):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot assign a role higher than your own",
        )
    if requested_role == Role.ADMIN.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can assign admin role",
        )
    if getattr(user_create, "group_ids", None):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can assign initial group memberships",
        )
    requested_org = str(getattr(user_create, "org_id", "") or "").strip()
    if requested_org and requested_org != config.DEFAULT_ORG_ID:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can assign tenant scope during user creation",
        )

    requested_role_defaults = _role_default_permissions(requested_role)
    _enforce_permission_delegation(
        requested_permissions=requested_role_defaults,
        actor_permissions=actor_perm_set,
        actor_role=actor_role_text,
        actor_is_superuser=actor_is_superuser,
    )


def _normalize_unique_user_identity(db: Session, user_create: UserCreate) -> tuple[str, str]:
    normalized_username = (user_create.username or "").strip().lower()
    if db.query(User).filter(func.lower(User.username) == normalized_username).first():
        raise ValueError("Username already exists")

    normalized_email = (user_create.email or "").strip().lower()
    if db.query(User).filter(func.lower(User.email) == normalized_email).first():
        raise ValueError("Email already exists")

    return normalized_username, normalized_email


def get_user_by_id(
    service: DatabaseAuthService, user_id: str, tenant_id: str | None = None, db: Session | None = None
) -> UserSchema | None:
    if not user_id:
        return None

    service.ensure_initialized()

    def _query(session: Session) -> UserSchema | None:
        q = (
            session.query(User)
            .options(
                joinedload(User.groups),
                joinedload(User.permissions),
                joinedload(User.api_keys),
            )
            .filter(User.id == user_id)
        )
        if tenant_id is not None:
            q = q.filter(User.tenant_id == tenant_id)

        user = q.first()
        return service.to_user_schema(user) if user else None

    if db is not None:
        return _query(db)

    with get_db_session() as s:
        return _query(s)


def get_user_by_username(service: DatabaseAuthService, username: str) -> UserSchema | None:
    service.ensure_initialized()
    username = (username or "").strip().lower()
    with get_db_session() as db:
        user = db.query(User).options(joinedload(User.api_keys)).filter(func.lower(User.username) == username).first()
        if not user:
            return None
        return UserSchema.model_validate(service.to_user_schema(user))


def create_user(
    service: DatabaseAuthService,
    user_create: UserCreate,
    tenant_id: str,
    actor: AuthActorCaps | None = None,
) -> UserSchema:
    actor = actor or AuthActorCaps()
    creator_id = actor.user_id

    service.ensure_initialized()
    with get_db_session() as db:
        requested_role, actor_role_text, actor_is_superuser, actor_perm_set = _resolve_create_user_actor_context(
            service,
            db,
            user_create=user_create,
            tenant_id=tenant_id,
            actor=actor,
        )
        _enforce_create_user_policy(
            user_create=user_create,
            requested_role=requested_role,
            actor_role_text=actor_role_text,
            actor_perm_set=actor_perm_set,
            actor_is_superuser=actor_is_superuser,
        )
        normalized_username, normalized_email = _normalize_unique_user_identity(db, user_create)

        is_external = service.is_external_auth_enabled()
        external_subject = None
        auth_provider = "local"

        if is_external:
            external_subject = service.provision_external_user(
                email=normalized_email,
                username=normalized_username,
                full_name=user_create.full_name,
            )
            if config.KEYCLOAK_USER_PROVISIONING_ENABLED and not external_subject:
                raise ValueError("External identity provisioning failed; user was not created")
            auth_provider = config.AUTH_PROVIDER

        raw_password = user_create.password
        if is_external and not raw_password:
            raw_password = secrets.token_urlsafe(24)
        if not raw_password:
            raise ValueError("Password is required when local authentication is enabled")

        org_value = config.DEFAULT_ORG_ID
        if _is_admin_actor(actor_role=actor_role_text, actor_is_superuser=actor_is_superuser):
            requested_org = str(getattr(user_create, "org_id", "") or "").strip()
            if requested_org:
                org_value = requested_org

        enforce_change = True
        user = User(
            tenant_id=tenant_id,
            username=normalized_username,
            email=normalized_email,
            full_name=user_create.full_name,
            org_id=org_value,
            role=requested_role,
            is_active=user_create.is_active,
            hashed_password=service.hash_password(raw_password),
            needs_password_change=enforce_change,
            password_changed_at=_now_utc(),
            auth_provider=auth_provider,
            external_subject=external_subject,
            must_setup_mfa=getattr(user_create, "must_setup_mfa", False),
        )

        if user_create.group_ids:
            groups = (
                db.query(Group).filter(and_(Group.id.in_(user_create.group_ids), Group.tenant_id == tenant_id)).all()
            )
            user.groups.extend(groups)

        db.add(user)
        db.flush()
        service.ensure_default_api_key(db, user)

        if creator_id:
            service.log_audit(
                db,
                AuditLogRecord(
                    tenant_id=tenant_id,
                    user_id=creator_id,
                    action="create_user",
                    resource_type="users",
                    resource_id=user.id,
                    details={"username": user.username, "role": user.role},
                ),
            )

        db.commit()
        return UserSchema.model_validate(service.to_user_schema(user))


def _validate_user_update_data(
    update_data: dict[str, object],
    *,
    updater_id: str | None,
    user_id: str,
) -> None:
    for field in ("username", "email", "org_id", "role", "is_active", "must_setup_mfa", "needs_password_change"):
        if field in update_data and update_data[field] is None:
            update_data.pop(field, None)

    if updater_id and user_id == updater_id:
        if update_data.get("is_active") is False:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You cannot disable your own account",
            )
        if set(update_data.keys()) & {"role", "group_ids", "org_id"}:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Users cannot change their own role, tenant scope, or group memberships",
            )


def _enforce_user_update_actor_policy(
    *,
    user: User,
    user_id: str,
    updater_id: str | None,
    updater_user: User | None,
    update_data: dict[str, object],
) -> None:
    updater_is_superuser = bool(getattr(updater_user, "is_superuser", False))
    updater_role_text = _role_to_text(getattr(updater_user, "role", ""))

    if _is_admin_user(user) and updater_user and updater_role_text != Role.ADMIN.value and not updater_is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can modify admin accounts",
        )

    if updater_user and not updater_is_superuser:
        if (SENSITIVE_USER_FIELDS & set(update_data.keys())) and updater_role_text != Role.ADMIN.value:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only administrators can modify role, tenant scope, or group memberships",
            )

        requested_role = update_data.get("role")
        if requested_role is not None and _role_rank(requested_role) > _role_rank(updater_role_text):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot assign a role higher than your own",
            )
        if _is_admin_user(user) and str(user_id) != str(updater_id) and (set(update_data.keys()) - {"is_active"}):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin accounts can only be activated or deactivated by another admin",
            )


def list_users(
    service: DatabaseAuthService,
    tenant_id: str,
    *,
    limit: int | None = None,
    offset: int = 0,
    q: str | None = None,
) -> list[UserSchema]:
    service.ensure_initialized()
    try:
        requested_limit = int(limit) if limit is not None else int(getattr(config, "DEFAULT_QUERY_LIMIT", 100))
        max_limit = int(getattr(config, "MAX_QUERY_LIMIT", 5000))
        limit = max(1, min(requested_limit, max_limit))
        offset = max(0, int(offset))
    except (TypeError, ValueError) as exc:
        raise ValueError("limit and offset must be integers") from exc

    with get_db_session() as db:
        query = (
            db.query(User).options(joinedload(User.groups), joinedload(User.api_keys)).filter_by(tenant_id=tenant_id)
        )
        query_text = str(q or "").strip()
        if query_text:
            pattern = f"%{query_text.lower()}%"
            query = query.filter(
                or_(
                    func.lower(func.coalesce(User.username, "")).like(pattern),
                    func.lower(func.coalesce(User.email, "")).like(pattern),
                    func.lower(func.coalesce(User.full_name, "")).like(pattern),
                )
            )
        users = query.limit(limit).offset(offset).all()
        return [service.to_user_schema(u) for u in users]


def update_user(
    service: DatabaseAuthService,
    user_id: str,
    user_update: UserUpdate,
    tenant_id: str,
    *,
    updater_id: str | None = None,
) -> UserSchema | None:
    service.ensure_initialized()
    with get_db_session() as db:
        user = _get_user(
            db,
            user_id=user_id,
            tenant_id=tenant_id,
            load=UserLoadOptions(with_groups=True, with_api_keys=True),
        )
        if not user:
            return None

        update_data = {
            k: v
            for k, v in user_update.model_dump(exclude_unset=True).items()
            if k in MUTABLE_USER_FIELDS or k == "group_ids"
        }
        _validate_user_update_data(update_data, updater_id=updater_id, user_id=user_id)
        updater_user = _get_user(db, user_id=updater_id, tenant_id=tenant_id) if updater_id else None
        _enforce_user_update_actor_policy(
            user=user,
            user_id=user_id,
            updater_id=updater_id,
            updater_user=updater_user,
            update_data=update_data,
        )

        if getattr(user, "auth_provider", "local") != "local" and "email" in update_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email is managed by the external identity provider",
            )

        if "username" in update_data:
            normalized_username = str(update_data.get("username") or "").strip().lower()
            if not normalized_username:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Username is required",
                )
            existing_username = (
                db.query(User)
                .filter(
                    func.lower(User.username) == normalized_username,
                    User.id != user.id,
                )
                .first()
            )
            if existing_username:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Username already exists",
                )
            update_data["username"] = normalized_username

        removed_group_ids: list[str] = []
        removed_usernames: list[str] = []
        requested_group_ids = update_data.pop("group_ids", None) if "group_ids" in update_data else None
        if requested_group_ids is not None:
            existing_group_ids = {str(g.id) for g in (user.groups or [])}
            groups = db.query(Group).filter(and_(Group.id.in_(requested_group_ids), Group.tenant_id == tenant_id)).all()
            user.groups = groups
            updated_group_ids = {str(g.id) for g in groups}
            removed_group_ids = sorted(existing_group_ids - updated_group_ids)
            if removed_group_ids:
                removed_usernames = _load_usernames_for_ids(db, tenant_id=tenant_id, user_ids=[user_id])
                for removed_group_id in removed_group_ids:
                    _prune_removed_member_grafana_group_shares(
                        db,
                        tenant_id=tenant_id,
                        group_id=removed_group_id,
                        removed_user_ids=[user_id],
                    )

        for field, value in update_data.items():
            setattr(user, field, value)

        user.updated_at = _now_utc()

        if "org_id" in update_data:
            service.ensure_default_api_key(db, user)

        audit_data = dict(update_data)
        if requested_group_ids is not None:
            audit_data["group_ids"] = [str(group.id) for group in (user.groups or [])]

        if updater_id:
            service.log_audit(
                db,
                AuditLogRecord(
                    tenant_id=tenant_id,
                    user_id=updater_id,
                    action="update_user",
                    resource_type="users",
                    resource_id=user_id,
                    details=audit_data,
                ),
            )

        db.commit()
        for removed_group_id in removed_group_ids:
            _propagate_removed_member_group_shares(
                tenant_id=tenant_id,
                group_id=removed_group_id,
                removed_user_ids=[user_id],
                removed_usernames=removed_usernames,
            )
        return UserSchema.model_validate(service.to_user_schema(user))


def set_grafana_user_id(user_id: str, grafana_user_id: int, tenant_id: str) -> bool:
    with get_db_session() as db:
        user = db.query(User).filter_by(id=user_id, tenant_id=tenant_id).first()
        if not user:
            return False
        user.grafana_user_id = grafana_user_id
        db.commit()
        return True


def delete_user(service: DatabaseAuthService, user_id: str, tenant_id: str, deleter_id: str | None = None) -> bool:
    service.ensure_initialized()
    if deleter_id and user_id == deleter_id:
        raise ValueError("Users cannot delete their own account")

    with get_db_session() as db:
        user = _get_user(db, user_id=user_id, tenant_id=tenant_id)
        if not user:
            return False

        if _is_admin_user(user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin accounts cannot be deleted",
            )

        deleter = _get_user(db, user_id=deleter_id, tenant_id=tenant_id) if deleter_id else None
        if deleter_id:
            if not deleter:
                return False
            if _role_to_text(getattr(deleter, "role", None)) != Role.ADMIN.value and not getattr(
                deleter, "is_superuser", False
            ):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Only administrators can delete users",
                )

            service.log_audit(
                db,
                AuditLogRecord(
                    tenant_id=tenant_id,
                    user_id=deleter_id,
                    action="delete_user",
                    resource_type="users",
                    resource_id=user_id,
                    details={"username": user.username},
                ),
            )

        db.delete(user)
        db.commit()
        return True


def update_user_permissions(
    service: DatabaseAuthService,
    user_id: str,
    permission_names: list[str],
    tenant_id: str,
    *,
    actor: AuthActorCaps | None = None,
) -> bool:
    actor = actor or AuthActorCaps()
    actor_user_id = actor.user_id
    actor_role = actor.role
    actor_permissions = actor.permissions
    actor_is_superuser = actor.is_superuser

    service.ensure_initialized()
    with get_db_session() as db:
        if not actor_user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Actor context is required for permission updates",
            )

        user = _get_user(db, user_id=user_id, tenant_id=tenant_id, load=UserLoadOptions(with_permissions=True))
        if not user:
            return False

        actor_user_row = _get_user(db, user_id=actor_user_id, tenant_id=tenant_id)
        if not actor_user_row:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Actor not found")
        if str(user_id) == str(actor_user_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Users cannot change their own permissions",
            )

        actor_role_text = _role_to_text(actor_role or getattr(actor_user_row, "role", None))
        actor_is_superuser = bool(actor_is_superuser or getattr(actor_user_row, "is_superuser", False))
        actor_perm_set = _resolve_actor_permissions(
            service,
            db=db,
            actor_user_id=actor_user_id,
            tenant_id=tenant_id,
            actor_permissions=actor_permissions,
        )

        if not _is_admin_actor(actor_role=actor_role_text, actor_is_superuser=actor_is_superuser):
            if _is_admin_user(user):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Only administrators can modify admin permissions",
                )
            if _role_rank(getattr(user, "role", None)) > _role_rank(actor_role_text):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Cannot modify permissions of users with higher role",
                )

        normalized_requested = _normalize_permissions(permission_names)
        existing_permissions = {
            str(getattr(p, "name", "")).strip() for p in (user.permissions or []) if str(getattr(p, "name", "")).strip()
        }

        requested_for_actor_scope = normalized_requested
        if not actor_is_superuser:
            existing_out_of_scope = existing_permissions - actor_perm_set
            requested_out_of_scope = normalized_requested - actor_perm_set
            if requested_out_of_scope != existing_out_of_scope:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Cannot modify permissions outside your own scope",
                )
            requested_for_actor_scope = normalized_requested & actor_perm_set

        _enforce_permission_delegation(
            requested_permissions=requested_for_actor_scope,
            actor_permissions=actor_perm_set,
            actor_role=actor_role_text,
            actor_is_superuser=actor_is_superuser,
        )

        known_names = {
            name for (name,) in db.query(Permission.name).filter(Permission.name.in_(normalized_requested)).all()
        }
        unknown = normalized_requested - known_names
        if unknown:
            raise ValueError(f"Unknown permissions: {sorted(unknown)}")

        permissions = db.query(Permission).filter(Permission.name.in_(known_names)).all()
        user.permissions = permissions

        service.log_audit(
            db,
            AuditLogRecord(
                tenant_id=tenant_id,
                user_id=actor_user_id,
                action="update_user_permissions",
                resource_type="users",
                resource_id=user_id,
                details={"permissions": sorted(known_names)},
            ),
        )
        db.commit()
        return True
