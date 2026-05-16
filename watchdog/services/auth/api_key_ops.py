"""API key management operations and OTLP token backfilling."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from config import config
from database import get_db_session
from db_models import ApiKeyShare, Group, HiddenApiKey, User, UserApiKey
from fastapi import HTTPException, status
from models.access.api_key_models import ApiKey, ApiKeyCreate, ApiKeyShareUser, ApiKeyUpdate
from services.auth.api_key_schema import ApiKeySchemaContext, api_key_to_schema, list_api_key_shares_in_session
from services.auth.time_utils import utcnow
from services.database_auth.audit import AuditLogRecord
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

if TYPE_CHECKING:
    from services.database_auth_service import DatabaseAuthService
BACKFILL_BATCH_SIZE, ORG_SCOPE_KEY_RE = 500, re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,199}$")

@dataclass(frozen=True, slots=True)
class ApiKeyShareReplaceRequest:
    tenant_id: str
    key_id: str
    user_ids: list[str]
    group_ids: list[str] | None = None


@dataclass(frozen=True, slots=True)
class ApiKeyUpdateContext:
    db: Session
    viewer: User
    user_id: str
    key_id: str
    api_key: UserApiKey
    key_update: ApiKeyUpdate


def _normalize_scope_key(raw: str | None) -> str | None:
    if raw is None:
        return None
    value = str(raw).strip()
    if not value:
        raise ValueError("API key value cannot be blank")
    if not ORG_SCOPE_KEY_RE.fullmatch(value):
        raise ValueError(
            "API key value must be 3-200 chars and contain only letters, numbers, dot, underscore, hyphen, or colon"
        )
    return value


def _require_user(db: Session, user_id: str) -> User:
    user = db.query(User).filter_by(id=user_id).first()
    if not user:
        raise ValueError("User not found")
    return user


def _require_user_in_tenant(db: Session, user_id: str, tenant_id: str) -> User:
    user = db.query(User).filter_by(id=user_id, tenant_id=tenant_id).first()
    if not user:
        raise ValueError("User not found")
    return user


def _require_api_key_in_tenant(db: Session, key_id: str, tenant_id: str) -> UserApiKey:
    api_key = db.query(UserApiKey).filter_by(id=key_id, tenant_id=tenant_id).first()
    if not api_key:
        raise ValueError("API key not found")
    return api_key


def _disable_other_enabled_keys(
    db: Session, user_id: str, tenant_id: str, now: datetime, *, exclude_key_id: str | None = None
) -> None:
    q = db.query(UserApiKey).filter(
        UserApiKey.user_id == user_id,
        UserApiKey.tenant_id == tenant_id,
        UserApiKey.is_enabled.is_(True),
    )
    if exclude_key_id is not None:
        q = q.filter(UserApiKey.id != exclude_key_id)
    q.update({"is_enabled": False, "updated_at": now})


def _set_org_id(user: User, new_org_id: str | None, now: datetime) -> None:
    if new_org_id is None:
        return
    if str(user.org_id or "") != str(new_org_id or ""):
        user.org_id = new_org_id
        user.updated_at = now


def _normalize_api_key_name(name: str | None) -> str:
    normalized = str(name or "").strip()
    if not normalized:
        raise ValueError("API key name is required")
    return normalized


def _assert_unique_api_key_name(
    db: Session,
    *,
    tenant_id: str,
    owner_user_id: str,
    name: str,
    exclude_key_id: str | None = None,
) -> None:
    query = db.query(UserApiKey.id).filter(
        UserApiKey.tenant_id == tenant_id,
        UserApiKey.user_id == owner_user_id,
        func.lower(UserApiKey.name) == name.lower(),
    )
    if exclude_key_id:
        query = query.filter(UserApiKey.id != exclude_key_id)
    if query.first():
        raise ValueError("API key name already exists")


def list_api_keys(service: DatabaseAuthService, user_id: str, show_hidden: bool = False) -> list[ApiKey]:
    service.ensure_initialized()
    with get_db_session() as db:
        viewer = db.query(User).filter_by(id=user_id).first()
        if not viewer:
            return []

        own_keys = (
            db.query(UserApiKey)
            .options(joinedload(UserApiKey.shares).joinedload(ApiKeyShare.shared_user), joinedload(UserApiKey.user))
            .filter(UserApiKey.user_id == user_id, UserApiKey.tenant_id == viewer.tenant_id)
            .order_by(UserApiKey.created_at.asc())
            .all()
        )

        shared_links = (
            db.query(ApiKeyShare)
            .options(
                joinedload(ApiKeyShare.api_key).joinedload(UserApiKey.shares).joinedload(ApiKeyShare.shared_user),
                joinedload(ApiKeyShare.api_key).joinedload(UserApiKey.user),
            )
            .filter(ApiKeyShare.shared_user_id == user_id, ApiKeyShare.tenant_id == viewer.tenant_id)
            .all()
        )

        output: list[ApiKey] = []
        seen_ids = set()
        has_enabled_owned_key = any(bool(getattr(k, "is_enabled", False)) for k in own_keys)
        hidden_key_ids = {
            row.api_key_id
            for row in (
                db.query(HiddenApiKey.api_key_id)
                .filter(
                    HiddenApiKey.tenant_id == viewer.tenant_id,
                    HiddenApiKey.user_id == user_id,
                )
                .all()
            )
        }

        for owned_key in own_keys:
            is_hidden = getattr(owned_key, "id", None) in hidden_key_ids
            if is_hidden and not show_hidden:
                continue
            output.append(
                api_key_to_schema(
                    owned_key,
                    ApiKeySchemaContext(False, True, bool(getattr(owned_key, "is_enabled", False)), is_hidden),
                )
            )
            seen_ids.add(getattr(owned_key, "id", None))

        for link in shared_links:
            shared_key: UserApiKey | None = getattr(link, "api_key", None)
            if not shared_key:
                continue
            key_id = getattr(shared_key, "id", None)
            if key_id in seen_ids:
                continue

            can_use = bool(getattr(link, "can_use", True))
            viewer_enabled = bool(
                can_use
                and (not has_enabled_owned_key)
                and (str(viewer.org_id or "") == str(getattr(shared_key, "key", None) or ""))
            )
            is_hidden = key_id in hidden_key_ids
            if is_hidden and not show_hidden:
                continue
            output.append(api_key_to_schema(shared_key, ApiKeySchemaContext(True, can_use, viewer_enabled, is_hidden)))
            seen_ids.add(key_id)

        output.sort(key=lambda item: item.created_at)
        return output


def set_api_key_hidden(service: DatabaseAuthService, user_id: str, key_id: str, hidden: bool) -> bool:
    service.ensure_initialized()
    with get_db_session() as db:
        viewer = _require_user(db, user_id)
        api_key = _require_api_key_in_tenant(db, key_id, viewer.tenant_id)

        is_owner = str(getattr(api_key, "user_id", "")) == str(user_id)
        if is_owner:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You cannot hide your own API key",
            )

        share_link = (
            db.query(ApiKeyShare)
            .filter_by(
                api_key_id=key_id,
                shared_user_id=user_id,
                tenant_id=viewer.tenant_id,
            )
            .first()
        )
        if not share_link:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to manage hidden state for this API key",
            )

        existing = (
            db.query(HiddenApiKey)
            .filter_by(
                tenant_id=viewer.tenant_id,
                user_id=user_id,
                api_key_id=key_id,
            )
            .first()
        )
        if hidden:
            if not existing:
                db.add(
                    HiddenApiKey(
                        tenant_id=viewer.tenant_id,
                        user_id=user_id,
                        api_key_id=key_id,
                    )
                )
        elif existing:
            db.delete(existing)

        service.log_audit(
            db,
            AuditLogRecord(
                tenant_id=viewer.tenant_id,
                user_id=user_id,
                action="api_key.hide" if hidden else "api_key.unhide",
                resource_type="api_keys",
                resource_id=key_id,
                details={"hidden": bool(hidden)},
            ),
        )
        db.commit()
        return True


def create_api_key(service: DatabaseAuthService, user_id: str, tenant_id: str, key_create: ApiKeyCreate) -> ApiKey:
    service.ensure_initialized()
    with get_db_session() as db:
        user = _require_user_in_tenant(db, user_id, tenant_id)
        current_keys_count = (
            db.query(UserApiKey.id).filter(UserApiKey.user_id == user_id, UserApiKey.tenant_id == tenant_id).count()
        )
        if current_keys_count >= int(config.MAX_API_KEYS_PER_USER):
            raise ValueError(f"Maximum API key limit reached ({int(config.MAX_API_KEYS_PER_USER)})")
        normalized_name = _normalize_api_key_name(key_create.name)
        _assert_unique_api_key_name(
            db,
            tenant_id=tenant_id,
            owner_user_id=user_id,
            name=normalized_name,
        )

        requested_key = _normalize_scope_key(key_create.key)
        if requested_key:
            existing = db.query(UserApiKey).filter(UserApiKey.key == requested_key).first()
            if existing and str(existing.tenant_id) != str(tenant_id):
                raise ValueError("API key value is already assigned to another tenant")
            if existing and str(existing.tenant_id) == str(tenant_id):
                raise ValueError("API key value already exists in this tenant")
            key_value = requested_key
        else:
            key_value = str(uuid.uuid4())

        now = utcnow()
        _disable_other_enabled_keys(db, user_id=user_id, tenant_id=tenant_id, now=now)

        raw_otlp_token = service.generate_otlp_token()
        api_key = UserApiKey(
            tenant_id=tenant_id,
            user_id=user_id,
            name=normalized_name,
            key=key_value,
            otlp_token=None,
            otlp_token_hash=service.hash_otlp_token(raw_otlp_token),
            is_default=False,
            is_enabled=True,
        )
        db.add(api_key)

        try:
            db.flush()
        except IntegrityError as exc:
            db.rollback()
            raise ValueError("API key value already exists in this tenant") from exc

        user.org_id = api_key.key
        user.updated_at = now

        service.log_audit(
            db,
            AuditLogRecord(
                tenant_id=tenant_id,
                user_id=user_id,
                action="api_key.create",
                resource_type="api_keys",
                resource_id=api_key.id,
                details={"name": api_key.name},
            ),
        )
        db.commit()
        db.refresh(api_key)

        return api_key_to_schema(
            api_key,
            ApiKeySchemaContext(False, True, True, revealed_otlp_token=raw_otlp_token),
        )


def _update_shared_api_key_selection(service: DatabaseAuthService, ctx: ApiKeyUpdateContext) -> ApiKey:
    db = ctx.db
    share_link = (
        db.query(ApiKeyShare)
        .filter_by(
            api_key_id=ctx.key_id,
            shared_user_id=ctx.user_id,
            can_use=True,
            tenant_id=ctx.viewer.tenant_id,
        )
        .first()
    )
    if not share_link:
        raise ValueError("API key not found")

    requested_fields = ctx.key_update.model_dump(exclude_unset=True)
    if set(requested_fields.keys()) - {"is_enabled"}:
        raise ValueError("Shared API keys can only be selected as active")
    if ctx.key_update.is_enabled is not True:
        raise ValueError("Shared API key selection requires is_enabled=true")

    now = utcnow()
    _disable_other_enabled_keys(db, user_id=ctx.user_id, tenant_id=ctx.viewer.tenant_id, now=now)
    _set_org_id(ctx.viewer, getattr(ctx.api_key, "key", None), now)
    db.flush()

    service.log_audit(
        db,
        AuditLogRecord(
            tenant_id=ctx.viewer.tenant_id,
            user_id=ctx.user_id,
            action="api_key.use_shared",
            resource_type="api_keys",
            resource_id=ctx.api_key.id,
            details={"owner_user_id": ctx.api_key.user_id, "name": ctx.api_key.name},
        ),
    )
    db.commit()
    db.refresh(ctx.api_key)
    return api_key_to_schema(ctx.api_key, ApiKeySchemaContext(True, True, True))


def _update_owned_api_key_fields(ctx: ApiKeyUpdateContext, *, now: datetime) -> None:
    db = ctx.db
    if ctx.key_update.name is not None:
        normalized_name = _normalize_api_key_name(ctx.key_update.name)
        _assert_unique_api_key_name(
            db,
            tenant_id=ctx.viewer.tenant_id,
            owner_user_id=ctx.user_id,
            name=normalized_name,
            exclude_key_id=ctx.key_id,
        )
        ctx.api_key.name = normalized_name

    if ctx.key_update.is_default is not None and ctx.key_update.is_default:
        has_shares = (
            db.query(ApiKeyShare)
            .filter(ApiKeyShare.api_key_id == ctx.key_id, ApiKeyShare.tenant_id == ctx.viewer.tenant_id)
            .first()
            is not None
        )
        if has_shares:
            raise ValueError("Shared keys cannot be set as default. Remove shares first")
        db.query(UserApiKey).filter(
            UserApiKey.user_id == ctx.user_id,
            UserApiKey.tenant_id == ctx.viewer.tenant_id,
            UserApiKey.id != ctx.key_id,
            UserApiKey.is_default.is_(True),
        ).update({"is_default": False, "updated_at": now})
        _disable_other_enabled_keys(
            db,
            user_id=ctx.user_id,
            tenant_id=ctx.viewer.tenant_id,
            now=now,
            exclude_key_id=ctx.key_id,
        )
        ctx.api_key.is_default = True
        ctx.api_key.is_enabled = True
        owner = db.query(User).filter_by(id=ctx.user_id).first()
        if owner:
            _set_org_id(owner, getattr(ctx.api_key, "key", None), now)
        db.flush()

    if ctx.key_update.is_enabled is not None:
        if bool(getattr(ctx.api_key, "is_default", False)) and not ctx.key_update.is_enabled:
            raise ValueError("Default key cannot be disabled")
        if ctx.key_update.is_enabled:
            _disable_other_enabled_keys(
                db,
                user_id=ctx.user_id,
                tenant_id=ctx.viewer.tenant_id,
                now=now,
                exclude_key_id=ctx.key_id,
            )
            ctx.api_key.is_enabled = True
            _set_org_id(ctx.viewer, getattr(ctx.api_key, "key", None), now)
        else:
            replacement_key = (
                db.query(UserApiKey)
                .filter(
                    UserApiKey.user_id == ctx.user_id,
                    UserApiKey.tenant_id == ctx.viewer.tenant_id,
                    UserApiKey.id != ctx.key_id,
                )
                .order_by(
                    UserApiKey.is_default.desc(),
                    UserApiKey.is_enabled.desc(),
                    UserApiKey.updated_at.desc(),
                    UserApiKey.created_at.asc(),
                )
                .first()
            )
            if replacement_key is None:
                raise ValueError("At least one API key must be enabled")
            ctx.api_key.is_enabled = False
            db.flush()
            replacement_key.is_enabled = True
            replacement_key.updated_at = now
            _set_org_id(ctx.viewer, getattr(replacement_key, "key", None), now)


def update_api_key(service: DatabaseAuthService, user_id: str, key_id: str, key_update: ApiKeyUpdate) -> ApiKey:
    service.ensure_initialized()
    with get_db_session() as db:
        viewer = _require_user(db, user_id)
        api_key = _require_api_key_in_tenant(db, key_id, viewer.tenant_id)
        update_ctx = ApiKeyUpdateContext(
            db=db,
            viewer=viewer,
            user_id=user_id,
            key_id=key_id,
            api_key=api_key,
            key_update=key_update,
        )

        is_owner = str(getattr(api_key, "user_id", "")) == str(user_id)

        if not is_owner:
            return _update_shared_api_key_selection(service, update_ctx)

        now = utcnow()
        _update_owned_api_key_fields(update_ctx, now=now)

        api_key.updated_at = now

        service.log_audit(
            db,
            AuditLogRecord(
                tenant_id=api_key.tenant_id,
                user_id=user_id,
                action="api_key.update",
                resource_type="api_keys",
                resource_id=api_key.id,
                details=key_update.model_dump(exclude_unset=True),
            ),
        )
        db.commit()
        db.refresh(api_key)

        return api_key_to_schema(
            api_key,
            ApiKeySchemaContext(False, True, bool(api_key.is_enabled)),
        )


def regenerate_api_key_otlp_token(service: DatabaseAuthService, user_id: str, key_id: str) -> ApiKey:
    service.ensure_initialized()
    with get_db_session() as db:
        viewer = _require_user(db, user_id)
        api_key = _require_api_key_in_tenant(db, key_id, viewer.tenant_id)

        if str(getattr(api_key, "user_id", "")) != str(user_id):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to rotate API key token")
        if bool(getattr(api_key, "is_default", False)):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Default key OTLP token cannot be regenerated",
            )

        now = utcnow()
        raw_otlp_token = service.generate_otlp_token()
        api_key.otlp_token_hash = service.hash_otlp_token(raw_otlp_token)
        api_key.otlp_token = None
        api_key.updated_at = now

        service.log_audit(
            db,
            AuditLogRecord(
                tenant_id=api_key.tenant_id,
                user_id=user_id,
                action="api_key.rotate_otlp_token",
                resource_type="api_keys",
                resource_id=api_key.id,
                details={"name": api_key.name},
            ),
        )
        db.commit()
        db.refresh(api_key)

        return api_key_to_schema(
            api_key,
            ApiKeySchemaContext(False, True, bool(api_key.is_enabled), revealed_otlp_token=raw_otlp_token),
        )


def delete_api_key(service: DatabaseAuthService, user_id: str, key_id: str) -> bool:
    service.ensure_initialized()
    with get_db_session() as db:
        viewer = db.query(User).filter_by(id=user_id).first()
        if not viewer:
            return False

        api_key = db.query(UserApiKey).filter(UserApiKey.id == key_id, UserApiKey.tenant_id == viewer.tenant_id).first()
        if not api_key:
            return False

        if str(getattr(api_key, "user_id", "")) != str(user_id):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to delete API key")
        if bool(getattr(api_key, "is_default", False)):
            raise ValueError("Default key cannot be deleted")

        tenant_id = str(getattr(api_key, "tenant_id", "") or "")
        api_key_name = str(getattr(api_key, "name", "") or "")
        deleted_scope_key = str(getattr(api_key, "key", "") or "")

        db.delete(api_key)
        db.flush()

        enabled_count = (
            db.query(UserApiKey)
            .filter(
                UserApiKey.user_id == user_id,
                UserApiKey.tenant_id == tenant_id,
                UserApiKey.is_enabled.is_(True),
            )
            .count()
        )
        if enabled_count == 0:
            default_key = (
                db.query(UserApiKey)
                .filter(
                    UserApiKey.user_id == user_id,
                    UserApiKey.tenant_id == tenant_id,
                    UserApiKey.is_default.is_(True),
                )
                .first()
            )
            if default_key:
                default_key.is_enabled = True
                now = utcnow()
                default_key.updated_at = now
                if str(getattr(viewer, "org_id", "") or "") == deleted_scope_key:
                    _set_org_id(viewer, getattr(default_key, "key", None), now)

        service.log_audit(
            db,
            AuditLogRecord(
                tenant_id=tenant_id,
                user_id=user_id,
                action="api_key.delete",
                resource_type="api_keys",
                resource_id=key_id,
                details={"name": api_key_name},
            ),
        )
        db.commit()
        return True


def list_api_key_shares(
    service: DatabaseAuthService, owner_user_id: str, tenant_id: str, key_id: str
) -> list[ApiKeyShareUser]:
    service.ensure_initialized()
    with get_db_session() as db:
        api_key = db.query(UserApiKey).filter_by(id=key_id, user_id=owner_user_id, tenant_id=tenant_id).first()
        if not api_key:
            raise ValueError("API key not found")

        return list_api_key_shares_in_session(db, tenant_id=tenant_id, key_id=key_id)


def replace_api_key_shares(
    service: DatabaseAuthService,
    owner_user_id: str,
    request: ApiKeyShareReplaceRequest,
) -> list[ApiKeyShareUser]:
    tenant_id = request.tenant_id
    key_id = request.key_id
    user_ids = request.user_ids
    group_ids = request.group_ids
    service.ensure_initialized()
    with get_db_session() as db:
        api_key = db.query(UserApiKey).filter_by(id=key_id, user_id=owner_user_id, tenant_id=tenant_id).first()
        if not api_key:
            raise ValueError("API key not found")

        normalized_user_ids = list(
            dict.fromkeys(
                uid.strip() for uid in (user_ids or []) if uid and uid.strip() and uid.strip() != owner_user_id
            )
        )

        normalized_group_ids = [gid.strip() for gid in (group_ids or []) if gid and gid.strip()]
        member_user_ids_from_groups: list[str] = []

        if normalized_group_ids:
            groups = (
                db.query(Group)
                .options(joinedload(Group.members))
                .filter(
                    Group.tenant_id == tenant_id,
                    Group.id.in_(normalized_group_ids),
                    Group.is_active.is_(True),
                )
                .all()
            )
            found_group_ids = {str(g.id) for g in groups}
            missing_groups = sorted(set(normalized_group_ids) - found_group_ids)
            if missing_groups:
                raise ValueError("Invalid share groups: " + ", ".join(missing_groups))

            owner_group_ids = {
                str(g.id)
                for g in groups
                if any(str(getattr(m, "id", "")) == owner_user_id for m in (getattr(g, "members", None) or []))
            }
            unauthorized = sorted(found_group_ids - owner_group_ids)
            if unauthorized:
                raise ValueError("You can only share with groups you are in: " + ", ".join(unauthorized))

            for group in groups:
                for member in getattr(group, "members", None) or []:
                    if (
                        str(getattr(member, "id", "")) != owner_user_id
                        and bool(getattr(member, "is_active", False))
                        and str(getattr(member, "tenant_id", "")) == str(tenant_id)
                    ):
                        member_user_ids_from_groups.append(str(getattr(member, "id", "")))

        combined_user_ids = list(dict.fromkeys([*normalized_user_ids, *member_user_ids_from_groups]))

        if bool(getattr(api_key, "is_default", False)) and combined_user_ids:
            raise ValueError("Default key cannot be shared")

        if combined_user_ids:
            allowed_users = (
                db.query(User)
                .filter(User.tenant_id == tenant_id, User.id.in_(combined_user_ids), User.is_active.is_(True))
                .all()
            )
            allowed_user_ids = {str(u.id) for u in allowed_users}
            missing = sorted(set(combined_user_ids) - allowed_user_ids)
            if missing:
                raise ValueError("Invalid share users: " + ", ".join(missing))

        db.query(ApiKeyShare).filter(ApiKeyShare.api_key_id == key_id, ApiKeyShare.tenant_id == tenant_id).delete(
            synchronize_session=False
        )

        now = utcnow()
        for shared_user_id in combined_user_ids:
            db.add(
                ApiKeyShare(
                    tenant_id=tenant_id,
                    api_key_id=key_id,
                    owner_user_id=owner_user_id,
                    shared_user_id=shared_user_id,
                    can_use=True,
                    created_at=now,
                )
            )

        service.log_audit(
            db,
            AuditLogRecord(
                tenant_id=tenant_id,
                user_id=owner_user_id,
                action="api_key.share",
                resource_type="api_keys",
                resource_id=key_id,
                details={"shared_user_ids": combined_user_ids, "shared_group_ids": normalized_group_ids},
            ),
        )
        db.commit()
        return list_api_key_shares_in_session(db, tenant_id=tenant_id, key_id=key_id)


def delete_api_key_share(
    service: DatabaseAuthService,
    owner_user_id: str,
    tenant_id: str,
    key_id: str,
    *,
    shared_user_id: str,
) -> bool:
    service.ensure_initialized()
    with get_db_session() as db:
        api_key = db.query(UserApiKey).filter_by(id=key_id, user_id=owner_user_id, tenant_id=tenant_id).first()
        if not api_key:
            raise ValueError("API key not found")

        share = (
            db.query(ApiKeyShare)
            .filter(
                ApiKeyShare.api_key_id == key_id,
                ApiKeyShare.shared_user_id == shared_user_id,
                ApiKeyShare.tenant_id == tenant_id,
            )
            .first()
        )
        if not share:
            return False

        db.delete(share)
        service.log_audit(
            db,
            AuditLogRecord(
                tenant_id=tenant_id,
                user_id=owner_user_id,
                action="api_key.unshare",
                resource_type="api_keys",
                resource_id=key_id,
                details={"shared_user_id": shared_user_id},
            ),
        )
        db.commit()
        return True


def backfill_otlp_tokens(service: DatabaseAuthService) -> None:
    service.ensure_initialized()
    with get_db_session() as db:
        total = 0
        while True:
            batch = (
                db.query(UserApiKey)
                .filter(UserApiKey.otlp_token_hash.is_(None))
                .order_by(UserApiKey.id.asc())
                .limit(BACKFILL_BATCH_SIZE)
                .all()
            )
            if not batch:
                break

            now = utcnow()
            try:
                for key in batch:
                    source_token = getattr(key, "otlp_token", None) or service.generate_otlp_token()
                    key.otlp_token_hash = service.hash_otlp_token(source_token)
                    key.otlp_token = None
                    key.updated_at = now

                db.commit()
            except Exception:
                db.rollback()
                raise
            total += len(batch)

        if total:
            service.logger.info("Backfilled otlp_token_hash for %d API keys", total)
