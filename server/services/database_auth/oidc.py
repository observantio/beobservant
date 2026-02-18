"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");

you may not use this file except in compliance with the License.

You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional

from sqlalchemy import func

from config import config
from database import get_db_session
from db_models import Tenant, User


def extract_permissions_from_oidc_claims(service, claims: Dict[str, any]) -> List[str]:
    extracted = set()
    scope_raw = claims.get("scope")
    if isinstance(scope_raw, str):
        extracted.update(p.strip() for p in scope_raw.split(" ") if p.strip())
    scp = claims.get("scp")
    if isinstance(scp, list):
        extracted.update(str(item).strip() for item in scp if str(item).strip())
    direct = claims.get("permissions")
    if isinstance(direct, list):
        extracted.update(str(item).strip() for item in direct if str(item).strip())
    return [v for v in extracted if ":" in v]


def sync_user_from_oidc_claims(service, claims: Dict[str, any]):
    email = (claims.get("email") or "").strip().lower()
    subject = (claims.get("sub") or "").strip()
    if not email:
        service.logger.warning("OIDC token missing email claim")
        return None

    preferred_username = (claims.get("preferred_username") or email.split("@", 1)[0] or "").strip().lower()
    full_name = (claims.get("name") or "").strip() or None

    with get_db_session() as db:
        user = (
            db.query(User).filter(User.external_subject == subject).first()
            if subject else None
        ) or db.query(User).filter(func.lower(User.email) == email).first()

        if not user:
            if not config.OIDC_AUTO_PROVISION_USERS:
                return None
            user = provision_oidc_user(service, db, email, preferred_username, full_name, subject)
        else:
            update_oidc_user(service, db, user, email, full_name, subject)

        user.last_login = datetime.now(timezone.utc)
        db.commit()
        db.refresh(user)
        return user


def provision_oidc_user(service, db, email: str, preferred_username: str, full_name: Optional[str], subject: str):
    default_tenant = db.query(Tenant).filter_by(name=config.DEFAULT_ADMIN_TENANT).first()
    if not default_tenant:
        default_tenant = Tenant(
            name=config.DEFAULT_ADMIN_TENANT,
            display_name="Default Organization",
            is_active=True,
        )
        db.add(default_tenant)
        db.flush()

    base = preferred_username or email.split("@", 1)[0]
    candidate, suffix = base, 1
    while db.query(User).filter(func.lower(User.username) == candidate.lower()).first():
        candidate = f"{base}{suffix}"
        suffix += 1

    from models.access.auth_models import Role

    user = User(
        tenant_id=default_tenant.id,
        username=candidate,
        email=email,
        full_name=full_name,
        org_id=config.DEFAULT_ORG_ID,
        role=Role.USER,
        is_active=True,
        is_superuser=False,
        hashed_password=service.hash_password(__import__('secrets').token_urlsafe(24)),
        needs_password_change=False,
        auth_provider=config.AUTH_PROVIDER,
        external_subject=subject or None,
    )
    db.add(user)
    db.flush()
    service._ensure_default_api_key(db, user)
    return user


def update_oidc_user(service, db, user, email: str, full_name: Optional[str], subject: str):
    user.auth_provider = config.AUTH_PROVIDER
    if subject:
        user.external_subject = subject
    if email and user.email.lower() != email:
        conflict = db.query(User).filter(
            (func.lower(User.email) == email) & (User.id != user.id)
        ).first()
        if not conflict:
            user.email = email
    if full_name and user.full_name != full_name:
        user.full_name = full_name
