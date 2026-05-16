"""
Dashboard management endpoints for Watchdog Grafana proxy router.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the
License. You may obtain a copy of the License at
http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

from dataclasses import dataclass

from config import config
from custom_types.json import JSONDict
from database import get_db
from fastapi import Body, Depends, HTTPException, Path, Query
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
    HiddenToggleParams,
    HiddenToggleRequest,
)
from services.grafana.grafana_bundles import (
    DashboardCreateRequest as DashboardCreateBundle,
)
from services.grafana.grafana_bundles import (
    DashboardUpdateRequest as DashboardUpdateBundle,
)
from services.grafana.route_payloads import (
    parse_dashboard_create_payload,
    parse_dashboard_update_payload,
    validate_visibility,
)
from sqlalchemy.orm import Session

from .shared import dashboard_payload, dashboard_uid, hidden_toggle_context, proxy, router, rtp, scope_context


@router.get("/dashboards/meta/filters")
async def get_dashboard_filter_metadata(
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_DASHBOARDS, "grafana")),
    db: Session = Depends(get_db),
) -> JSONDict:
    return await rtp(proxy.get_dashboard_metadata, db=db, tenant_id=current_user.tenant_id)


@dataclass(frozen=True, slots=True)
class SearchDashboardsTextParams:
    query: str | None
    tag: str | None
    uid: str | None
    team_id: str | None


@dataclass(frozen=True, slots=True)
class SearchDashboardsFolderParams:
    folder_ids: list[int] | None
    folder_uids: list[str] | None
    dashboard_uids: list[str] | None
    search_type: str | None


@dataclass(frozen=True, slots=True)
class SearchDashboardsPagingParams:
    starred: bool | None
    show_hidden: str
    limit: int
    offset: int


@dataclass(frozen=True, slots=True)
class SearchDashboardsRequestParams:
    text: SearchDashboardsTextParams
    folders: SearchDashboardsFolderParams
    paging: SearchDashboardsPagingParams


@dataclass(frozen=True, slots=True)
class DashboardVisibilityParams:
    visibility: str | None
    shared_group_ids: list[str] | None


@dataclass(frozen=True, slots=True)
class DashboardUpdateRequest:
    uid: str
    payload: GrafanaDashboardPayloadRequest


def _search_dashboards_text_dep(
    query: str | None = Query(None),
    tag: str | None = Query(None),
    uid: str | None = Query(None),
    team_id: str | None = Query(None),
) -> SearchDashboardsTextParams:
    return SearchDashboardsTextParams(query=query, tag=tag, uid=uid, team_id=team_id)


def _search_dashboards_folder_dep(
    folder_ids: list[int] | None = Query(None, alias="folderIds"),
    folder_uids: list[str] | None = Query(None, alias="folderUIDs"),
    dashboard_uids: list[str] | None = Query(None, alias="dashboardUID"),
    search_type: str | None = Query(None, alias="type"),
) -> SearchDashboardsFolderParams:
    return SearchDashboardsFolderParams(
        folder_ids=folder_ids,
        folder_uids=folder_uids,
        dashboard_uids=dashboard_uids,
        search_type=search_type,
    )


def _search_dashboards_paging_dep(
    starred: bool | None = Query(None),
    show_hidden: str = Query("false", pattern=r"^(true|false)$"),
    limit: int = Query(config.DEFAULT_QUERY_LIMIT, ge=1, le=config.MAX_QUERY_LIMIT),
    offset: int = Query(0, ge=0),
) -> SearchDashboardsPagingParams:
    return SearchDashboardsPagingParams(starred=starred, show_hidden=show_hidden, limit=limit, offset=offset)


def _search_dashboards_request_dep(
    text: SearchDashboardsTextParams = Depends(_search_dashboards_text_dep),
    folders: SearchDashboardsFolderParams = Depends(_search_dashboards_folder_dep),
    paging: SearchDashboardsPagingParams = Depends(_search_dashboards_paging_dep),
) -> SearchDashboardsRequestParams:
    return SearchDashboardsRequestParams(text=text, folders=folders, paging=paging)


def _dashboard_create_visibility_dep(
    visibility: str = Query("private"),
    shared_group_ids: list[str] | None = Query(None),
) -> DashboardVisibilityParams:
    return DashboardVisibilityParams(visibility=visibility, shared_group_ids=shared_group_ids)


def _dashboard_update_visibility_dep(
    visibility: str | None = Query(None),
    shared_group_ids: list[str] | None = Query(None),
) -> DashboardVisibilityParams:
    return DashboardVisibilityParams(visibility=visibility, shared_group_ids=shared_group_ids)


def _dashboard_update_request_dep(
    uid: str = Path(..., min_length=1, max_length=200, pattern=r"^[A-Za-z0-9_-]+$"),
    payload: GrafanaDashboardPayloadRequest = Body(...),
) -> DashboardUpdateRequest:
    return DashboardUpdateRequest(uid=uid, payload=payload)


@router.get("/dashboards/search")
async def search_dashboards(
    dash_text: SearchDashboardsTextParams = Depends(_search_dashboards_text_dep),
    dash_folders: SearchDashboardsFolderParams = Depends(_search_dashboards_folder_dep),
    dash_paging: SearchDashboardsPagingParams = Depends(_search_dashboards_paging_dep),
    *,
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_DASHBOARDS, "grafana")),
    db: Session = Depends(get_db),
) -> list[DashboardSearchResult]:
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
    shared_group_ids: list[str] | None = Query(None),
    *,
    current_user: TokenData = Depends(require_authenticated_with_scope("grafana")),
    db: Session = Depends(get_db),
) -> JSONDict:
    validate_visibility(visibility)
    user_id, tenant_id, group_ids, is_admin = scope_context(current_user)
    raw = dashboard_payload(payload)
    result = await proxy.create_dashboard(
        db=db,
        request=DashboardCreateBundle(
            dashboard_create=parse_dashboard_create_payload(raw),
            scope=GrafanaUserScope(user_id=user_id, tenant_id=tenant_id, group_ids=group_ids),
            options=DashboardCreateOptions(
                visibility=visibility,
                shared_group_ids=shared_group_ids or [],
                is_admin=is_admin,
                actor_permissions=current_user.permissions or [],
            ),
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
                request=DashboardUpdateBundle(
                    uid=uid,
                    dashboard_update=parse_dashboard_update_payload(raw),
                    scope=GrafanaUserScope(user_id=user_id, tenant_id=tenant_id, group_ids=group_ids),
                    options=DashboardUpdateOptions(
                        visibility=None,
                        shared_group_ids=None,
                        is_admin=is_admin,
                        actor_permissions=current_user.permissions or [],
                    ),
                ),
            )
            if result:
                return result
            raise HTTPException(
                status_code=404,
                detail=f"Dashboard {uid} not found, access denied, or update failed",
            )

    result = await proxy.create_dashboard(
        db=db,
        request=DashboardCreateBundle(
            dashboard_create=parse_dashboard_create_payload(raw),
            scope=GrafanaUserScope(user_id=user_id, tenant_id=tenant_id, group_ids=group_ids),
            options=DashboardCreateOptions(
                visibility="private",
                shared_group_ids=[],
                is_admin=is_admin,
                actor_permissions=current_user.permissions or [],
            ),
        ),
    )
    if not result:
        raise HTTPException(status_code=500, detail="Failed to save dashboard")
    return result


@router.put("/dashboards/{uid}")
@handle_route_errors()
async def update_dashboard(
    request: DashboardUpdateRequest = Depends(_dashboard_update_request_dep),
    visibility: str | None = Query(None),
    shared_group_ids: list[str] | None = Query(None),
    *,
    current_user: TokenData = Depends(require_authenticated_with_scope("grafana")),
    db: Session = Depends(get_db),
) -> JSONDict:
    validate_visibility(visibility)
    user_id, tenant_id, group_ids, is_admin = scope_context(current_user)
    raw = dashboard_payload(request.payload)
    result = await proxy.update_dashboard(
        db=db,
        request=DashboardUpdateBundle(
            uid=request.uid,
            dashboard_update=parse_dashboard_update_payload(raw),
            scope=GrafanaUserScope(user_id=user_id, tenant_id=tenant_id, group_ids=group_ids),
            options=DashboardUpdateOptions(
                visibility=visibility,
                shared_group_ids=shared_group_ids,
                is_admin=is_admin,
                actor_permissions=current_user.permissions or [],
            ),
        ),
    )
    if not result:
        raise HTTPException(
            status_code=404,
            detail=f"Dashboard {request.uid} not found, access denied, or update failed",
        )
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
        request=HiddenToggleRequest(
            uid=uid,
            scope=GrafanaUserScope(user_id=user_id, tenant_id=tenant_id, group_ids=[]),
            params=HiddenToggleParams(hidden=payload.hidden),
        ),
    )
    if not ok:
        raise HTTPException(status_code=404, detail=f"Dashboard {uid} not found")
    return {"status": "success", "hidden": payload.hidden}
