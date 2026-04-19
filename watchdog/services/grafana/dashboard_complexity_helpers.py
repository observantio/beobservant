"""
Grafana dashboard complexity helpers.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the
License. You may obtain a copy of the License at
http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Protocol, cast

import httpx
from fastapi import HTTPException
from sqlalchemy.orm import Session

from custom_types.json import JSONDict
from db_models import GrafanaDashboard, Group
from models.grafana.grafana_dashboard_models import DashboardCreate, DashboardSearchResult
from services.grafana.grafana_bundles import FolderAccessCriteria, GrafanaUserScope
from services.grafana.folder_ops import check_folder_access
from services.grafana.grafana_service import GrafanaAPIError
from services.grafana.grafana_bundles import GroupVisibilityValidation
from services.grafana.visibility import group_share_change_for_scope, resolve_group_share_on_visibility_change


class DashboardComplexityService(Protocol):
    grafana_service: Any
    logger: Any

    def raise_http_from_grafana_error(self, exc: GrafanaAPIError) -> None: ...

    def validate_group_visibility(self, db: Session, validation: GroupVisibilityValidation) -> List[Group]: ...


@dataclass(frozen=True, slots=True)
class DashboardVisibilityUpdateContext:
    db_dashboard: GrafanaDashboard
    scope: GrafanaUserScope
    visibility: Optional[str]
    shared_group_ids: Optional[list[str]]
    is_admin: bool


@dataclass(frozen=True, slots=True)
class DashboardUpdateMoveVisibilityContext:
    db_dashboard: GrafanaDashboard
    is_owner: bool
    visibility: Optional[str]
    shared_group_ids: Optional[list[str]]
    target_folder_uid: Optional[str]


@dataclass(frozen=True, slots=True)
class CreateDashboardAccessContext:
    db: Session
    folder_uid: Optional[str]
    user_id: str
    tenant_id: str
    gids: list[str]
    is_admin: bool
    has_create_scope: bool
    visibility: str
    shared_group_ids: Optional[list[str]]


@dataclass(frozen=True, slots=True)
class UpdateScopeAccessContext:
    db: Session
    db_dashboard: GrafanaDashboard
    is_owner: bool
    actor_permissions: Optional[list[str]]
    user_id: str
    tenant_id: str
    gids: list[str]
    is_admin: bool


def dedupe_search_dashboards(
    all_dashboards: List[DashboardSearchResult],
    dashboard_uid_set: set[str],
) -> List[DashboardSearchResult]:
    deduped: Dict[str, DashboardSearchResult] = {}
    for dashboard in all_dashboards:
        uid_val = str(getattr(dashboard, "uid", "") or "")
        if not uid_val or (dashboard_uid_set and uid_val not in dashboard_uid_set):
            continue
        current = deduped.get(uid_val)
        dashboard_has_folder = bool(getattr(dashboard, "folder_uid", None) or getattr(dashboard, "folderUid", None))
        current_has_folder = bool(
            current and (getattr(current, "folder_uid", None) or getattr(current, "folderUid", None))
        )
        if current is None or (dashboard_has_folder and not current_has_folder):
            deduped[uid_val] = dashboard
    return list(deduped.values())


async def create_dashboard_in_grafana(
    service: DashboardComplexityService,
    dashboard_create: DashboardCreate,
) -> Optional[JSONDict]:
    dash_obj = getattr(dashboard_create, "dashboard", None)
    try:
        created = await service.grafana_service.create_dashboard(dashboard_create)
        return cast(Optional[JSONDict], created)
    except GrafanaAPIError as exc:
        status = getattr(exc, "status", None)
        dash_uid = getattr(dash_obj, "uid", None) if dash_obj is not None else None
        if status in {409, 412} and dash_uid and dash_obj is not None:
            next_uid = f"{str(dash_uid)}-{uuid.uuid4().hex[:6]}"
            retry_payload = dashboard_create.model_copy(
                update={"dashboard": dash_obj.model_copy(update={"uid": next_uid})}
            )
            try:
                created = await service.grafana_service.create_dashboard(retry_payload)
                return cast(Optional[JSONDict], created)
            except GrafanaAPIError as retry_exc:
                service.raise_http_from_grafana_error(retry_exc)
                return None
        service.raise_http_from_grafana_error(exc)
        return None


async def resolve_created_folder_uid(
    service: DashboardComplexityService,
    dashboard_create: DashboardCreate,
    result: JSONDict,
    dashboard_data: JSONDict,
) -> Optional[str]:
    folder_uid_value = result.get("folderUid") or dashboard_data.get("folderUid")
    folder_uid = folder_uid_value if isinstance(folder_uid_value, str) else None
    if folder_uid:
        return folder_uid

    folder_id = getattr(dashboard_create, "folder_id", None)
    if folder_id:
        try:
            for folder in await service.grafana_service.get_folders():
                if folder.id == folder_id:
                    uid = getattr(folder, "uid", None)
                    return uid if isinstance(uid, str) else None
        except (httpx.HTTPError, RuntimeError, ValueError) as exc:
            service.logger.debug("Unable to resolve folder uid for created dashboard: %s", exc)
    return None


def apply_dashboard_visibility_update(
    service: DashboardComplexityService,
    db: Session,
    context: DashboardVisibilityUpdateContext,
) -> None:
    if not context.visibility:
        return
    context.db_dashboard.visibility = context.visibility
    if context.visibility == "group" and context.shared_group_ids is not None:
        groups = resolve_group_share_on_visibility_change(
            service,
            db,
            group_share_change_for_scope(
                context.scope,
                visibility=context.visibility,
                shared_group_ids=context.shared_group_ids,
                is_admin=context.is_admin,
            ),
        )
        context.db_dashboard.shared_groups.clear()
        context.db_dashboard.shared_groups.extend(groups)
    elif context.visibility != "group":
        context.db_dashboard.shared_groups.clear()


def validate_update_move_and_visibility(
    context: DashboardUpdateMoveVisibilityContext,
    shared_group_ids_getter: Callable[[GrafanaDashboard], list[str]],
) -> None:
    if context.is_owner:
        return
    current_visibility = (context.db_dashboard.visibility or "private") or "private"
    if context.visibility is not None and str(context.visibility) != str(current_visibility):
        raise HTTPException(status_code=403, detail="Only owners can change dashboard visibility")
    if context.shared_group_ids is not None:
        requested_groups = {str(group_id) for group_id in (context.shared_group_ids or [])}
        current_groups = set(shared_group_ids_getter(context.db_dashboard))
        if requested_groups != current_groups:
            raise HTTPException(status_code=403, detail="Only owners can change dashboard visibility")
    if context.target_folder_uid and str(context.target_folder_uid) != str(context.db_dashboard.folder_uid or ""):
        raise HTTPException(status_code=403, detail="Only owners can move dashboards between folders")


def validate_create_dashboard_access(context: CreateDashboardAccessContext) -> None:
    target_folder = None
    if context.folder_uid:
        target_folder = check_folder_access(
            context.db,
            context.folder_uid,
            GrafanaUserScope(context.user_id, context.tenant_id, context.gids),
            FolderAccessCriteria(require_write=False, is_admin=context.is_admin, include_hidden=False),
        )
    if context.folder_uid and not target_folder:
        raise HTTPException(status_code=403, detail="Folder access denied")
    if (
        target_folder
        and str(getattr(target_folder, "created_by", "")) != str(context.user_id)
        and not bool(getattr(target_folder, "allow_dashboard_writes", False))
    ):
        raise HTTPException(status_code=403, detail="Folder is owner-only for dashboard creation")
    if not context.has_create_scope:
        if not target_folder:
            raise HTTPException(status_code=403, detail="Missing permission to create dashboards")
        if context.visibility != "private" or context.shared_group_ids:
            raise HTTPException(
                status_code=403,
                detail="Delegated folder dashboard creation only supports private visibility",
            )


def ensure_update_scope_access(context: UpdateScopeAccessContext) -> bool:
    if context.actor_permissions is None:
        has_update_scope = True
    else:
        perm_set = {
            str(permission).strip()
            for permission in (context.actor_permissions or [])
            if str(permission).strip()
        }
        has_update_scope = bool({"update:dashboards", "write:dashboards"} & perm_set)

    delegated_update_allowed = False
    if not context.is_owner and context.db_dashboard.folder_uid:
        folder = check_folder_access(
            context.db,
            context.db_dashboard.folder_uid,
            GrafanaUserScope(context.user_id, context.tenant_id, context.gids),
            FolderAccessCriteria(require_write=False, is_admin=context.is_admin, include_hidden=False),
        )
        delegated_update_allowed = bool(folder and bool(getattr(folder, "allow_dashboard_writes", False)))

    if not context.is_owner and not delegated_update_allowed:
        return False
    if not has_update_scope and not delegated_update_allowed:
        raise HTTPException(status_code=403, detail="Missing permission to update dashboards")
    return True
