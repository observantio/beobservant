"""
Dashboard operations for Grafana integration.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the
License. You may obtain a copy of the License at
http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Dict, List, Optional

import httpx
from fastapi import HTTPException
from sqlalchemy.orm import Session

from config import config
from custom_types.json import JSONDict
from db_models import GrafanaDashboard, GrafanaFolder
from models.grafana.grafana_dashboard_models import DashboardCreate, DashboardSearchResult, DashboardUpdate
from services.grafana.dashboard_helpers import (
    DashboardSearchContext,
    _cap,
    _dashboard_has_datasource,
    _db_dashboard_by_uid,
    _has_accessible_title_conflict,
    _is_hidden_for,
    _is_general_folder_id,
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
from services.grafana.grafana_service import GrafanaAPIError
from services.grafana.folder_ops import check_folder_access, is_folder_accessible
from services.grafana.shared_ops import commit_session, group_id_strs, update_hidden_members
from services.grafana.visibility import resolve_visibility_groups

if TYPE_CHECKING:
    from services.grafana_proxy_service import GrafanaProxyService


async def search_dashboards(
    service: GrafanaProxyService,
    db: Session,
    user_id: str,
    tenant_id: str,
    group_ids: List[str],
    query: Optional[str] = None,
    tag: Optional[str] = None,
    starred: Optional[bool] = None,
    folder_ids: Optional[List[int]] = None,
    folder_uids: Optional[List[str]] = None,
    dashboard_uids: Optional[List[str]] = None,
    uid: Optional[str] = None,
    team_id: Optional[str] = None,
    show_hidden: bool = False,
    limit: Optional[int] = None,
    offset: int = 0,
    search_context: Optional[DashboardSearchContext] = None,
    is_admin: bool = False,
    exclude_foldered_dashboards: bool = False,
) -> List[DashboardSearchResult]:
    capped_limit, capped_offset = _cap(limit, offset)
    gids = group_id_strs(group_ids)
    team_id_s = str(team_id) if team_id is not None else None
    folder_id_set = {parsed for parsed in (_to_safe_int32(fid) for fid in (folder_ids or [])) if parsed is not None}
    folder_uid_set = {str(fu) for fu in (folder_uids or []) if fu}
    dashboard_uid_set = {str(du) for du in (dashboard_uids or []) if du}

    if uid:
        result = await service.grafana_service.get_dashboard(uid)
        if not result:
            return []
        meta = _json_dict(result.get("meta"))
        folder_uid_value = meta.get("folderUid")
        folder_uid = folder_uid_value if isinstance(folder_uid_value, str) else None
        if folder_uid and not is_folder_accessible(
            db,
            folder_uid,
            user_id,
            tenant_id,
            gids,
            require_write=False,
            is_admin=is_admin,
        ):
            return []
        effective_context = search_context or build_dashboard_search_context(db, tenant_id=tenant_id, uid=uid)
        db_dash = effective_context.get("uid_db_dashboard")
        if db_dash:
            if check_dashboard_access(db, uid, user_id, tenant_id, gids) is None:
                return []
            if not show_hidden and _is_hidden_for(db_dash, user_id):
                return []
        dash_data = _json_dict(result.get("dashboard", {}))
        grafana_like = {
            "id": dash_data.get("id", 0),
            "uid": uid,
            "title": dash_data.get("title", ""),
            "uri": f"db/{meta.get('slug', '')}",
            "url": meta.get("url", f"/d/{uid}"),
            "slug": meta.get("slug", ""),
            "type": "dash-db",
            "tags": dash_data.get("tags", []),
            "isStarred": meta.get("isStarred", False),
            "folderId": meta.get("folderId"),
            "folderUid": meta.get("folderUid"),
            "folderTitle": meta.get("folderTitle"),
        }
        return [_to_search_result(grafana_like, db_dash=db_dash, user_id=user_id)]

    all_dashboards = await service.grafana_service.search_dashboards(
        query=query,
        tag=tag,
        starred=starred,
        folder_ids=list(folder_id_set) or None,
        folder_uids=list(folder_uid_set) or None,
        dashboard_uids=list(dashboard_uid_set) or None,
    )
    deduped: Dict[str, DashboardSearchResult] = {}
    for d in all_dashboards:
        uid_val = str(getattr(d, "uid", "") or "")
        if not uid_val:
            continue
        if dashboard_uid_set and uid_val not in dashboard_uid_set:
            continue
        current = deduped.get(uid_val)
        d_has_folder = bool(getattr(d, "folder_uid", None) or getattr(d, "folderUid", None))
        current_has_folder = bool(
            current and (getattr(current, "folder_uid", None) or getattr(current, "folderUid", None))
        )
        if current is None or (d_has_folder and not current_has_folder):
            deduped[uid_val] = d
    all_dashboards = list(deduped.values())
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

    effective_context = search_context or build_dashboard_search_context(db, tenant_id=tenant_id)
    all_registered_uids = effective_context.get("all_registered_uids") or set()
    db_dashboards = effective_context.get("db_dashboards") or {}

    out: List[DashboardSearchResult] = []
    folder_updates: List[GrafanaDashboard] = []
    for d in all_dashboards:
        db_dash = db_dashboards.get(d.uid)
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
                folder_updates.append(db_dash)
            folder_uid = None
        if folder_uid_set and str(folder_uid or "") not in folder_uid_set:
            continue
        if folder_id_set and folder_id_int not in folder_id_set:
            continue
        if exclude_foldered_dashboards and (folder_uid or _is_non_general_folder_id(folder_id_int)):
            continue
        if not folder_uid and folder_id:
            folder_by_id = (
                db.query(GrafanaFolder)
                .filter(
                    GrafanaFolder.tenant_id == tenant_id,
                    GrafanaFolder.grafana_id == folder_id,
                )
                .first()
            )
            folder_uid = getattr(folder_by_id, "grafana_uid", None)

        if not folder_uid and _is_non_general_folder_id(folder_id):
            continue
        if db_dash and folder_uid and db_dash.folder_uid != folder_uid:
            db_dash.folder_uid = str(folder_uid)
            folder_updates.append(db_dash)
        if folder_uid and not is_folder_accessible(
            db,
            folder_uid,
            user_id,
            tenant_id,
            gids,
            require_write=False,
            is_admin=is_admin,
        ):
            continue
        if d.uid not in accessible and not (allow_system and d.uid not in all_registered_uids):
            continue
        if db_dash and not show_hidden and _is_hidden_for(db_dash, user_id):
            continue
        if team_id_s:
            if not db_dash:
                continue
            if team_id_s not in {str(g.id) for g in (db_dash.shared_groups or [])}:
                continue
        out.append(_to_search_result(d, db_dash=db_dash, user_id=user_id))

    if folder_updates:
        commit_session(db)

    return out[capped_offset : capped_offset + capped_limit]


async def get_dashboard(
    service: GrafanaProxyService,
    db: Session,
    uid: str,
    user_id: str,
    tenant_id: str,
    group_ids: List[str],
    is_admin: bool = False,
) -> Optional[JSONDict]:
    gids = group_id_strs(group_ids)
    db_dashboard = _db_dashboard_by_uid(db, tenant_id, uid)
    if not db_dashboard:
        return None
    result = await service.grafana_service.get_dashboard(uid)
    if not result:
        db.delete(db_dashboard)
        commit_session(db)
        return None
    meta = _json_dict(result.get("meta"))
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
    if not folder_uid and _is_non_general_folder_id(folder_id):
        return None
    if folder_uid and not is_folder_accessible(
        db,
        folder_uid,
        user_id,
        tenant_id,
        gids,
        require_write=False,
        is_admin=is_admin,
    ):
        return None
    if check_dashboard_access(db, uid, user_id, tenant_id, gids) is None:
        return None
    sgids = _shared_group_ids(db_dashboard)
    payload = dict(result)
    payload["visibility"] = (db_dashboard.visibility or "private") or "private"
    payload["shared_group_ids"] = sgids
    payload["sharedGroupIds"] = sgids
    payload["created_by"] = db_dashboard.created_by
    payload["is_owned"] = bool(db_dashboard.created_by == user_id)
    payload["is_hidden"] = _is_hidden_for(db_dashboard, user_id)
    return payload


async def create_dashboard(
    service: GrafanaProxyService,
    db: Session,
    dashboard_create: DashboardCreate,
    user_id: str,
    tenant_id: str,
    group_ids: List[str],
    visibility: str = "private",
    shared_group_ids: Optional[List[str]] = None,
    is_admin: bool = False,
    actor_permissions: Optional[List[str]] = None,
) -> Optional[JSONDict]:
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
        tenant_id=tenant_id,
        user_id=user_id,
        group_ids=group_ids,
        title=requested_title,
    ):
        raise HTTPException(status_code=409, detail="Dashboard title already exists in your visible scope")

    folder_id = getattr(dashboard_create, "folder_id", None)
    folder_uid = await _resolve_folder_uid_by_id(service, folder_id)
    target_folder = None
    if folder_uid:
        target_folder = check_folder_access(
            db,
            folder_uid,
            user_id,
            tenant_id,
            gids,
            require_write=False,
            is_admin=is_admin,
        )
    if folder_uid and not target_folder:
        raise HTTPException(status_code=403, detail="Folder access denied")
    if (
        target_folder
        and str(getattr(target_folder, "created_by", "")) != str(user_id)
        and not bool(getattr(target_folder, "allow_dashboard_writes", False))
    ):
        raise HTTPException(
            status_code=403,
            detail="Folder is owner-only for dashboard creation",
        )
    if not has_create_scope:
        if not target_folder:
            raise HTTPException(
                status_code=403,
                detail="Missing permission to create dashboards",
            )
        if visibility != "private" or shared_group_ids:
            raise HTTPException(
                status_code=403,
                detail="Delegated folder dashboard creation only supports private visibility",
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

    groups = resolve_visibility_groups(
        service, db, user_id, tenant_id, visibility, group_ids, shared_group_ids, is_admin
    )

    try:
        result = await service.grafana_service.create_dashboard(dashboard_create)
    except GrafanaAPIError as exc:
        dash_uid = getattr(dash_obj, "uid", None) if dash_obj is not None else None
        if exc.status in {409, 412} and dash_uid and dash_obj is not None:
            next_uid = f"{str(dash_uid)}-{uuid.uuid4().hex[:6]}"
            retry_payload = dashboard_create.model_copy(
                update={"dashboard": dash_obj.model_copy(update={"uid": next_uid})}
            )
            try:
                result = await service.grafana_service.create_dashboard(retry_payload)
            except GrafanaAPIError as retry_exc:
                service.raise_http_from_grafana_error(retry_exc)
        else:
            service.raise_http_from_grafana_error(exc)

    if not result:
        return None

    dashboard_data = _json_dict(result.get("dashboard", {}))
    uid = result.get("uid") or dashboard_data.get("uid")
    if not uid:
        return dict(result)

    folder_uid_value = result.get("folderUid") or dashboard_data.get("folderUid")
    folder_uid = folder_uid_value if isinstance(folder_uid_value, str) else None
    if not folder_uid:
        folder_id = getattr(dashboard_create, "folder_id", None)
        if folder_id:
            try:
                for f in await service.grafana_service.get_folders():
                    if f.id == folder_id:
                        folder_uid = f.uid
                        break
            except (httpx.HTTPError, RuntimeError, ValueError) as e:
                service.logger.debug("Unable to resolve folder uid for created dashboard: %s", e)

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
    service: GrafanaProxyService,
    db: Session,
    uid: str,
    dashboard_update: DashboardUpdate,
    user_id: str,
    tenant_id: str,
    group_ids: List[str],
    visibility: Optional[str] = None,
    shared_group_ids: Optional[List[str]] = None,
    is_admin: bool = False,
    actor_permissions: Optional[List[str]] = None,
) -> Optional[JSONDict]:
    gids = group_id_strs(group_ids)
    if actor_permissions is None:
        has_update_scope = True
    else:
        perm_set = {str(p).strip() for p in (actor_permissions or []) if str(p).strip()}
        has_update_scope = bool({"update:dashboards", "write:dashboards"} & perm_set)

    db_dashboard = _db_dashboard_by_uid(db, tenant_id, uid)
    if not db_dashboard:
        return None
    is_owner = str(getattr(db_dashboard, "created_by", "")) == str(user_id)

    delegated_update_allowed = False
    if not is_owner and db_dashboard.folder_uid:
        folder = check_folder_access(
            db,
            db_dashboard.folder_uid,
            user_id,
            tenant_id,
            gids,
            require_write=False,
            is_admin=is_admin,
        )
        delegated_update_allowed = bool(folder and bool(getattr(folder, "allow_dashboard_writes", False)))

    if not is_owner and not delegated_update_allowed:
        return None

    if not has_update_scope and not delegated_update_allowed:
        raise HTTPException(status_code=403, detail="Missing permission to update dashboards")

    requested_title = str(getattr(getattr(dashboard_update, "dashboard", None), "title", "") or "").strip()
    if requested_title and await _has_accessible_title_conflict(
        service,
        db,
        tenant_id=tenant_id,
        user_id=user_id,
        group_ids=gids,
        title=requested_title,
        exclude_uid=uid,
    ):
        raise HTTPException(status_code=409, detail="Dashboard title already exists in your visible scope")

    target_folder_id = getattr(dashboard_update, "folder_id", None)
    target_folder_uid = await _resolve_folder_uid_by_id(service, target_folder_id)
    if is_owner:
        if target_folder_uid:
            target_folder = check_folder_access(
                db,
                target_folder_uid,
                user_id,
                tenant_id,
                gids,
                require_write=False,
                is_admin=is_admin,
            )
            if not target_folder:
                raise HTTPException(status_code=403, detail="Folder access denied")
            if str(getattr(target_folder, "created_by", "")) != str(user_id) and not bool(
                getattr(target_folder, "allow_dashboard_writes", False)
            ):
                raise HTTPException(status_code=403, detail="Folder access denied")
    else:
        current_visibility = (db_dashboard.visibility or "private") or "private"
        if visibility is not None and str(visibility) != str(current_visibility):
            raise HTTPException(
                status_code=403,
                detail="Only owners can change dashboard visibility",
            )
        if shared_group_ids is not None:
            requested_groups = {str(g) for g in (shared_group_ids or [])}
            current_groups = set(_shared_group_ids(db_dashboard))
            if requested_groups != current_groups:
                raise HTTPException(
                    status_code=403,
                    detail="Only owners can change dashboard visibility",
                )
        if target_folder_uid and str(target_folder_uid) != str(db_dashboard.folder_uid or ""):
            raise HTTPException(
                status_code=403,
                detail="Only owners can move dashboards between folders",
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

    if visibility:
        db_dashboard.visibility = visibility
        if visibility == "group" and shared_group_ids is not None:
            groups = service.validate_group_visibility(
                db,
                user_id=user_id,
                tenant_id=tenant_id,
                group_ids=group_ids,
                shared_group_ids=shared_group_ids,
                is_admin=is_admin,
            )
            db_dashboard.shared_groups.clear()
            db_dashboard.shared_groups.extend(groups)
        elif visibility != "group":
            db_dashboard.shared_groups.clear()

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
    service: GrafanaProxyService,
    db: Session,
    uid: str,
    user_id: str,
    tenant_id: str,
    group_ids: List[str],
) -> bool:
    db_dashboard = check_dashboard_access(db, uid, user_id, tenant_id, group_ids, require_write=True)
    if not db_dashboard:
        return False
    ok = await service.grafana_service.delete_dashboard(uid)
    if not ok:
        return False
    db.delete(db_dashboard)
    commit_session(db)
    return True


def toggle_dashboard_hidden(db: Session, uid: str, user_id: str, tenant_id: str, hidden: bool) -> bool:
    db_dash = _db_dashboard_by_uid(db, tenant_id, uid)
    if not db_dash:
        return False
    db_dash.hidden_by = update_hidden_members(db_dash.hidden_by, user_id, hidden)
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
