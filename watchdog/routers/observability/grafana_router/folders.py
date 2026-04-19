"""
Folder management endpoints for Watchdog Grafana proxy router.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the
License. You may obtain a copy of the License at
http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from fastapi import Body, Depends, HTTPException, Query, Path
from sqlalchemy.orm import Session

from database import get_db
from middleware.dependencies import (
    require_any_permission_with_scope,
    require_authenticated_with_scope,
    require_permission_with_scope,
)
from middleware.error_handlers import handle_route_errors
from models.access.auth_models import Permission, TokenData
from models.grafana.grafana_folder_models import Folder
from models.observability.grafana_request_models import (
    GrafanaCreateFolderRequest,
    GrafanaHiddenToggleRequest,
    GrafanaUpdateFolderRequest,
)
from routers.observability.grafana_router.param_helpers import show_hidden_enabled
from services.grafana.grafana_bundles import (
    FolderCreateRequest as FolderCreateBundle,
    FolderDeleteRequest as FolderDeleteBundle,
    FolderGetRequest as FolderGetBundle,
    FolderCreateOptions,
    FolderDeleteOptions,
    FolderGetParams,
    FolderListParams,
    FolderUpdateRequest as FolderUpdateBundle,
    FolderUpdateOptions,
    GrafanaUserScope,
    HiddenToggleParams,
    HiddenToggleRequest,
)
from services.grafana.route_payloads import validate_visibility
from custom_types.json import JSONDict

from .shared import hidden_toggle_context, proxy, router, rtp, scope_context


@dataclass(frozen=True, slots=True)
class FolderUpdateRequest:
    uid: str
    payload: GrafanaUpdateFolderRequest


def _folder_update_request_dep(
    uid: str = Path(..., min_length=1, max_length=200, pattern=r"^[A-Za-z0-9_-]+$"),
    payload: GrafanaUpdateFolderRequest = Body(...),
) -> FolderUpdateRequest:
    return FolderUpdateRequest(uid=uid, payload=payload)


@router.get("/folders", response_model=List[Folder])
async def get_folders(
    show_hidden: str = Query("false", pattern=r"^(true|false)$"),
    current_user: TokenData = Depends(require_authenticated_with_scope("grafana")),
    db: Session = Depends(get_db),
) -> List[Folder]:
    user_id, tenant_id, group_ids, is_admin = scope_context(current_user)
    scope = GrafanaUserScope(user_id=user_id, tenant_id=tenant_id, group_ids=group_ids)
    params = FolderListParams(show_hidden=show_hidden_enabled(show_hidden), is_admin=is_admin)
    return await proxy.get_folders(db=db, scope=scope, params=params)


@router.get("/folders/{uid}", response_model=Folder)
async def get_folder_by_uid(
    uid: str = Path(..., min_length=1, max_length=200, pattern=r"^[A-Za-z0-9_-]+$"),
    current_user: TokenData = Depends(require_authenticated_with_scope("grafana")),
    db: Session = Depends(get_db),
) -> Folder:
    user_id, tenant_id, group_ids, is_admin = scope_context(current_user)
    folder = await proxy.get_folder(
        db=db,
        request=FolderGetBundle(
            uid=uid,
            scope=GrafanaUserScope(user_id=user_id, tenant_id=tenant_id, group_ids=group_ids),
            params=FolderGetParams(is_admin=is_admin),
        ),
    )
    if not folder:
        raise HTTPException(status_code=404, detail=f"Folder {uid} not found or access denied")
    return folder


@router.post("/folders", response_model=Folder)
@handle_route_errors()
async def create_folder(
    payload: GrafanaCreateFolderRequest,
    visibility: str = Query("private"),
    shared_group_ids: Optional[List[str]] = Query(None),
    *,
    current_user: TokenData = Depends(require_permission_with_scope(Permission.CREATE_FOLDERS, "grafana")),
    db: Session = Depends(get_db),
) -> Folder:
    validate_visibility(visibility)
    user_id, tenant_id, group_ids, is_admin = scope_context(current_user)
    result = await proxy.create_folder(
        db=db,
        request=FolderCreateBundle(
            title=payload.title,
            scope=GrafanaUserScope(user_id=user_id, tenant_id=tenant_id, group_ids=group_ids),
            options=FolderCreateOptions(
                visibility=visibility,
                shared_group_ids=shared_group_ids or [],
                allow_dashboard_writes=payload.allow_dashboard_writes,
                is_admin=is_admin,
            ),
        ),
    )
    if not result:
        raise HTTPException(status_code=500, detail="Failed to create folder")
    return result


@router.delete("/folders/{uid}")
@handle_route_errors()
async def delete_folder(
    uid: str = Path(..., min_length=1, max_length=200, pattern=r"^[A-Za-z0-9_-]+$"),
    current_user: TokenData = Depends(require_permission_with_scope(Permission.DELETE_FOLDERS, "grafana")),
    db: Session = Depends(get_db),
) -> JSONDict:
    user_id, tenant_id, group_ids, is_admin = scope_context(current_user)
    ok = await proxy.delete_folder(
        db=db,
        request=FolderDeleteBundle(
            uid=uid,
            scope=GrafanaUserScope(user_id=user_id, tenant_id=tenant_id, group_ids=group_ids),
            options=FolderDeleteOptions(is_admin=is_admin),
        ),
    )
    if not ok:
        raise HTTPException(status_code=404, detail=f"Folder {uid} not found or delete failed")
    return {"status": "success", "message": f"Folder {uid} deleted"}


@router.put("/folders/{uid}", response_model=Folder)
@handle_route_errors()
async def update_folder(
    request: FolderUpdateRequest = Depends(_folder_update_request_dep),
    visibility: Optional[str] = Query(None),
    shared_group_ids: Optional[List[str]] = Query(None),
    *,
    current_user: TokenData = Depends(require_permission_with_scope(Permission.CREATE_FOLDERS, "grafana")),
    db: Session = Depends(get_db),
) -> Folder:
    validate_visibility(visibility)
    user_id, tenant_id, group_ids, is_admin = scope_context(current_user)
    result = await proxy.update_folder(
        db=db,
        request=FolderUpdateBundle(
            uid=request.uid,
            scope=GrafanaUserScope(user_id=user_id, tenant_id=tenant_id, group_ids=group_ids),
            options=FolderUpdateOptions(
                title=request.payload.title,
                visibility=visibility,
                shared_group_ids=shared_group_ids,
                allow_dashboard_writes=request.payload.allow_dashboard_writes,
                is_admin=is_admin,
            ),
        ),
    )
    if not result:
        raise HTTPException(status_code=404, detail=f"Folder {request.uid} not found or update failed")
    return result


@router.post("/folders/{uid}/hide")
@handle_route_errors()
async def hide_folder(
    uid: str = Path(..., min_length=1, max_length=200, pattern=r"^[A-Za-z0-9_-]+$"),
    payload: GrafanaHiddenToggleRequest = Body(default_factory=GrafanaHiddenToggleRequest),
    current_user: TokenData = Depends(
        require_any_permission_with_scope([Permission.CREATE_FOLDERS, Permission.DELETE_FOLDERS], "grafana")
    ),
    db: Session = Depends(get_db),
) -> JSONDict:
    user_id, tenant_id = hidden_toggle_context(current_user)
    ok = await rtp(
        proxy.toggle_folder_hidden,
        db=db,
        request=HiddenToggleRequest(
            uid=uid,
            scope=GrafanaUserScope(user_id=user_id, tenant_id=tenant_id, group_ids=[]),
            params=HiddenToggleParams(hidden=payload.hidden),
        ),
    )
    if not ok:
        raise HTTPException(status_code=404, detail=f"Folder {uid} not found")
    return {"status": "success", "hidden": payload.hidden}
