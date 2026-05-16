"""
Schema transformations for API key related operations.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the
License. You may obtain a copy of the License at
http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from db_models import ApiKeyShare, UserApiKey
from models.access.api_key_models import ApiKey, ApiKeyShareUser
from sqlalchemy.orm import Session, joinedload


@dataclass(frozen=True, slots=True)
class ApiKeySchemaContext:
    is_shared: bool
    can_use: bool
    viewer_enabled: bool
    is_hidden: bool = False
    revealed_otlp_token: str | None = None


def share_created_at(share: ApiKeyShare) -> datetime:
    created_at = getattr(share, "created_at", None)
    return created_at if isinstance(created_at, datetime) else datetime.now(UTC)


def list_api_key_shares_in_session(db: Session, *, tenant_id: str, key_id: str) -> list[ApiKeyShareUser]:
    shares = (
        db.query(ApiKeyShare)
        .options(joinedload(ApiKeyShare.shared_user))
        .filter(ApiKeyShare.api_key_id == key_id, ApiKeyShare.tenant_id == tenant_id)
        .all()
    )

    return [
        ApiKeyShareUser(
            user_id=str(getattr(share, "shared_user_id", "")),
            username=getattr(getattr(share, "shared_user", None), "username", None),
            email=getattr(getattr(share, "shared_user", None), "email", None),
            can_use=bool(getattr(share, "can_use", True)),
            created_at=share_created_at(share),
        )
        for share in shares
    ]


def api_key_to_schema(
    api_key: UserApiKey,
    context: ApiKeySchemaContext,
) -> ApiKey:
    shared_with: list[ApiKeyShareUser] = []
    if not context.is_shared:
        for share in getattr(api_key, "shares", None) or []:
            shared_user = getattr(share, "shared_user", None)
            shared_with.append(
                ApiKeyShareUser(
                    user_id=str(getattr(share, "shared_user_id", "")),
                    username=getattr(shared_user, "username", None),
                    email=getattr(shared_user, "email", None),
                    can_use=bool(getattr(share, "can_use", True)),
                    created_at=share_created_at(share),
                )
            )

    owner_username = getattr(getattr(api_key, "user", None), "username", None)

    if context.is_shared:
        otlp_token_value = None
    else:
        otlp_token_value = (
            context.revealed_otlp_token
            if context.revealed_otlp_token is not None
            else getattr(api_key, "otlp_token", None)
        )

    payload = {
        "id": getattr(api_key, "id", None),
        "name": getattr(api_key, "name", None),
        "key": getattr(api_key, "key", None),
        "otlp_token": otlp_token_value,
        "owner_user_id": getattr(api_key, "user_id", None),
        "owner_username": owner_username,
        "is_shared": context.is_shared,
        "can_use": context.can_use,
        "shared_with": [s.model_dump() if hasattr(s, "model_dump") else s for s in shared_with],
        "is_default": bool(getattr(api_key, "is_default", False)),
        "is_enabled": bool(context.viewer_enabled),
        "is_hidden": bool(context.is_hidden),
        "created_at": getattr(api_key, "created_at", None),
        "updated_at": getattr(api_key, "updated_at", None),
    }
    return ApiKey.model_validate(payload)
