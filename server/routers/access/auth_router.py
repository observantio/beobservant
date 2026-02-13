import logging
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status, Request

from config import config
from models.access.user_models import (
    LoginRequest, RegisterRequest, UserResponse,
    UserCreate, UserUpdate, UserPasswordUpdate
)
from models.access.group_models import (
    Group, GroupCreate, GroupUpdate, GroupMembersUpdate
)
from models.access.api_key_models import (
    ApiKey, ApiKeyCreate, ApiKeyUpdate
)
from models.access.auth_models import TokenData, Permission, Role, ROLE_PERMISSIONS, Token

from middleware.dependencies import (
    get_current_user,
    require_permission,
    require_any_permission_with_scope,
    auth_service,
    enforce_public_endpoint_security,
    require_authenticated_with_scope,
    require_permission_with_scope,
)
from middleware.error_handlers import handle_route_errors

logger = logging.getLogger(__name__)

USER_NOT_FOUND = "User not found"
GROUP_NOT_FOUND = "Group not found"

router = APIRouter(prefix="/api/auth", tags=["authentication"])


@router.post("/login", response_model=Token)
async def login(request: Request, login_request: LoginRequest):
    enforce_public_endpoint_security(
        request,
        scope="auth_login",
        limit=config.RATE_LIMIT_LOGIN_PER_MINUTE,
        window_seconds=60,
        allowlist=config.AUTH_PUBLIC_IP_ALLOWLIST,
    )
    user = auth_service.authenticate_user(login_request.username, login_request.password)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    token = auth_service.create_access_token(user)
    return token


@router.post("/register", response_model=UserResponse)
@handle_route_errors()
async def register(request: Request, register_request: RegisterRequest):
    enforce_public_endpoint_security(
        request,
        scope="auth_register",
        limit=config.RATE_LIMIT_REGISTER_PER_HOUR,
        window_seconds=3600,
        allowlist=config.AUTH_PUBLIC_IP_ALLOWLIST,
    )
    user_create = UserCreate(
        username=register_request.username,
        email=register_request.email,
        password=register_request.password,
        full_name=register_request.full_name
    )

    user = auth_service.create_user(user_create, tenant_id=config.DEFAULT_ORG_ID)

    return auth_service.build_user_response(user, fallback_permissions=ROLE_PERMISSIONS.get(user.role, []))


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: TokenData = Depends(require_authenticated_with_scope("auth"))):
    user = auth_service.get_user_by_id(current_user.user_id)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=USER_NOT_FOUND
        )
    
    return auth_service.build_user_response(user, fallback_permissions=current_user.permissions)


@router.put("/me", response_model=UserResponse)
async def update_current_user_info(
    user_update: UserUpdate,
    current_user: TokenData = Depends(require_authenticated_with_scope("auth"))
):
    update_data = user_update.model_dump(exclude_unset=True)
    for field in ("role", "group_ids", "is_active"):
        update_data.pop(field, None)
    user_update = UserUpdate(**update_data)
    updated_user = auth_service.update_user(
        current_user.user_id,
        user_update,
        current_user.tenant_id,
        updater_id=current_user.user_id,
    )

    if not updated_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=USER_NOT_FOUND)

    return auth_service.build_user_response(updated_user, fallback_permissions=current_user.permissions)


@router.get("/api-keys", response_model=List[ApiKey])
async def list_api_keys(current_user: TokenData = Depends(require_authenticated_with_scope("auth"))):
    return auth_service.list_api_keys(current_user.user_id)


@router.post("/api-keys", response_model=ApiKey)
@handle_route_errors()
async def create_api_key(
    key_create: ApiKeyCreate,
    current_user: TokenData = Depends(require_authenticated_with_scope("auth"))
):
    return auth_service.create_api_key(current_user.user_id, current_user.tenant_id, key_create)


@router.patch("/api-keys/{key_id}", response_model=ApiKey)
@handle_route_errors()
async def update_api_key(
    key_id: str,
    key_update: ApiKeyUpdate,
    current_user: TokenData = Depends(require_authenticated_with_scope("auth"))
):
    return auth_service.update_api_key(current_user.user_id, key_id, key_update)


@router.delete("/api-keys/{key_id}")
@handle_route_errors()
async def delete_api_key(
    key_id: str,
    current_user: TokenData = Depends(require_authenticated_with_scope("auth"))
):
    success = auth_service.delete_api_key(current_user.user_id, key_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")
    return {"message": "API key deleted"}


@router.get("/users", response_model=List[UserResponse])
async def list_users(
    current_user: TokenData = Depends(
        require_any_permission_with_scope([Permission.READ_USERS, Permission.MANAGE_USERS], "auth")
    )
):
    users = auth_service.list_users(current_user.tenant_id)
    return [auth_service.build_user_response(user, fallback_permissions=ROLE_PERMISSIONS.get(user.role, [])) for user in users]


@router.post("/users", response_model=UserResponse)
@handle_route_errors()
async def create_user(
    user_create: UserCreate,
    current_user: TokenData = Depends(
        require_any_permission_with_scope([Permission.CREATE_USERS, Permission.MANAGE_USERS], "auth")
    )
):
    user = auth_service.create_user(user_create, current_user.tenant_id)

    return auth_service.build_user_response(user, fallback_permissions=ROLE_PERMISSIONS.get(user.role, []))


@router.put("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: str,
    user_update: UserUpdate,
    current_user: TokenData = Depends(
        require_any_permission_with_scope([Permission.UPDATE_USERS, Permission.MANAGE_USERS], "auth")
    )
):
    user = auth_service.update_user(user_id, user_update, current_user.tenant_id, current_user.user_id)
    
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=USER_NOT_FOUND)
    
    return auth_service.build_user_response(user, fallback_permissions=ROLE_PERMISSIONS.get(user.role, []))


@router.put("/users/{user_id}/password")
@handle_route_errors()
async def update_user_password(
    user_id: str,
    password_update: UserPasswordUpdate,
    current_user: TokenData = Depends(require_authenticated_with_scope("auth"))
):
    if current_user.user_id != user_id:
        user_obj = auth_service.get_user_by_id(current_user.user_id)
        user_perms = auth_service.get_user_permissions(user_obj) if user_obj else (getattr(current_user, "permissions", []) or [])
        if (
            Permission.MANAGE_USERS.value not in user_perms
            and Permission.UPDATE_USERS.value not in user_perms
            and not getattr(current_user, "is_superuser", False)
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot update another user's password"
            )

    success = auth_service.update_password(user_id, password_update, current_user.tenant_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect"
        )

    return {"message": "Password updated successfully"}


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: str,
    current_user: TokenData = Depends(
        require_any_permission_with_scope([Permission.DELETE_USERS, Permission.MANAGE_USERS], "auth")
    )
):
    if current_user.user_id == user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete your own account"
        )

    target_user = auth_service.get_user_by_id(user_id)
    if target_user and target_user.role == Role.ADMIN and current_user.role != Role.ADMIN and not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can delete admin accounts"
        )
    success = auth_service.delete_user(user_id, current_user.tenant_id, current_user.user_id)

    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=USER_NOT_FOUND)

    return {"message": "User deleted successfully"}


@router.get("/groups", response_model=List[Group])
async def list_groups(current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_GROUPS, "auth"))):
    return auth_service.list_groups(current_user.tenant_id)


@router.post("/groups", response_model=Group)
async def create_group(
    group_create: GroupCreate,
    current_user: TokenData = Depends(
        require_any_permission_with_scope([Permission.CREATE_GROUPS, Permission.MANAGE_GROUPS], "auth")
    )
):
    return auth_service.create_group(group_create, current_user.tenant_id)


@router.get("/groups/{group_id}", response_model=Group)
async def get_group(
    group_id: str,
    current_user: TokenData = Depends(
        require_any_permission_with_scope([Permission.READ_GROUPS, Permission.MANAGE_GROUPS], "auth")
    )
):
    group = auth_service.get_group(group_id, current_user.tenant_id)
    
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=GROUP_NOT_FOUND)
    
    return group


@router.put("/groups/{group_id}", response_model=Group)
async def update_group(
    group_id: str,
    group_update: GroupUpdate,
    current_user: TokenData = Depends(
        require_any_permission_with_scope([Permission.UPDATE_GROUPS, Permission.MANAGE_GROUPS], "auth")
    )
):
    group = auth_service.update_group(group_id, group_update, current_user.tenant_id)
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=GROUP_NOT_FOUND)
    return group


@router.delete("/groups/{group_id}")
async def delete_group(
    group_id: str,
    current_user: TokenData = Depends(
        require_any_permission_with_scope([Permission.DELETE_GROUPS, Permission.MANAGE_GROUPS], "auth")
    )
):
    success = auth_service.delete_group(group_id, current_user.tenant_id)
    
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=GROUP_NOT_FOUND)
    
    return {"message": "Group deleted successfully"}


@router.put("/users/{user_id}/permissions")
async def update_user_permissions(
    user_id: str,
    permission_names: List[str],
    current_user: TokenData = Depends(
        require_any_permission_with_scope([Permission.UPDATE_USERS, Permission.MANAGE_USERS], "auth")
    )
):
    """Update user's direct permissions."""
    success = auth_service.update_user_permissions(user_id, permission_names, current_user.tenant_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=USER_NOT_FOUND)
    return {"success": True, "permissions": permission_names}


@router.put("/groups/{group_id}/permissions")
async def update_group_permissions(
    group_id: str,
    permission_names: List[str],
    current_user: TokenData = Depends(
        require_any_permission_with_scope([Permission.UPDATE_GROUPS, Permission.MANAGE_GROUPS], "auth")
    )
):
    """Update group's permissions."""
    success = auth_service.update_group_permissions(group_id, permission_names, current_user.tenant_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=GROUP_NOT_FOUND)
    return {"success": True, "permissions": permission_names}


@router.put("/groups/{group_id}/members")
async def update_group_members(
    group_id: str,
    members: GroupMembersUpdate,
    current_user: TokenData = Depends(
        require_any_permission_with_scope([Permission.UPDATE_GROUPS, Permission.MANAGE_GROUPS], "auth")
    )
):
    """Update group membership."""
    success = auth_service.update_group_members(group_id, members.user_ids, current_user.tenant_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=GROUP_NOT_FOUND)
    return {"success": True, "user_ids": members.user_ids}


@router.get("/permissions")
async def list_all_permissions(current_user: TokenData = Depends(require_authenticated_with_scope("auth"))):
    """List all available permissions."""
    return auth_service.list_all_permissions()


@router.get("/role-defaults")
async def list_role_defaults(current_user: TokenData = Depends(require_authenticated_with_scope("auth"))):
    """List role default permissions."""
    return {
        role.value: [perm.value for perm in perms]
        for role, perms in ROLE_PERMISSIONS.items()
    }
