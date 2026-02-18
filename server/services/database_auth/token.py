"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");

you may not use this file except in compliance with the License.

You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""
from typing import Optional

from models.access.auth_models import Role, TokenData
from services.auth.auth_ops import decode_token as decode_token_op


def build_token_data_for_user(service, user) -> TokenData:
    return TokenData(
        user_id=user.id,
        username=user.username,
        tenant_id=user.tenant_id,
        org_id=user.org_id,
        role=Role(user.role),
        is_superuser=user.is_superuser,
        permissions=service.get_user_permissions(user),
        group_ids=[g.id for g in (getattr(user, "groups", None) or [])],
    )


def decode_token(service, token: str) -> Optional[TokenData]:
    local_token = decode_token_op(service, token)
    if local_token:
        return local_token

    if not service.is_external_auth_enabled():
        return None

    claims = service.oidc_service.verify_access_token(token)
    if not claims:
        return None

    user = service._sync_user_from_oidc_claims(claims)
    if not user or not user.is_active:
        return None

    token_data = build_token_data_for_user(service, user)
    token_data.permissions = list(
        set(token_data.permissions) | set(service._extract_permissions_from_oidc_claims(claims))
    )
    return token_data
