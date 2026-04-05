"""
Dashboard management endpoints for Watchdog Grafana proxy router.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the
License. You may obtain a copy of the License at
http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

from typing import Annotated, List, Optional

from fastapi import Body, Depends, HTTPException, Path, Query
from sqlalchemy.orm import Session

from config import config
from custom_types.json import JSONDict
from database import get_db
from middleware.dependencies import (
    require_any_permission_with_scope,
    require_authenticated_with_scope,
    require_permission_with_scope,
)
from middleware.error_handlers import handle_route_errors
from models.access.auth_models import Permission, TokenData
from models.grafana.grafana_dashboard_models import DashboardSearchResult
from models.observability.grafana_request_models import GrafanaDashboardPayloadRequest, GrafanaHiddenToggleRequest
from routers.observability.grafana_router.param_helpers import (
    is_valid_uid_query,
    normalize_optional_param,
    show_hidden_enabled,
)
from services.grafana.grafana_bundles import (
    DashboardCreateOptions,
    DashboardSearchParams,
    DashboardUpdateOptions,
    GrafanaUserScope,
)
from services.grafana.route_payloads import (
    parse_dashboard_create_payload,
    parse_dashboard_update_payload,
    validate_visibility,
)

from .shared import dashboard_payload, dashboard_uid, hidden_toggle_context, proxy, router, rtp, scope_context


@router.get("/dashboards/meta/filters")
async def get_dashboard_filter_metadata(
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_DASHBOARDS, "grafana")),
    db: Session = Depends(get_db),
) -> JSONDict:
    return await rtp(proxy.get_dashboard_metadata, db=db, tenant_id=current_user.tenant_id)


class SearchDashboardsTextParams:
    def __init__(
        self,
        query: Optional[str] = Query(None),
        tag: Optional[str] = Query(None),
        uid: Optional[str] = Query(None),
        team_id: Optional[str] = Query(None),
    ) -> None:
        self.query = query
        self.tag = tag
        self.uid = uid
        self.team_id = team_id


class SearchDashboardsFolderParams:
    def __init__(
        self,
        folder_ids: Optional[List[int]] = Query(None, alias="folderIds"),
        folder_uids: Optional[List[str]] = Query(None, alias="folderUIDs"),
        dashboard_uids: Optional[List[str]] = Query(None, alias="dashboardUID"),
        search_type: Optional[str] = Query(None, alias="type"),
    ) -> None:
        self.folder_ids = folder_ids
        self.folder_uids = folder_uids
        self.dashboard_uids = dashboard_uids
        self.search_type = search_type


class SearchDashboardsPagingParams:
    def __init__(
        self,
        starred: Optional[bool] = Query(None),
        show_hidden: str = Query("false", pattern=r"^(true|false)$"),
        limit: int = Query(config.DEFAULT_QUERY_LIMIT, ge=1, le=config.MAX_QUERY_LIMIT),
        offset: int = Query(0, ge=0),
    ) -> None:
        self.starred = starred
        self.show_hidden = show_hidden
        self.limit = limit
        self.offset = offset


@router.get("/dashboards/search")
async def search_dashboards(
    dash_text: Annotated[SearchDashboardsTextParams, Depends()],
    dash_folders: Annotated[SearchDashboardsFolderParams, Depends()],
    dash_paging: Annotated[SearchDashboardsPagingParams, Depends()],
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_DASHBOARDS, "grafana")),
    db: Session = Depends(get_db),
) -> List[DashboardSearchResult]:
    query = normalize_optional_param(dash_text.query)
    tag = normalize_optional_param(dash_text.tag)
    search_type = normalize_optional_param(dash_folders.search_type)
    team_id = normalize_optional_param(dash_text.team_id)
    uid = normalize_optional_param(dash_text.uid)
    if uid and not is_valid_uid_query(uid):
        raise HTTPException(status_code=400, detail="Invalid uid format")

    user_id, tenant_id, group_ids, is_admin = scope_context(current_user)
    search_context = await rtp(proxy.build_dashboard_search_context, db, tenant_id=current_user.tenant_id, uid=uid)
    subject = GrafanaUserScope(user_id=user_id, tenant_id=tenant_id, group_ids=group_ids)
    params = DashboardSearchParams(
        query=query,
        tag=tag,
        starred=dash_paging.starred,
        folder_ids=dash_folders.folder_ids,
        folder_uids=dash_folders.folder_uids,
        dashboard_uids=dash_folders.dashboard_uids,
        uid=uid,
        team_id=team_id,
        show_hidden=show_hidden_enabled(dash_paging.show_hidden),
        limit=dash_paging.limit,
        offset=dash_paging.offset,
        search_context=search_context,
        is_admin=is_admin,
        exclude_foldered_dashboards=bool(
            search_type is not None
            and not dash_folders.folder_ids
            and not dash_folders.folder_uids
            and not dash_folders.dashboard_uids
        ),
    )
    return await proxy.search_dashboards(db=db, subject=subject, params=params)


@router.get("/dashboards/{uid}")
async def get_dashboard(
    uid: str = Path(..., min_length=1, max_length=200, pattern=r"^[A-Za-z0-9_-]+$"),
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_DASHBOARDS, "grafana")),
    db: Session = Depends(get_db),
) -> JSONDict:
    user_id, tenant_id, group_ids, is_admin = scope_context(current_user)
    dashboard = await proxy.get_dashboard(
        db=db,
        uid=uid,
        subject=GrafanaUserScope(user_id=user_id, tenant_id=tenant_id, group_ids=group_ids),
        is_admin=is_admin,
    )
    if not dashboard:
        raise HTTPException(status_code=404, detail=f"Dashboard {uid} not found or access denied")
    return dashboard


@router.post("/dashboards")
@handle_route_errors()
async def create_dashboard(
    payload: GrafanaDashboardPayloadRequest,
    visibility: str = Query("private"),
    shared_group_ids: Optional[List[str]] = Query(None),
    current_user: TokenData = Depends(require_authenticated_with_scope("grafana")),
    db: Session = Depends(get_db),
) -> JSONDict:
    validate_visibility(visibility)
    user_id, tenant_id, group_ids, is_admin = scope_context(current_user)
    raw = dashboard_payload(payload)
    result = await proxy.create_dashboard(
        db=db,
        dashboard_create=parse_dashboard_create_payload(raw),
        subject=GrafanaUserScope(user_id=user_id, tenant_id=tenant_id, group_ids=group_ids),
        options=DashboardCreateOptions(
            visibility=visibility,
            shared_group_ids=shared_group_ids or [],
            is_admin=is_admin,
            actor_permissions=current_user.permissions or [],
        ),
    )
    if not result:
        raise HTTPException(status_code=500, detail="Failed to create dashboard")
    return result


@router.post("/dashboards/db")
@router.post("/dashboards/db/")
@handle_route_errors()
async def save_dashboard_from_grafana_ui(
    payload: GrafanaDashboardPayloadRequest,
    current_user: TokenData = Depends(require_authenticated_with_scope("grafana")),
    db: Session = Depends(get_db),
) -> JSONDict:
    user_id, tenant_id, group_ids, is_admin = scope_context(current_user)
    raw = dashboard_payload(payload)
    uid = dashboard_uid(raw)

    if uid:
        existing = await rtp(proxy.build_dashboard_search_context, db, tenant_id=tenant_id, uid=uid)
        if existing.get("uid_db_dashboard") is not None:
            result = await proxy.update_dashboard(
                db=db,
                uid=uid,
                dashboard_update=parse_dashboard_update_payload(raw),
                subject=GrafanaUserScope(user_id=user_id, tenant_id=tenant_id, group_ids=group_ids),
                options=DashboardUpdateOptions(
                    visibility=None,
                    shared_group_ids=None,
                    is_admin=is_admin,
                    actor_permissions=current_user.permissions or [],
                ),
            )
            if result:
                return result

    result = await proxy.create_dashboard(
        db=db,
        dashboard_create=parse_dashboard_create_payload(raw),
        subject=GrafanaUserScope(user_id=user_id, tenant_id=tenant_id, group_ids=group_ids),
        options=DashboardCreateOptions(
            visibility="private",
            shared_group_ids=[],
            is_admin=is_admin,
            actor_permissions=current_user.permissions or [],
        ),
    )
    if not result:
        raise HTTPException(status_code=500, detail="Failed to save dashboard")
    return result


@router.put("/dashboards/{uid}")
@handle_route_errors()
async def update_dashboard(
    uid: str = Path(..., min_length=1, max_length=200, pattern=r"^[A-Za-z0-9_-]+$"),
    payload: GrafanaDashboardPayloadRequest = Body(...),
    visibility: Optional[str] = Query(None),
    shared_group_ids: Optional[List[str]] = Query(None),
    current_user: TokenData = Depends(require_authenticated_with_scope("grafana")),
    db: Session = Depends(get_db),
) -> JSONDict:
    validate_visibility(visibility)
    user_id, tenant_id, group_ids, is_admin = scope_context(current_user)
    raw = dashboard_payload(payload)
    result = await proxy.update_dashboard(
        db=db,
        uid=uid,
        dashboard_update=parse_dashboard_update_payload(raw),
        subject=GrafanaUserScope(user_id=user_id, tenant_id=tenant_id, group_ids=group_ids),
        options=DashboardUpdateOptions(
            visibility=visibility,
            shared_group_ids=shared_group_ids,
            is_admin=is_admin,
            actor_permissions=current_user.permissions or [],
        ),
    )
    if not result:
        raise HTTPException(status_code=404, detail=f"Dashboard {uid} not found, access denied, or update failed")
    return result


@router.delete("/dashboards/{uid}")
@handle_route_errors()
async def delete_dashboard(
    uid: str = Path(..., min_length=1, max_length=200, pattern=r"^[A-Za-z0-9_-]+$"),
    current_user: TokenData = Depends(require_permission_with_scope(Permission.DELETE_DASHBOARDS, "grafana")),
    db: Session = Depends(get_db),
) -> JSONDict:
    user_id, tenant_id, group_ids, _ = scope_context(current_user)
    ok = await proxy.delete_dashboard(
        db=db,
        uid=uid,
        subject=GrafanaUserScope(user_id=user_id, tenant_id=tenant_id, group_ids=group_ids),
    )
    if not ok:
        raise HTTPException(status_code=404, detail=f"Dashboard {uid} not found or access denied")
    return {"status": "success", "message": f"Dashboard {uid} deleted"}


@router.post("/dashboards/{uid}/hide")
@handle_route_errors()
async def hide_dashboard(
    uid: str = Path(..., min_length=1, max_length=200, pattern=r"^[A-Za-z0-9_-]+$"),
    payload: GrafanaHiddenToggleRequest = Body(default_factory=GrafanaHiddenToggleRequest),
    current_user: TokenData = Depends(
        require_any_permission_with_scope([Permission.UPDATE_DASHBOARDS, Permission.WRITE_DASHBOARDS], "grafana")
    ),
    db: Session = Depends(get_db),
) -> JSONDict:
    user_id, tenant_id = hidden_toggle_context(current_user)
    ok = await rtp(
        proxy.toggle_dashboard_hidden,
        db=db,
        uid=uid,
        user_id=user_id,
        tenant_id=tenant_id,
        hidden=payload.hidden,
    )
    if not ok:
        raise HTTPException(status_code=404, detail=f"Dashboard {uid} not found")
    return {"status": "success", "hidden": payload.hidden}
