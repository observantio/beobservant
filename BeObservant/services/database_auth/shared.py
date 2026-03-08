"""Shared helpers for database-backed auth flows."""

from __future__ import annotations

from typing import Any, Optional


def sync_active_user_from_claims(service, claims: Optional[dict[str, Any]]):
    if not claims:
        return None

    user = service._sync_user_from_oidc_claims(claims)
    if not user or not getattr(user, "is_active", False):
        return None
    return user
