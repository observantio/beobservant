"""
Dashboard operations for Grafana integration.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the
License. You may obtain a copy of the License at
http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

import httpx
from config import config
from custom_types.json import JSONDict
from db_models import GrafanaDashboard, GrafanaFolder
from fastapi import HTTPException
from models.grafana.grafana_dashboard_models import DashboardCreate, DashboardSearchResult
from services.grafana.dashboard_complexity_helpers import (
    CreateDashboardAccessContext,
    DashboardUpdateMoveVisibilityContext,
    DashboardVisibilityUpdateContext,
    UpdateScopeAccessContext,
    apply_dashboard_visibility_update,
    create_dashboard_in_grafana,
    dedupe_search_dashboards,
    ensure_update_scope_access,
    resolve_created_folder_uid,
    validate_create_dashboard_access,
    validate_update_move_and_visibility,
)
from services.grafana.dashboard_helpers import (
    DashboardSearchContext,
    _cap,
    _dashboard_has_datasource,
    _db_dashboard_by_uid,
    _has_accessible_title_conflict,
    _is_general_folder_id,
    _is_hidden_for,
    _is_non_general_folder_id,
    _json_dict,
    _purge_stale_dashboards,
    _resolve_folder_uid_by_id,
    _shared_group_ids,
    _to_safe_int32,
    _to_search_result,
    build_dashboard_search_context,
    check_dashboard_access,
    get_accessible_dashboard_uids,
)
from services.grafana.folder_ops import check_folder_access, is_folder_accessible
from services.grafana.grafana_bundles import (
    AccessibleTitleConflictParams,
    DashboardAccessCriteria,
    DashboardCreateOptions,
    DashboardSearchAppendContext,
    DashboardSearchParams,
    DashboardUpdateRequest,
    FolderAccessCriteria,
    GrafanaUserScope,
    HiddenToggleParams,
)
from services.grafana.grafana_service import GrafanaAPIError, GrafanaDashboardSearchRequest
from services.grafana.proxy_client import GrafanaProxyClient
from services.grafana.shared_ops import commit_session, group_id_strs, update_hidden_members
from services.grafana.visibility import resolve_visibility_groups_for_scope, visibility_group_resolve_context
from sqlalchemy.orm import Session


def _append_dashboard_search_match(d: DashboardSearchResult, ctx: DashboardSearchAppendContext) -> None:
    db_dash = ctx.db_dashboards.get(d.uid)
    folder_id = getattr(d, "folder_id", None)
    if folder_id is None:
        folder_id = getattr(d, "folderId", None)
    try:
        folder_id_int = int(folder_id) if folder_id is not None else None
    except (TypeError, ValueError):
        folder_id_int = None
    folder_uid = (
        getattr(d, "folder_uid", None)
        or getattr(d, "folderUid", None)
        or (getattr(db_dash, "folder_uid", None) if db_dash else None)
    )
    if folder_id is None and not folder_uid:
        folder_id_int = 0
    if _is_general_folder_id(folder_id):
        if db_dash and db_dash.folder_uid:
            db_dash.folder_uid = None
            ctx.folder_updates.append(db_dash)
        folder_uid = None
    skip = False
    if ctx.folder_uid_set and str(folder_uid or "") not in ctx.folder_uid_set:
        skip = True
    if not skip and ctx.folder_id_set and folder_id_int not in ctx.folder_id_set:
        skip = True
    if not skip and ctx.exclude_foldered_dashboards and (folder_uid or _is_non_general_folder_id(folder_id_int)):
        skip = True
    if not folder_uid and folder_id:
        folder_by_id = (
            ctx.db.query(GrafanaFolder)
            .filter(
                GrafanaFolder.tenant_id == ctx.tenant_id,
                GrafanaFolder.grafana_id == folder_id,
            )
            .first()
        )
        folder_uid = getattr(folder_by_id, "grafana_uid", None)

    if not folder_uid and _is_non_general_folder_id(folder_id):
        skip = True
    if db_dash and folder_uid and db_dash.folder_uid != folder_uid:
        db_dash.folder_uid = str(folder_uid)
        ctx.folder_updates.append(db_dash)
    if (
        not skip
        and folder_uid
        and not is_folder_accessible(
            ctx.db,
            folder_uid,
            GrafanaUserScope(ctx.user_id, ctx.tenant_id, ctx.gids),
            FolderAccessCriteria(require_write=False, is_admin=ctx.is_admin, include_hidden=False),
        )
    ):
        skip = True
    if not skip and d.uid not in ctx.accessible and not (ctx.allow_system and d.uid not in ctx.all_registered_uids):
        skip = True
    if not skip and db_dash and not ctx.show_hidden and _is_hidden_for(db_dash, ctx.user_id):
        skip = True
    if (
        not skip
        and ctx.team_id_s
        and (not db_dash or ctx.team_id_s not in {str(g.id) for g in (db_dash.shared_groups or [])})
    ):
        skip = True
    if not skip:
        ctx.out.append(_to_search_result(d, db_dash=db_dash, user_id=ctx.user_id))


@dataclass(frozen=True, slots=True)
class DashboardUidSearchRequest:
    uid: str
    user_id: str
    tenant_id: str
    gids: list[str]
    is_admin: bool
    show_hidden: bool
    search_context: object | None


async def _search_dashboard_by_uid(
    service: GrafanaProxyClient,
    db: Session,
    request: DashboardUidSearchRequest,
) -> list[DashboardSearchResult]:
    result = await service.grafana_service.get_dashboard(request.uid)
    if not result:
        return []

    meta = _json_dict(result.get("meta"))
    folder_uid_value = meta.get("folderUid")
    folder_uid = folder_uid_value if isinstance(folder_uid_value, str) else None
    if folder_uid and not is_folder_accessible(
        db,
        folder_uid,
        GrafanaUserScope(request.user_id, request.tenant_id, request.gids),
        FolderAccessCriteria(require_write=False, is_admin=request.is_admin, include_hidden=False),
    ):
        return []

    effective_context = request.search_context or build_dashboard_search_context(
        db,
        tenant_id=request.tenant_id,
        uid=request.uid,
    )
    effective_context = cast(DashboardSearchContext, effective_context)
    db_dash = effective_context.get("uid_db_dashboard")
    if db_dash and (
        check_dashboard_access(
            db,
            request.uid,
            GrafanaUserScope(user_id=request.user_id, tenant_id=request.tenant_id, group_ids=request.gids),
            DashboardAccessCriteria(),
        )
        is None
        or (not request.show_hidden and _is_hidden_for(db_dash, request.user_id))
    ):
        return []

    dash_data = _json_dict(result.get("dashboard", {}))
    grafana_like = {
        "id": dash_data.get("id", 0),
        "uid": request.uid,
        "title": dash_data.get("title", ""),
        "uri": f"db/{meta.get('slug', '')}",
        "url": meta.get("url", f"/d/{request.uid}"),
        "slug": meta.get("slug", ""),
        "type": "dash-db",
        "tags": dash_data.get("tags", []),
        "isStarred": meta.get("isStarred", False),
        "folderId": meta.get("folderId"),
        "folderUid": meta.get("folderUid"),
        "folderTitle": meta.get("folderTitle"),
    }
    return [_to_search_result(grafana_like, db_dash=db_dash, user_id=request.user_id)]


def _build_dashboard_payload(result: JSONDict, db_dashboard: GrafanaDashboard, *, user_id: str) -> JSONDict:
    sgids = _shared_group_ids(db_dashboard)
    payload = dict(result)
    payload["visibility"] = (db_dashboard.visibility or "private") or "private"
    payload["shared_group_ids"] = sgids
    payload["sharedGroupIds"] = sgids
    payload["created_by"] = db_dashboard.created_by
    payload["is_owned"] = bool(db_dashboard.created_by == user_id)
    payload["is_hidden"] = _is_hidden_for(db_dashboard, user_id)
    return payload


def _resolve_dashboard_folder_uid(
    db: Session,
    *,
    tenant_id: str,
    db_dashboard: GrafanaDashboard,
    meta: JSONDict,
) -> str | None:
    meta_folder_uid = meta.get("folderUid")
    folder_uid = meta_folder_uid if isinstance(meta_folder_uid, str) and meta_folder_uid else db_dashboard.folder_uid
    folder_id = meta.get("folderId")
    if _is_general_folder_id(folder_id) and db_dashboard.folder_uid:
        db_dashboard.folder_uid = None
        commit_session(db)
        folder_uid = None
    if not folder_uid and _is_non_general_folder_id(folder_id):
        folder_by_id = (
            db.query(GrafanaFolder)
            .filter(
                GrafanaFolder.tenant_id == tenant_id,
                GrafanaFolder.grafana_id == folder_id,
            )
            .first()
        )
        folder_uid = getattr(folder_by_id, "grafana_uid", None)
    return str(folder_uid) if folder_uid else None


async def search_dashboards(
    service: GrafanaProxyClient,
    db: Session,
    scope: GrafanaUserScope,
    params: DashboardSearchParams,
) -> list[DashboardSearchResult]:
    user_id = scope.user_id
    tenant_id = scope.tenant_id
    group_ids = scope.group_ids
    query = params.query
    tag = params.tag
    starred = params.starred
    folder_ids = params.folder_ids
    folder_uids = params.folder_uids
    dashboard_uids = params.dashboard_uids
    uid = params.uid
    team_id = params.team_id
    show_hidden = params.show_hidden
    limit = params.limit
    offset = params.offset
    search_context = params.search_context
    is_admin = params.is_admin
    exclude_foldered_dashboards = params.exclude_foldered_dashboards

    capped_limit, capped_offset = _cap(limit, offset)
    gids = group_id_strs(group_ids)
    team_id_s = str(team_id) if team_id is not None else None
    folder_id_set = {parsed for parsed in (_to_safe_int32(fid) for fid in (folder_ids or [])) if parsed is not None}
    folder_uid_set = {str(fu) for fu in (folder_uids or []) if fu}
    dashboard_uid_set = {str(du) for du in (dashboard_uids or []) if du}

    if uid:
        return await _search_dashboard_by_uid(
            service,
            db,
            DashboardUidSearchRequest(
                uid=uid,
                user_id=user_id,
                tenant_id=tenant_id,
                gids=gids,
                is_admin=is_admin,
                show_hidden=show_hidden,
                search_context=search_context,
            ),
        )

    all_dashboards = await service.grafana_service.search_dashboards(
        GrafanaDashboardSearchRequest(
            query=query,
            tag=tag,
            starred=starred,
            folder_ids=list(folder_id_set) or None,
            folder_uids=list(folder_uid_set) or None,
            dashboard_uids=list(dashboard_uid_set) or None,
        )
    )
    all_dashboards = dedupe_search_dashboards(all_dashboards, dashboard_uid_set)
    should_sync_stale = (
        query is None
        and tag is None
        and starred is None
        and not folder_id_set
        and not folder_uid_set
        and not dashboard_uid_set
        and not exclude_foldered_dashboards
    )
    if should_sync_stale:
        _purge_stale_dashboards(
            db,
            tenant_id=tenant_id,
            live_uids={str(d.uid) for d in all_dashboards if getattr(d, "uid", None)},
        )
    accessible_uids, allow_system = get_accessible_dashboard_uids(db, user_id, tenant_id, gids)
    accessible = set(accessible_uids)

    effective_context = cast(
        DashboardSearchContext,
        search_context or build_dashboard_search_context(db, tenant_id=tenant_id),
    )
    all_registered_uids = effective_context.get("all_registered_uids") or set()
    db_dashboards = effective_context.get("db_dashboards") or {}

    out: list[DashboardSearchResult] = []
    folder_updates: list[GrafanaDashboard] = []
    append_ctx = DashboardSearchAppendContext(
        db=db,
        tenant_id=tenant_id,
        user_id=user_id,
        gids=gids,
        is_admin=is_admin,
        folder_uid_set=folder_uid_set,
        folder_id_set=folder_id_set,
        exclude_foldered_dashboards=exclude_foldered_dashboards,
        accessible=accessible,
        allow_system=allow_system,
        all_registered_uids=all_registered_uids,
        db_dashboards=db_dashboards,
        show_hidden=show_hidden,
        team_id_s=team_id_s,
        out=out,
        folder_updates=folder_updates,
    )
    for d in all_dashboards:
        _append_dashboard_search_match(d, append_ctx)

    if folder_updates:
        commit_session(db)

    return out[capped_offset : capped_offset + capped_limit]


async def get_dashboard(
    service: GrafanaProxyClient,
    db: Session,
    uid: str,
    scope: GrafanaUserScope,
    *,
    is_admin: bool = False,
) -> JSONDict | None:
    user_id = scope.user_id
    tenant_id = scope.tenant_id
    gids = group_id_strs(scope.group_ids)
    db_dashboard = _db_dashboard_by_uid(db, tenant_id, uid)
    if not db_dashboard:
        return None
    result = await service.grafana_service.get_dashboard(uid)
    if not result:
        db.delete(db_dashboard)
        commit_session(db)
        return None
    meta = _json_dict(result.get("meta"))
    folder_id = meta.get("folderId")
    folder_uid = _resolve_dashboard_folder_uid(
        db,
        tenant_id=tenant_id,
        db_dashboard=db_dashboard,
        meta=meta,
    )
    if not folder_uid and _is_non_general_folder_id(folder_id):
        return None
    if (
        folder_uid
        and not is_folder_accessible(
            db,
            folder_uid,
            GrafanaUserScope(user_id, tenant_id, gids),
            FolderAccessCriteria(require_write=False, is_admin=is_admin, include_hidden=False),
        )
    ) or check_dashboard_access(
        db,
        uid,
        GrafanaUserScope(user_id=user_id, tenant_id=tenant_id, group_ids=gids),
        DashboardAccessCriteria(),
    ) is None:
        return None
    return _build_dashboard_payload(result, db_dashboard, user_id=user_id)


def _merge_grafana_update_into_db_dashboard(
    db_dashboard: GrafanaDashboard,
    result: JSONDict,
    *,
    requested_title: str,
    target_folder_id: object,
    target_folder_uid: str | None,
) -> None:
    dashboard_data = _json_dict(result.get("dashboard", {}))
    title_value = dashboard_data.get("title", db_dashboard.title)
    db_dashboard.title = requested_title or (title_value if isinstance(title_value, str) else db_dashboard.title)
    tags_value = dashboard_data.get("tags", [])
    db_dashboard.tags = tags_value if isinstance(tags_value, list) else []
    resolved_folder_uid = result.get("folderUid") or dashboard_data.get("folderUid")
    if not resolved_folder_uid:
        if _is_general_folder_id(target_folder_id):
            resolved_folder_uid = None
        elif target_folder_uid:
            resolved_folder_uid = target_folder_uid
    db_dashboard.folder_uid = str(resolved_folder_uid) if resolved_folder_uid else None


async def create_dashboard(
    service: GrafanaProxyClient,
    db: Session,
    dashboard_create: DashboardCreate,
    *,
    scope: GrafanaUserScope,
    options: DashboardCreateOptions,
) -> JSONDict | None:
    user_id = scope.user_id
    tenant_id = scope.tenant_id
    group_ids = scope.group_ids
    visibility = options.visibility
    shared_group_ids = options.shared_group_ids
    is_admin = options.is_admin
    actor_permissions = options.actor_permissions

    requested_title = str(getattr(getattr(dashboard_create, "dashboard", None), "title", "") or "").strip()
    gids = group_id_strs(group_ids)
    if actor_permissions is None:
        has_create_scope = True
    else:
        perm_set = {str(p).strip() for p in (actor_permissions or []) if str(p).strip()}
        has_create_scope = bool({"create:dashboards", "write:dashboards"} & perm_set)
    if requested_title and await _has_accessible_title_conflict(
        service,
        db,
        AccessibleTitleConflictParams(
            tenant_id=tenant_id,
            user_id=user_id,
            group_ids=group_ids,
            title=requested_title,
            visibility=visibility,
            shared_group_ids=shared_group_ids,
        ),
    ):
        raise HTTPException(status_code=409, detail="Dashboard title already exists in your visible scope")

    folder_id = getattr(dashboard_create, "folder_id", None)
    folder_uid = await _resolve_folder_uid_by_id(service, folder_id)
    validate_create_dashboard_access(
        CreateDashboardAccessContext(
            db=db,
            folder_uid=folder_uid,
            user_id=user_id,
            tenant_id=tenant_id,
            gids=gids,
            is_admin=is_admin,
            has_create_scope=has_create_scope,
            visibility=visibility,
            shared_group_ids=shared_group_ids,
        )
    )

    dash_obj = getattr(dashboard_create, "dashboard", None)
    if dash_obj and not _dashboard_has_datasource(dash_obj):
        raise HTTPException(
            status_code=400,
            detail=(
                "Dashboard JSON missing datasource references; include a templating datasource "
                "(ds_default) or explicit panel/target datasources"
            ),
        )

    groups = resolve_visibility_groups_for_scope(
        service,
        db,
        visibility_group_resolve_context(
            scope,
            visibility=visibility,
            shared_group_ids=shared_group_ids,
            is_admin=is_admin,
        ),
    )

    result = await create_dashboard_in_grafana(service, dashboard_create)

    if not result:
        return None

    dashboard_data = _json_dict(result.get("dashboard", {}))
    uid = result.get("uid") or dashboard_data.get("uid")
    if not uid:
        return dict(result)

    folder_uid = await resolve_created_folder_uid(service, dashboard_create, result, dashboard_data)

    db_dashboard = GrafanaDashboard(
        tenant_id=tenant_id,
        created_by=user_id,
        grafana_uid=uid,
        grafana_id=result.get("id"),
        title=requested_title or dashboard_data.get("title", "Untitled"),
        folder_uid=folder_uid,
        visibility=visibility,
        tags=dashboard_data.get("tags", []),
        hidden_by=[],
    )
    if visibility == "group" and shared_group_ids:
        db_dashboard.shared_groups.extend(groups)

    db.add(db_dashboard)
    commit_session(db)

    sgids = _shared_group_ids(db_dashboard)
    payload = dict(result)
    payload["visibility"] = (db_dashboard.visibility or "private") or "private"
    payload["shared_group_ids"] = sgids
    payload["sharedGroupIds"] = sgids
    payload["created_by"] = db_dashboard.created_by
    payload["is_owned"] = True
    payload["is_hidden"] = False
    return payload


async def update_dashboard(
    service: GrafanaProxyClient,
    db: Session,
    request: DashboardUpdateRequest,
) -> JSONDict | None:
    uid = request.uid
    dashboard_update = request.dashboard_update
    scope = request.scope
    options = request.options
    user_id = scope.user_id
    tenant_id = scope.tenant_id
    group_ids = scope.group_ids
    visibility = options.visibility
    shared_group_ids = options.shared_group_ids
    is_admin = options.is_admin
    actor_permissions = options.actor_permissions
    gids = group_id_strs(group_ids)

    db_dashboard = _db_dashboard_by_uid(db, tenant_id, uid)
    if not db_dashboard:
        return None
    is_owner = str(getattr(db_dashboard, "created_by", "")) == str(user_id)
    if not ensure_update_scope_access(
        UpdateScopeAccessContext(
            db=db,
            db_dashboard=db_dashboard,
            is_owner=is_owner,
            actor_permissions=actor_permissions,
            user_id=user_id,
            tenant_id=tenant_id,
            gids=gids,
            is_admin=is_admin,
        )
    ):
        return None

    requested_title = str(getattr(getattr(dashboard_update, "dashboard", None), "title", "") or "").strip()
    requested_visibility = visibility or str(db_dashboard.visibility or "private")
    requested_shared_group_ids = shared_group_ids if shared_group_ids is not None else _shared_group_ids(db_dashboard)
    if requested_title and await _has_accessible_title_conflict(
        service,
        db,
        AccessibleTitleConflictParams(
            tenant_id=tenant_id,
            user_id=user_id,
            group_ids=gids,
            title=requested_title,
            visibility=requested_visibility,
            shared_group_ids=requested_shared_group_ids,
            exclude_uid=uid,
        ),
    ):
        raise HTTPException(status_code=409, detail="Dashboard title already exists in your visible scope")

    target_folder_id = getattr(dashboard_update, "folder_id", None)
    target_folder_uid = await _resolve_folder_uid_by_id(service, target_folder_id)
    if is_owner and target_folder_uid:
        target_folder = check_folder_access(
            db,
            target_folder_uid,
            GrafanaUserScope(user_id, tenant_id, gids),
            FolderAccessCriteria(require_write=False, is_admin=is_admin, include_hidden=False),
        )
        if not target_folder or (
            str(getattr(target_folder, "created_by", "")) != str(user_id)
            and not bool(getattr(target_folder, "allow_dashboard_writes", False))
        ):
            raise HTTPException(status_code=403, detail="Folder access denied")
    validate_update_move_and_visibility(
        DashboardUpdateMoveVisibilityContext(
            db_dashboard=db_dashboard,
            is_owner=is_owner,
            visibility=visibility,
            shared_group_ids=shared_group_ids,
            target_folder_uid=target_folder_uid,
        ),
        _shared_group_ids,
    )

    dash_obj = getattr(dashboard_update, "dashboard", None)
    if dash_obj and not _dashboard_has_datasource(dash_obj):
        raise HTTPException(
            status_code=400,
            detail=(
                "Dashboard JSON missing datasource references; include a templating datasource "
                "(ds_default) or explicit panel/target datasources"
            ),
        )

    try:
        result = await service.grafana_service.update_dashboard(uid, dashboard_update)
    except (GrafanaAPIError, httpx.HTTPError) as exc:
        service.raise_http_from_grafana_error(exc)
        return None

    if not result:
        return None

    _merge_grafana_update_into_db_dashboard(
        db_dashboard,
        result,
        requested_title=requested_title,
        target_folder_id=target_folder_id,
        target_folder_uid=target_folder_uid,
    )

    apply_dashboard_visibility_update(
        service,
        db,
        DashboardVisibilityUpdateContext(
            db_dashboard=db_dashboard,
            scope=scope,
            visibility=visibility,
            shared_group_ids=shared_group_ids,
            is_admin=is_admin,
        ),
    )

    commit_session(db)

    sgids = _shared_group_ids(db_dashboard)
    payload = dict(result)
    payload["visibility"] = (db_dashboard.visibility or "private") or "private"
    payload["shared_group_ids"] = sgids
    payload["sharedGroupIds"] = sgids
    payload["created_by"] = db_dashboard.created_by
    payload["is_owned"] = bool(db_dashboard.created_by == user_id)
    payload["is_hidden"] = _is_hidden_for(db_dashboard, user_id)
    return payload


async def delete_dashboard(
    service: GrafanaProxyClient,
    db: Session,
    uid: str,
    scope: GrafanaUserScope,
) -> bool:
    db_dashboard = check_dashboard_access(db, uid, scope, DashboardAccessCriteria(require_write=True))
    if not db_dashboard:
        return False
    ok = await service.grafana_service.delete_dashboard(uid)
    if not ok:
        return False
    db.delete(db_dashboard)
    commit_session(db)
    return True


def toggle_dashboard_hidden(
    db: Session,
    uid: str,
    scope: GrafanaUserScope,
    params: HiddenToggleParams,
) -> bool:
    db_dash = _db_dashboard_by_uid(db, scope.tenant_id, uid)
    if not db_dash:
        return False
    db_dash.hidden_by = update_hidden_members(db_dash.hidden_by, scope.user_id, params.hidden)
    commit_session(db)
    return True


def get_dashboard_metadata(db: Session, tenant_id: str) -> dict[str, list[str]]:
    rows = (
        db.query(GrafanaDashboard)
        .filter(GrafanaDashboard.tenant_id == tenant_id)
        .limit(int(config.MAX_QUERY_LIMIT))
        .all()
    )
    team_ids = sorted({str(g.id) for d in rows for g in (d.shared_groups or [])})
    return {"team_ids": team_ids}
