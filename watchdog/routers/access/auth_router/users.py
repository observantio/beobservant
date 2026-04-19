"""
User authentication and registration endpoints for Watchdog access management.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the
License. You may obtain a copy of the License at
http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

import re
from typing import List

from fastapi import BackgroundTasks, Body, Depends, HTTPException, Path, Query, status

from config import config
from middleware.dependencies import (
    apply_scoped_rate_limit,
    auth_service,
    require_any_permission,
    require_any_permission_with_scope,
    require_authenticated_with_scope,
)
from middleware.error_handlers import handle_route_errors
from models.access.auth_models import Permission, ROLE_PERMISSIONS, Role, TokenData
from models.access.user_models import (
    TempPasswordResetResponse,
    UserCreate,
    UserPasswordUpdate,
    UserResponse,
    UserUpdate,
)
from services.auth.actor_caps import AuthActorCaps
from services.auth.helper import (
    invalidate_grafana_proxy_auth_cache,
    is_admin_check,
    perms_check,
    role_permission_strings,
)
from services.notification_service import TemporaryPasswordEmailRequest, WelcomeEmailRequest
from .shared import USER_NOT_FOUND, notification_service, router, rtp
from .shared import SAFE_PATH_ID_PATTERN

_CONTROL_CHARS_RE = re.compile(r"[\x00-\x1F]")


def _sanitize_query_text(value: str | None) -> str:
    cleaned = _CONTROL_CHARS_RE.sub("", str(value or "")).strip()
    return cleaned[:200]


def _string_value(value: object) -> str:
    return value if isinstance(value, str) else ""


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: TokenData = Depends(require_authenticated_with_scope("auth")),
) -> UserResponse:
    user = await rtp(auth_service.get_user_by_id, current_user.user_id)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, USER_NOT_FOUND)
    user_response = await rtp(auth_service.build_user_response, user, current_user.permissions)
    user_response.api_keys = await rtp(auth_service.list_api_keys, current_user.user_id)
    return user_response


@router.put("/me", response_model=UserResponse)
@handle_route_errors()
async def update_current_user_info(
    user_update: UserUpdate,
    current_user: TokenData = Depends(require_authenticated_with_scope("auth")),
) -> UserResponse:
    data = user_update.model_dump(exclude_unset=True)
    for field in ("role", "group_ids", "is_active"):
        data.pop(field, None)
    updated = await rtp(
        auth_service.update_user,
        current_user.user_id,
        UserUpdate(**data),
        tenant_id=current_user.tenant_id,
        updater_id=current_user.user_id,
    )
    if not updated:
        raise HTTPException(status.HTTP_404_NOT_FOUND, USER_NOT_FOUND)
    user_response = await rtp(auth_service.build_user_response, updated, current_user.permissions)
    user_response.api_keys = await rtp(auth_service.list_api_keys, current_user.user_id)
    return user_response


@router.get("/users", response_model=List[UserResponse])
async def list_users(
    limit: int = Query(config.DEFAULT_QUERY_LIMIT, ge=1, le=config.MAX_QUERY_LIMIT),
    offset: int = Query(0, ge=0, le=1_000_000),
    current_user: TokenData = Depends(
        require_any_permission_with_scope(
            [Permission.READ_USERS, Permission.MANAGE_USERS, Permission.MANAGE_TENANTS],
            "auth",
        )
    ),
    q: str | None = Query(None),
) -> List[UserResponse]:
    query_text = _sanitize_query_text(q)
    if query_text:
        users = await rtp(
            auth_service.list_users,
            current_user.tenant_id,
            limit=limit,
            offset=offset,
            q=query_text,
        )
    else:
        users = await rtp(
            auth_service.list_users,
            current_user.tenant_id,
            limit=limit,
            offset=offset,
        )
    return [await rtp(auth_service.build_user_response, user, role_permission_strings(user.role)) for user in users]


@router.post("/users", response_model=UserResponse)
@handle_route_errors()
async def create_user(
    user_create: UserCreate,
    background_tasks: BackgroundTasks,
    current_user: TokenData = Depends(require_any_permission([Permission.CREATE_USERS, Permission.MANAGE_USERS])),
) -> UserResponse:
    apply_scoped_rate_limit(current_user, "auth")
    user = await rtp(
        auth_service.create_user,
        user_create,
        current_user.tenant_id,
        AuthActorCaps(
            user_id=current_user.user_id,
            role=current_user.role,
            permissions=list(perms_check(current_user)),
            is_superuser=bool(getattr(current_user, "is_superuser", False)),
        ),
    )
    background_tasks.add_task(
        notification_service.send_user_welcome_email,
        email_request=WelcomeEmailRequest(
            recipient_email=user.email,
            username=user.username,
            full_name=user.full_name,
            login_url=None,
        ),
    )
    invalidate_grafana_proxy_auth_cache()
    return await rtp(auth_service.build_user_response, user, role_permission_strings(user.role))


@router.put("/users/{user_id}", response_model=UserResponse)
@handle_route_errors()
async def update_user(
    user_id: str = Path(..., min_length=1, max_length=200, pattern=SAFE_PATH_ID_PATTERN),
    user_update: UserUpdate = Body(...),
    current_user: TokenData = Depends(
        require_any_permission_with_scope(
            [Permission.UPDATE_USERS, Permission.MANAGE_USERS, Permission.MANAGE_TENANTS], "auth"
        )
    ),
) -> UserResponse:
    perms = perms_check(current_user)
    is_admin = is_admin_check(current_user)
    can_manage = Permission.MANAGE_USERS.value in perms or Permission.UPDATE_USERS.value in perms
    update_fields = set(user_update.model_dump(exclude_unset=True).keys())

    if Permission.MANAGE_TENANTS.value in perms and not can_manage and not is_admin:
        if update_fields - {"is_active"}:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "manage:tenants can only activate/deactivate non-admin users"
            )

    if (update_fields & {"role", "org_id", "group_ids"}) and not is_admin:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Only administrators can modify role, tenant scope, or group memberships",
        )

    user = await rtp(
        auth_service.update_user,
        user_id,
        user_update,
        tenant_id=current_user.tenant_id,
        updater_id=current_user.user_id,
    )
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, USER_NOT_FOUND)
    if update_fields & {"role", "group_ids", "org_id", "is_active"}:
        invalidate_grafana_proxy_auth_cache()
    return await rtp(auth_service.build_user_response, user, role_permission_strings(user.role))


@router.put("/users/{user_id}/password")
@handle_route_errors()
async def update_user_password(
    password_update: UserPasswordUpdate,
    user_id: str = Path(..., min_length=1, max_length=200, pattern=SAFE_PATH_ID_PATTERN),
    current_user: TokenData = Depends(require_authenticated_with_scope("auth")),
) -> dict[str, str]:
    if current_user.user_id != user_id:
        perms = perms_check(current_user)
        if not (
            Permission.MANAGE_USERS.value in perms
            or Permission.UPDATE_USERS.value in perms
            or getattr(current_user, "is_superuser", False)
        ):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Cannot update another user's password")
    if not await rtp(auth_service.update_password, user_id, password_update, current_user.tenant_id):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is incorrect")
    return {"message": "Password updated successfully"}


@router.post("/users/{user_id}/password/reset-temp", response_model=TempPasswordResetResponse)
async def reset_user_password_temp(
    user_id: str = Path(..., min_length=1, max_length=200, pattern=SAFE_PATH_ID_PATTERN),
    current_user: TokenData = Depends(require_authenticated_with_scope("auth")),
) -> TempPasswordResetResponse:
    if not (is_admin_check(current_user) or Permission.MANAGE_USERS.value in perms_check(current_user)):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not permitted to reset passwords")

    target = await rtp(auth_service.get_user_by_id_in_tenant, user_id, current_user.tenant_id)
    if not target:
        raise HTTPException(status.HTTP_404_NOT_FOUND, USER_NOT_FOUND)
    if target.role == Role.ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin account passwords cannot be reset")

    result = await rtp(auth_service.reset_user_password_temp, current_user.user_id, user_id, current_user.tenant_id)
    temp_pw = _string_value(result.get("temporary_password", ""))
    email_sent = False
    target_email = _string_value(result.get("target_email"))
    target_username = _string_value(result.get("target_username"))
    if target_email:
        email_sent = await notification_service.send_temporary_password_email(
            email_request=TemporaryPasswordEmailRequest(
                recipient_email=target_email,
                username=target_username or target.username,
                temporary_password=temp_pw,
                login_url=None,
            )
        )
    return TempPasswordResetResponse(
        email_sent=bool(email_sent),
        message=(
            "Temporary password generated and delivered by email."
            if email_sent
            else "Temporary password generated. Deliver credentials through a secure out-of-band channel."
        ),
    )


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: str = Path(..., min_length=1, max_length=200, pattern=SAFE_PATH_ID_PATTERN),
    current_user: TokenData = Depends(require_authenticated_with_scope("auth")),
) -> dict[str, str]:
    if not is_admin_check(current_user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only administrators can delete users")
    if current_user.user_id == user_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cannot delete your own account")
    target = await rtp(auth_service.get_user_by_id_in_tenant, user_id, current_user.tenant_id)
    if target and target.role == Role.ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin accounts cannot be deleted")
    if not await rtp(auth_service.delete_user, user_id, current_user.tenant_id, current_user.user_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, USER_NOT_FOUND)
    invalidate_grafana_proxy_auth_cache()
    return {"message": "User deleted successfully"}


@router.put("/users/{user_id}/permissions")
async def update_user_permissions(
    user_id: str = Path(..., min_length=1, max_length=200, pattern=SAFE_PATH_ID_PATTERN),
    permission_names: List[str] = Body(...),
    current_user: TokenData = Depends(
        require_any_permission_with_scope([Permission.UPDATE_USER_PERMISSIONS, Permission.MANAGE_USERS], "auth")
    ),
) -> dict[str, object]:
    if not await rtp(
        auth_service.update_user_permissions,
        user_id,
        permission_names,
        tenant_id=current_user.tenant_id,
        actor=AuthActorCaps(
            user_id=current_user.user_id,
            role=current_user.role,
            permissions=list(perms_check(current_user)),
            is_superuser=bool(getattr(current_user, "is_superuser", False)),
        ),
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, USER_NOT_FOUND)
    invalidate_grafana_proxy_auth_cache()
    return {"success": True, "permissions": permission_names}


@router.get("/permissions")
async def list_all_permissions(
    current_user: TokenData = Depends(
        require_any_permission_with_scope(
            [Permission.READ_USERS, Permission.READ_GROUPS, Permission.MANAGE_USERS, Permission.MANAGE_GROUPS],
            "auth",
        )
    ),
) -> List[dict[str, object]]:
    all_permissions = await rtp(auth_service.list_all_permissions)
    if getattr(current_user, "is_superuser", False):
        return all_permissions

    allowed = set(perms_check(current_user))
    return [permission for permission in all_permissions if str(permission.get("name") or "") in allowed]


@router.get("/role-defaults")
async def list_role_defaults(
    current_user: TokenData = Depends(
        require_any_permission_with_scope(
            [Permission.READ_USERS, Permission.READ_GROUPS, Permission.MANAGE_USERS, Permission.MANAGE_GROUPS],
            "auth",
        )
    ),
) -> dict[str, List[str]]:
    defaults = {role.value: [permission.value for permission in perms] for role, perms in ROLE_PERMISSIONS.items()}
    if getattr(current_user, "is_superuser", False):
        return defaults

    allowed = set(perms_check(current_user))
    return {role: [permission for permission in perms if permission in allowed] for role, perms in defaults.items()}
