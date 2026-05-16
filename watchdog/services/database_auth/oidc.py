"""
Database authentication service utilities for handling OpenID Connect (OIDC) user synchronization and provisioning.

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

from config import config
from custom_types.json import JSONDict
from database import get_db_session
from db_models import Tenant, User
from models.access.auth_models import Permission, Role
from services.database_auth.audit import AuditLogRecord
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

if TYPE_CHECKING:
    from services.database_auth_service import DatabaseAuthService


@dataclass(frozen=True, slots=True)
class OidcProvisionProfile:
    email: str
    preferred_username: str
    full_name: str | None
    subject: str
    default_tenant: Tenant | None = None


@dataclass(frozen=True, slots=True)
class ExistingUserLookupContext:
    email: str
    subject: str
    tenant_id: str | None
    claims: JSONDict


@dataclass(frozen=True, slots=True)
class OidcUserUpdateProfile:
    email: str
    full_name: str | None
    subject: str


MAX_OIDC_CLAIM_LIST_ITEMS = 256
MAX_OIDC_CLAIM_ITEM_LENGTH = 200
MAX_USERNAME_COLLISION_PROBES = 5000
ALLOWED_OIDC_PERMISSION_VALUES = {perm.value for perm in Permission}


def _claim_str(claims: JSONDict, key: str) -> str:
    value = claims.get(key)
    return value.strip() if isinstance(value, str) else ""


def extract_permissions_from_oidc_claims(claims: JSONDict) -> list[str]:
    extracted = _normalize_claim_list(claims.get("permissions"))
    extracted |= _normalize_claim_list(claims.get("scp"))
    return sorted(p for p in extracted if p in ALLOWED_OIDC_PERMISSION_VALUES)


def _normalize_claim_list(value: object) -> set[str]:
    if not isinstance(value, list):
        return set()
    out: set[str] = set()
    for item in value:
        if len(out) >= MAX_OIDC_CLAIM_LIST_ITEMS:
            break
        s = str(item).strip()
        if s and len(s) <= MAX_OIDC_CLAIM_ITEM_LENGTH:
            out.add(s)
    return out


def _claim_truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    if isinstance(value, (int, float)):
        return value != 0
    return False


def _can_auto_link_by_email(claims: JSONDict) -> bool:
    enabled = _claim_truthy(getattr(config, "OIDC_AUTO_LINK_BY_EMAIL", False))
    if not enabled:
        return False

    expected_issuer = str(getattr(config, "OIDC_ISSUER_URL", "") or "").strip().rstrip("/")
    if expected_issuer:
        token_issuer = _claim_str(claims, "iss").rstrip("/")
        if not token_issuer or token_issuer != expected_issuer:
            return False

    require_verified = _claim_truthy(getattr(config, "OIDC_REQUIRE_VERIFIED_EMAIL_FOR_LINK", True))
    return _claim_truthy(claims.get("email_verified")) if require_verified else True


def _normalize_email(claims: JSONDict) -> str:
    return _claim_str(claims, "email").lower()


def _normalize_subject(claims: JSONDict) -> str:
    return _claim_str(claims, "sub")


def _preferred_username(claims: JSONDict, email: str) -> str:
    raw = _claim_str(claims, "preferred_username").lower()
    if raw:
        return raw
    return email.split("@", 1)[0].strip().lower()


def _full_name(claims: JSONDict) -> str | None:
    name = _claim_str(claims, "name")
    return name or None


def _get_user_by_subject(db: Session, subject: str, tenant_id: str | None) -> User | None:
    if not subject or not tenant_id:
        return None
    return db.query(User).filter(User.tenant_id == tenant_id, User.external_subject == subject).first()


def _get_user_by_email(db: Session, email: str, tenant_id: str | None) -> User | None:
    if not email or not tenant_id:
        return None
    return db.query(User).filter(User.tenant_id == tenant_id, func.lower(User.email) == email).first()


def _subject_is_owned_by_other(db: Session, subject: str, user_id: str) -> bool:
    if not subject:
        return False
    return db.query(User).filter(User.external_subject == subject, User.id != user_id).first() is not None


def _resolve_existing_user(
    service: DatabaseAuthService,
    db: Session,
    context: ExistingUserLookupContext,
) -> User | None:
    resolved = _get_user_by_subject(db, context.subject, context.tenant_id)
    if resolved is None:
        candidate = _get_user_by_email(db, context.email, context.tenant_id)
        if candidate is not None:
            if candidate.auth_provider == config.AUTH_PROVIDER:
                existing_subject = str(getattr(candidate, "external_subject", "") or "").strip()
                if existing_subject and context.subject and existing_subject != context.subject:
                    service.logger.warning(
                        "OIDC subject mismatch for existing external account %s; refusing login",
                        candidate.id,
                    )
                else:
                    resolved = candidate
            else:
                auto_link_allowed = _can_auto_link_by_email(context.claims)
                subject_available = not context.subject or not _subject_is_owned_by_other(
                    db,
                    context.subject,
                    candidate.id,
                )
                if not auto_link_allowed:
                    service.logger.warning(
                        "OIDC email %s matches existing account with auth_provider=%s; refusing link",
                        context.email,
                        candidate.auth_provider,
                    )
                elif not subject_available:
                    service.logger.warning(
                        "OIDC subject %s is already linked to another account; refusing link for email %s",
                        context.subject,
                        context.email,
                    )
                else:
                    resolved = candidate
    return resolved


def sync_user_from_oidc_claims(service: DatabaseAuthService, claims: JSONDict) -> User | None:
    service.ensure_initialized()

    email = _normalize_email(claims)
    subject = _normalize_subject(claims)
    user: User | None = None

    if not email:
        service.logger.warning("OIDC token missing email claim")
    else:
        preferred_username = _preferred_username(claims, email)
        full_name = _full_name(claims)

        with get_db_session() as db:
            default_tenant = db.query(Tenant).filter_by(name=config.DEFAULT_ADMIN_TENANT).first()
            if default_tenant is None and config.OIDC_AUTO_PROVISION_USERS:
                default_tenant = _ensure_default_tenant(db)
            tenant_id = getattr(default_tenant, "id", None)

            if tenant_id is None and not config.OIDC_AUTO_PROVISION_USERS:
                service.logger.warning(
                    "OIDC login denied because no default tenant exists and auto-provisioning is disabled"
                )
            else:
                user = _resolve_existing_user(
                    service,
                    db,
                    ExistingUserLookupContext(email=email, subject=subject, tenant_id=tenant_id, claims=claims),
                )

                if user is None and config.OIDC_AUTO_PROVISION_USERS:
                    profile = OidcProvisionProfile(
                        email=email,
                        preferred_username=preferred_username,
                        full_name=full_name,
                        subject=subject,
                        default_tenant=default_tenant,
                    )
                    try:
                        user = provision_oidc_user(service, db, profile)
                    except ValueError as exc:
                        service.logger.warning("OIDC provisioning failed for email=%s: %s", email, exc)
                        user = None
                elif user is not None:
                    if user.is_active:
                        update_oidc_user(
                            service,
                            db,
                            user,
                            OidcUserUpdateProfile(email=email, full_name=full_name, subject=subject),
                        )
                    else:
                        service.logger.warning("OIDC login attempted for inactive user %s", user.id)
                        user = None

                if user is not None:
                    user.last_login = datetime.now(UTC)
                    db.commit()
                    db.refresh(user)
    return user


def _ensure_default_tenant(db: Session) -> Tenant:
    tenant = db.query(Tenant).filter_by(name=config.DEFAULT_ADMIN_TENANT).first()
    if tenant:
        return tenant

    tenant = Tenant(
        name=config.DEFAULT_ADMIN_TENANT,
        display_name="Default Organization",
        is_active=True,
    )
    try:
        with db.begin_nested():
            db.add(tenant)
            db.flush()
            return tenant
    except IntegrityError:
        existing = db.query(Tenant).filter_by(name=config.DEFAULT_ADMIN_TENANT).first()
        if existing:
            return existing
        raise


def _base_username(preferred_username: str, email: str) -> str:
    base = (preferred_username or "").strip().lower()
    return base or email.split("@", 1)[0].strip().lower()


def _username_exists(db: Session, username: str) -> bool:
    return db.query(User).filter(func.lower(User.username) == username.lower()).first() is not None


def _pick_unique_username(db: Session, base: str) -> str:
    candidate = base
    if not _username_exists(db, candidate):
        return candidate

    for suffix in range(1, MAX_USERNAME_COLLISION_PROBES + 1):
        candidate = f"{base}{suffix}"
        if not _username_exists(db, candidate):
            return candidate

    raise ValueError("Unable to allocate unique username for OIDC provisioning")


def provision_oidc_user(
    service: DatabaseAuthService,
    db: Session,
    profile: OidcProvisionProfile,
) -> User:
    tenant = profile.default_tenant or _ensure_default_tenant(db)

    base = _base_username(profile.preferred_username, profile.email)
    must_setup_mfa = _claim_truthy(getattr(config, "OIDC_REQUIRE_MFA_FOR_MEMBERS", False)) or _claim_truthy(
        getattr(config, "REQUIRE_MFA_FOR_NEW_USERS", False)
    )

    for _ in range(3):
        username = _pick_unique_username(db, base)
        user = User(
            tenant_id=tenant.id,
            username=username,
            email=profile.email,
            full_name=profile.full_name,
            org_id=config.DEFAULT_ORG_ID,
            role=Role.PROVISIONING,
            is_active=True,
            is_superuser=False,
            hashed_password=service.hash_password(secrets.token_urlsafe(24)),
            # OIDC users authenticate externally; local bootstrap is unnecessary.
            needs_password_change=False,
            password_changed_at=datetime.now(UTC),
            must_setup_mfa=must_setup_mfa,
            auth_provider=config.AUTH_PROVIDER,
            external_subject=profile.subject or None,
        )
        try:
            with db.begin_nested():
                db.add(user)
                db.flush()
                service.ensure_default_api_key(db, user)
                return user
        except IntegrityError:
            continue

    raise ValueError("Failed to provision user due to repeated uniqueness conflicts")


def update_oidc_user(
    service: DatabaseAuthService,
    db: Session,
    user: User,
    profile: OidcUserUpdateProfile,
) -> None:
    user.auth_provider = config.AUTH_PROVIDER

    require_oidc_mfa = _claim_truthy(getattr(config, "OIDC_REQUIRE_MFA_FOR_MEMBERS", False)) or _claim_truthy(
        getattr(config, "REQUIRE_MFA_FOR_NEW_USERS", False)
    )
    if not require_oidc_mfa and getattr(user, "must_setup_mfa", False) and not getattr(user, "mfa_enabled", False):
        user.must_setup_mfa = False

    if profile.subject and user.external_subject != profile.subject:
        conflict = (
            db.query(User)
            .filter(
                User.external_subject == profile.subject,
                User.id != user.id,
            )
            .first()
        )
        if not conflict:
            previous_subject = str(user.external_subject or "")
            user.external_subject = profile.subject
            service.log_audit(
                db,
                AuditLogRecord(
                    tenant_id=user.tenant_id,
                    user_id=user.id,
                    action="oidc.subject_update",
                    resource_type="users",
                    resource_id=user.id,
                    details={
                        "previous_subject_present": bool(previous_subject),
                        "subject_updated": True,
                    },
                ),
            )

    if profile.email and user.email.lower() != profile.email:
        conflict = (
            db.query(User)
            .filter(
                func.lower(User.email) == profile.email,
                User.id != user.id,
            )
            .first()
        )
        if not conflict:
            previous_email = str(user.email)
            user.email = profile.email
            service.log_audit(
                db,
                AuditLogRecord(
                    tenant_id=user.tenant_id,
                    user_id=user.id,
                    action="oidc.email_update",
                    resource_type="users",
                    resource_id=user.id,
                    details={
                        "previous_email": previous_email,
                        "new_email": profile.email,
                    },
                ),
            )

    if profile.full_name is not None and user.full_name != profile.full_name:
        user.full_name = profile.full_name
