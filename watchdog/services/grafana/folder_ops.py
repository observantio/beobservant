"""
Folder operations for Grafana integration.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the
License. You may obtain a copy of the License at
http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

import httpx
from fastapi import HTTPException
from sqlalchemy.orm import Session

from config import config
from custom_types.json import JSONDict
from db_models import GrafanaFolder
from models.grafana.grafana_folder_models import Folder
from services.grafana.grafana_bundles import (
    FolderAccessCriteria,
    FolderCreateRequest,
    FolderDeleteRequest,
    FolderGetRequest,
    FolderListParams,
    FolderUpdateRequest,
    GrafanaUserScope,
    GroupVisibilityValidation,
    HiddenToggleParams,
)
from services.grafana.grafana_service import GrafanaAPIError
from services.grafana.proxy_client import GrafanaProxyClient
from services.grafana.shared_ops import commit_session, group_id_strs, update_hidden_members
from services.grafana.visibility import resolve_visibility_groups_for_scope, visibility_group_resolve_context


def _db_folder_by_uid(db: Session, tenant_id: str, uid: str) -> GrafanaFolder | None:
    return (
        db.query(GrafanaFolder).filter(GrafanaFolder.tenant_id == tenant_id, GrafanaFolder.grafana_uid == uid).first()
    )


def check_folder_access(
    db: Session,
    uid: str,
    scope: GrafanaUserScope,
    criteria: FolderAccessCriteria,
) -> GrafanaFolder | None:
    folder = _db_folder_by_uid(db, scope.tenant_id, uid)
    has_access = False
    if folder is not None:
        is_hidden = scope.user_id in (folder.hidden_by or [])
        if not (is_hidden and not criteria.include_hidden):
            if folder.created_by == scope.user_id:
                has_access = True
            elif not criteria.require_write:
                if folder.visibility == "tenant":
                    has_access = True
                elif folder.visibility == "group":
                    allowed = set(group_id_strs(scope.group_ids))
                    shared = {str(g.id) for g in (folder.shared_groups or [])}
                    has_access = bool(allowed.intersection(shared))
    return folder if has_access else None


def is_folder_accessible(
    db: Session,
    uid: str | None,
    scope: GrafanaUserScope,
    criteria: FolderAccessCriteria,
) -> bool:
    if not uid:
        return True
    db_folder = _db_folder_by_uid(db, scope.tenant_id, uid)
    if db_folder is None:
        return False
    folder = check_folder_access(
        db,
        uid,
        scope,
        criteria,
    )
    return folder is not None


def _folder_payload(folder_obj: object, *, db_folder: GrafanaFolder | None, user_id: str) -> JSONDict:
    if hasattr(folder_obj, "model_dump"):
        payload = folder_obj.model_dump()
    elif isinstance(folder_obj, dict):
        payload = dict(folder_obj)
    else:
        payload = dict(vars(folder_obj))
    payload["created_by"] = db_folder.created_by if db_folder else None
    payload["visibility"] = (db_folder.visibility if db_folder else "tenant") or "tenant"
    payload["sharedGroupIds"] = [str(g.id) for g in (db_folder.shared_groups or [])] if db_folder else []
    payload["allowDashboardWrites"] = bool(getattr(db_folder, "allow_dashboard_writes", False)) if db_folder else False
    payload["isHidden"] = bool(db_folder and user_id in (db_folder.hidden_by or []))
    payload["is_owned"] = bool(db_folder and db_folder.created_by == user_id)
    return payload if isinstance(payload, dict) else {}


async def get_folders(
    service: GrafanaProxyClient,
    db: Session,
    scope: GrafanaUserScope,
    params: FolderListParams,
) -> list[Folder]:
    user_id = scope.user_id
    tenant_id = scope.tenant_id
    show_hidden = params.show_hidden
    is_admin = params.is_admin
    folders = await service.grafana_service.get_folders()
    db_rows = (
        db.query(GrafanaFolder).filter(GrafanaFolder.tenant_id == tenant_id).limit(int(config.MAX_QUERY_LIMIT)).all()
    )
    db_map = {f.grafana_uid: f for f in db_rows}
    access = FolderAccessCriteria(
        require_write=False,
        is_admin=is_admin,
        include_hidden=show_hidden,
    )

    out: list[Folder] = []
    for folder in folders:
        uid = str(getattr(folder, "uid", "") or "")
        db_folder = db_map.get(uid)
        if not db_folder:
            continue
        if not check_folder_access(db, uid, scope, access):
            continue
        out.append(Folder.model_validate(_folder_payload(folder, db_folder=db_folder, user_id=user_id)))
    return out


async def get_folder(
    service: GrafanaProxyClient,
    db: Session,
    request: FolderGetRequest,
) -> Folder | None:
    user_id = request.scope.user_id
    tenant_id = request.scope.tenant_id
    db_folder = _db_folder_by_uid(db, tenant_id, request.uid)
    if not db_folder:
        return None
    if not check_folder_access(
        db,
        request.uid,
        request.scope,
        FolderAccessCriteria(
            require_write=False,
            is_admin=request.params.is_admin,
            include_hidden=False,
        ),
    ):
        return None
    folder = await service.grafana_service.get_folder(request.uid)
    if not folder:
        return None
    return Folder.model_validate(_folder_payload(folder, db_folder=db_folder, user_id=user_id))


async def create_folder(
    service: GrafanaProxyClient,
    db: Session,
    request: FolderCreateRequest,
) -> Folder | None:
    user_id = request.scope.user_id
    tenant_id = request.scope.tenant_id
    visibility = request.options.visibility
    shared_group_ids = request.options.shared_group_ids
    allow_dashboard_writes = request.options.allow_dashboard_writes
    is_admin = request.options.is_admin
    groups = resolve_visibility_groups_for_scope(
        service,
        db,
        visibility_group_resolve_context(
            request.scope,
            visibility=visibility,
            shared_group_ids=shared_group_ids,
            is_admin=is_admin,
        ),
    )

    try:
        created = await service.grafana_service.create_folder(request.title)
    except (GrafanaAPIError, httpx.HTTPError) as exc:
        service.raise_http_from_grafana_error(exc)
        return None
    if not created:
        return None

    uid = str(getattr(created, "uid", "") or "")
    if not uid:
        return (
            created
            if isinstance(created, Folder)
            else Folder.model_validate(_folder_payload(created, db_folder=None, user_id=user_id))
        )

    db_folder = GrafanaFolder(
        tenant_id=tenant_id,
        created_by=user_id,
        grafana_uid=uid,
        grafana_id=getattr(created, "id", None),
        title=str(getattr(created, "title", request.title) or request.title),
        visibility=visibility or "private",
        allow_dashboard_writes=bool(allow_dashboard_writes),
        hidden_by=[],
    )
    if visibility == "group" and shared_group_ids:
        db_folder.shared_groups.extend(groups)

    db.add(db_folder)
    commit_session(db)

    return Folder.model_validate(_folder_payload(created, db_folder=db_folder, user_id=user_id))


async def update_folder(
    service: GrafanaProxyClient,
    db: Session,
    request: FolderUpdateRequest,
) -> Folder | None:
    user_id = request.scope.user_id
    tenant_id = request.scope.tenant_id
    group_ids = request.scope.group_ids
    title = request.options.title
    visibility = request.options.visibility
    shared_group_ids = request.options.shared_group_ids
    allow_dashboard_writes = request.options.allow_dashboard_writes
    is_admin = request.options.is_admin
    db_folder = _db_folder_by_uid(db, tenant_id, request.uid)
    if not db_folder:
        return None
    if not check_folder_access(
        db,
        request.uid,
        request.scope,
        FolderAccessCriteria(require_write=True, is_admin=is_admin, include_hidden=False),
    ):
        return None

    new_title = str(title or db_folder.title).strip()
    try:
        updated = await service.grafana_service.update_folder(request.uid, new_title)
    except GrafanaAPIError as exc:
        if exc.status == 412:
            raise HTTPException(
                status_code=409,
                detail="Folder changed by another request; reload folders and retry.",
            ) from exc
        service.raise_http_from_grafana_error(exc)
        return None
    if not updated:
        return None

    db_folder.title = str(getattr(updated, "title", new_title) or new_title)
    if allow_dashboard_writes is not None:
        db_folder.allow_dashboard_writes = bool(allow_dashboard_writes)
    if visibility:
        db_folder.visibility = visibility
        if visibility == "group":
            groups = service.validate_group_visibility(
                db,
                GroupVisibilityValidation(
                    user_id=user_id,
                    tenant_id=tenant_id,
                    group_ids=group_ids,
                    shared_group_ids=shared_group_ids,
                    is_admin=is_admin,
                ),
            )
            db_folder.shared_groups.clear()
            db_folder.shared_groups.extend(groups)
        else:
            db_folder.shared_groups.clear()

    commit_session(db)

    return Folder.model_validate(_folder_payload(updated, db_folder=db_folder, user_id=user_id))


async def delete_folder(
    service: GrafanaProxyClient,
    db: Session,
    request: FolderDeleteRequest,
) -> bool:
    tenant_id = request.scope.tenant_id
    is_admin = request.options.is_admin
    db_folder = _db_folder_by_uid(db, tenant_id, request.uid)
    if not db_folder:
        return False
    if not check_folder_access(
        db,
        request.uid,
        request.scope,
        FolderAccessCriteria(require_write=True, is_admin=is_admin, include_hidden=False),
    ):
        return False

    try:
        ok = await service.grafana_service.delete_folder(request.uid)
    except (GrafanaAPIError, httpx.HTTPError) as exc:
        service.raise_http_from_grafana_error(exc)
        return False
    if not ok:
        return False

    if db_folder:
        db.delete(db_folder)
        commit_session(db)
    return True


def toggle_folder_hidden(
    db: Session,
    uid: str,
    scope: GrafanaUserScope,
    params: HiddenToggleParams,
) -> bool:
    db_folder = _db_folder_by_uid(db, scope.tenant_id, uid)
    if not db_folder:
        return False
    if params.hidden and str(getattr(db_folder, "created_by", "")) == str(scope.user_id):
        raise HTTPException(status_code=400, detail="You cannot hide folders you own")
    db_folder.hidden_by = update_hidden_members(db_folder.hidden_by, scope.user_id, params.hidden)
    commit_session(db)
    return True
