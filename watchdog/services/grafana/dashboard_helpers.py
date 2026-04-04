"""
Helper utilities for Grafana dashboard operations.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, List, Optional, TypedDict

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from config import config
from custom_types.json import JSONDict
from db_models import GrafanaDashboard, Group
from models.grafana.grafana_dashboard_models import DashboardSearchResult
from services.grafana.shared_ops import group_id_strs

if TYPE_CHECKING:
    from services.grafana_proxy_service import GrafanaProxyService


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
    service: GrafanaProxyService,
    db: Session,
    *,
    tenant_id: str,
    user_id: str,
    group_ids: List[str],
    title: str,
    exclude_uid: Optional[str] = None,
) -> bool:
    target = _normalize_title(title)
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
        GrafanaDashboard.tenant_id == tenant_id,
        GrafanaDashboard.grafana_uid.in_(live_conflicting_uids),
    )
    for dash in q.all():
        if exclude_uid and dash.grafana_uid == str(exclude_uid):
            continue
        if check_dashboard_access(db, dash.grafana_uid, user_id, tenant_id, group_ids) is not None:
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
    user_id: str,
    tenant_id: str,
    group_ids: List[str],
    require_write: bool = False,
) -> Optional[GrafanaDashboard]:
    dashboard = _db_dashboard_by_uid(db, tenant_id, dashboard_uid)
    if not dashboard:
        return None
    if dashboard.created_by == user_id:
        return dashboard
    if require_write:
        return None
    if dashboard.visibility == "tenant":
        return dashboard
    if dashboard.visibility == "group":
        allowed = set(group_id_strs(group_ids))
        shared = {str(g.id) for g in (dashboard.shared_groups or [])}
        return dashboard if allowed.intersection(shared) else None
    return None


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
    if folder_id in ("", 0, "0"):
        return True
    if folder_id is None:
        return False
    if isinstance(folder_id, bool):
        return int(folder_id) <= 0
    if isinstance(folder_id, int):
        return folder_id <= 0
    if isinstance(folder_id, float):
        return int(folder_id) <= 0
    if not isinstance(folder_id, str):
        return False
    try:
        return int(folder_id) <= 0
    except (TypeError, ValueError):
        return False


def _is_non_general_folder_id(folder_id: object) -> bool:
    if folder_id in (None, "", 0, "0"):
        return False
    if isinstance(folder_id, bool):
        return int(folder_id) > 0
    if isinstance(folder_id, int):
        return folder_id > 0
    if isinstance(folder_id, float):
        return int(folder_id) > 0
    if not isinstance(folder_id, str):
        return False
    try:
        return int(folder_id) > 0
    except (TypeError, ValueError):
        return False


async def _resolve_folder_uid_by_id(service: GrafanaProxyService, folder_id: Optional[int]) -> Optional[str]:
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
