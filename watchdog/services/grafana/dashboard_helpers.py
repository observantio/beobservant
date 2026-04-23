"""
Helper utilities for Grafana dashboard operations.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the
License. You may obtain a copy of the License at
http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional, TypedDict

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from config import config
from custom_types.json import JSONDict
from db_models import GrafanaDashboard, Group
from models.grafana.grafana_dashboard_models import DashboardSearchResult
from services.grafana.proxy_client import GrafanaProxyClient
from services.grafana.grafana_bundles import AccessibleTitleConflictParams, DashboardAccessCriteria, GrafanaUserScope
from services.grafana.shared_ops import group_id_strs

def _json_dict(value: object) -> JSONDict:
    return value if isinstance(value, dict) else {}


def _json_dict_list(value: object) -> list[JSONDict]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


class DashboardSearchContext(TypedDict, total=False):
    uid_db_dashboard: Optional[GrafanaDashboard]
    all_registered_uids: set[str]
    db_dashboards: Dict[str, GrafanaDashboard]


INT32_MIN = -(2**31)
INT32_MAX = (2**31) - 1


def _cap(limit: Optional[int], offset: int) -> tuple[int, int]:
    mx = int(config.MAX_QUERY_LIMIT)
    req = int(limit) if limit is not None else int(config.DEFAULT_QUERY_LIMIT)
    return max(1, min(req, mx)), max(0, int(offset))


def _to_safe_int32(value: object) -> Optional[int]:
    if not isinstance(value, (int, float, bool, str)):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    if parsed < INT32_MIN or parsed > INT32_MAX:
        return None
    return parsed


def _normalize_title(title: Optional[str]) -> str:
    return str(title or "").strip().lower()


def _normalized_group_id_set(group_ids: Optional[Iterable[object]]) -> set[str]:
    normalized: set[str] = set()
    for group_id in group_ids or []:
        value = getattr(group_id, "id", group_id)
        text = str(value).strip()
        if text:
            normalized.add(text)
    return normalized


def _title_conflict_matches_requested_scope(
    dashboard: GrafanaDashboard,
    params: AccessibleTitleConflictParams,
) -> bool:
    if params.visibility is None:
        return True

    requested_visibility = str(params.visibility).strip()
    dashboard_visibility = str(getattr(dashboard, "visibility", "") or "private")
    if dashboard_visibility != requested_visibility:
        return False

    if requested_visibility == "group":
        requested_groups = _normalized_group_id_set(params.shared_group_ids)
        dashboard_groups = _normalized_group_id_set(getattr(dashboard, "shared_groups", None))
        return dashboard_groups == requested_groups

    return True


def _visible_scope_filter(user_id: str, group_ids: List[str]) -> ColumnElement[bool]:
    gids = group_id_strs(group_ids)
    conds = [GrafanaDashboard.created_by == user_id, GrafanaDashboard.visibility == "tenant"]
    if gids:
        conds.append(
            and_(
                GrafanaDashboard.visibility == "group",
                GrafanaDashboard.shared_groups.any(Group.id.in_(gids)),
            )
        )
    return or_(*conds)


def _is_hidden_for(db_dash: Optional[GrafanaDashboard], user_id: str) -> bool:
    return bool(db_dash and user_id in (db_dash.hidden_by or []))


def _shared_group_ids(db_dash: Optional[GrafanaDashboard]) -> List[str]:
    return [str(g.id) for g in (db_dash.shared_groups or [])] if db_dash else []


def _db_dashboard_by_uid(db: Session, tenant_id: str, uid: str) -> Optional[GrafanaDashboard]:
    return (
        db.query(GrafanaDashboard)
        .filter(GrafanaDashboard.grafana_uid == uid, GrafanaDashboard.tenant_id == tenant_id)
        .first()
    )


def _db_dashboards_map(db: Session, tenant_id: str) -> Dict[str, GrafanaDashboard]:
    rows = (
        db.query(GrafanaDashboard)
        .filter(GrafanaDashboard.tenant_id == tenant_id)
        .limit(int(config.MAX_QUERY_LIMIT))
        .all()
    )
    return {d.grafana_uid: d for d in rows}


def _to_search_result(
    grafana_obj: object, *, db_dash: Optional[GrafanaDashboard], user_id: str
) -> DashboardSearchResult:
    payload = grafana_obj.model_dump() if hasattr(grafana_obj, "model_dump") else _json_dict(grafana_obj)
    if db_dash and db_dash.title:
        payload["title"] = db_dash.title
    payload["created_by"] = db_dash.created_by if db_dash else None
    payload["is_hidden"] = _is_hidden_for(db_dash, user_id)
    payload["is_owned"] = bool(db_dash and db_dash.created_by == user_id)
    payload["visibility"] = (db_dash.visibility if db_dash else "private") or "private"
    sgids = _shared_group_ids(db_dash)
    payload["shared_group_ids"] = sgids
    payload["sharedGroupIds"] = sgids
    return DashboardSearchResult.model_validate(payload)


async def _has_accessible_title_conflict(
    service: GrafanaProxyClient,
    db: Session,
    params: AccessibleTitleConflictParams,
) -> bool:
    target = _normalize_title(params.title)
    if not target:
        return False
    all_dashboards = await service.grafana_service.search_dashboards()
    live_conflicting_uids = {
        str(getattr(d, "uid"))
        for d in all_dashboards
        if getattr(d, "uid", None) and _normalize_title(getattr(d, "title", None)) == target
    }
    if not live_conflicting_uids:
        return False

    q = db.query(GrafanaDashboard).filter(
        GrafanaDashboard.tenant_id == params.tenant_id,
        GrafanaDashboard.grafana_uid.in_(live_conflicting_uids),
    )
    for dash in q.all():
        if params.exclude_uid and dash.grafana_uid == str(params.exclude_uid):
            continue
        if check_dashboard_access(
            db,
            dash.grafana_uid,
            GrafanaUserScope(user_id=params.user_id, tenant_id=params.tenant_id, group_ids=params.group_ids),
            DashboardAccessCriteria(),
        ) is not None:
            if not _title_conflict_matches_requested_scope(dash, params):
                continue
            return True
    return False


def _purge_stale_dashboards(
    db: Session,
    *,
    tenant_id: str,
    live_uids: set[str],
) -> None:
    if not live_uids:
        return
    stale_rows = (
        db.query(GrafanaDashboard)
        .filter(
            GrafanaDashboard.tenant_id == tenant_id,
            ~GrafanaDashboard.grafana_uid.in_(live_uids),
        )
        .all()
    )
    if not stale_rows:
        return
    for row in stale_rows:
        db.delete(row)
    db.commit()


def check_dashboard_access(
    db: Session,
    dashboard_uid: str,
    scope: GrafanaUserScope,
    criteria: DashboardAccessCriteria | None = None,
) -> Optional[GrafanaDashboard]:
    effective_criteria = criteria or DashboardAccessCriteria(require_write=False)
    dashboard = _db_dashboard_by_uid(db, scope.tenant_id, dashboard_uid)
    has_access = False
    if dashboard is not None:
        if dashboard.created_by == scope.user_id:
            has_access = True
        elif not effective_criteria.require_write:
            if dashboard.visibility == "tenant":
                has_access = True
            elif dashboard.visibility == "group":
                allowed = set(group_id_strs(scope.group_ids))
                shared = {str(g.id) for g in (dashboard.shared_groups or [])}
                has_access = bool(allowed.intersection(shared))
    return dashboard if has_access else None


def get_accessible_dashboard_uids(
    db: Session,
    user_id: str,
    tenant_id: str,
    group_ids: List[str],
) -> tuple[List[str], bool]:
    rows = (
        db.query(GrafanaDashboard.grafana_uid)
        .filter(GrafanaDashboard.tenant_id == tenant_id)
        .filter(_visible_scope_filter(user_id, group_ids))
        .limit(int(config.MAX_QUERY_LIMIT))
        .all()
    )
    return [uid for (uid,) in rows], False


def build_dashboard_search_context(
    db: Session,
    *,
    tenant_id: str,
    uid: Optional[str] = None,
) -> DashboardSearchContext:
    if uid:
        return {"uid_db_dashboard": _db_dashboard_by_uid(db, tenant_id, uid)}
    uids = (
        db.query(GrafanaDashboard.grafana_uid)
        .filter(GrafanaDashboard.tenant_id == tenant_id)
        .limit(int(config.MAX_QUERY_LIMIT))
        .all()
    )
    return {
        "all_registered_uids": {u for (u,) in uids},
        "db_dashboards": _db_dashboards_map(db, tenant_id),
    }


def _dashboard_has_datasource(dashboard_obj: object) -> bool:
    if not dashboard_obj:
        return False
    dash = dashboard_obj.model_dump() if hasattr(dashboard_obj, "model_dump") else _json_dict(dashboard_obj)

    templating = _json_dict(dash.get("templating"))
    templating_list = _json_dict_list(templating.get("list"))

    for item in templating_list:
        if item.get("type") == "datasource":
            current = _json_dict(item.get("current"))
            if current.get("value"):
                return True

    saw_query = False
    for panel in _json_dict_list(dash.get("panels")):
        pds = panel.get("datasource")
        panel_has_ds = bool(
            (isinstance(pds, str) and pds.strip())
            or (isinstance(pds, dict) and pds.get("uid"))
            or panel.get("datasourceUid")
        )
        for t in _json_dict_list(panel.get("targets")):
            requires_ds = bool(t.get("expr") or t.get("query") or t.get("rawQuery") or t.get("metric"))
            if not requires_ds:
                continue
            saw_query = True
            tds = t.get("datasource")
            target_has_ds = bool(
                t.get("datasourceUid")
                or (isinstance(tds, dict) and tds.get("uid"))
                or (isinstance(tds, str) and tds.strip())
            )
            if target_has_ds or panel_has_ds:
                return True

    return not saw_query


def _is_general_folder_id(folder_id: object) -> bool:
    if folder_id is None:
        return False
    if folder_id in ("", 0, "0"):
        return True
    parsed = _to_safe_int32(folder_id)
    if parsed is None:
        return False
    return parsed <= 0


def _is_non_general_folder_id(folder_id: object) -> bool:
    parsed = _to_safe_int32(folder_id)
    if parsed is None:
        return False
    return parsed > 0


async def _resolve_folder_uid_by_id(service: GrafanaProxyClient, folder_id: Optional[int]) -> Optional[str]:
    if not folder_id:
        return None
    try:
        target_id = int(folder_id)
    except (TypeError, ValueError):
        return None
    folders = await service.grafana_service.get_folders()
    for folder in folders:
        if getattr(folder, "id", None) == target_id:
            return str(getattr(folder, "uid", "") or "") or None
    return None
