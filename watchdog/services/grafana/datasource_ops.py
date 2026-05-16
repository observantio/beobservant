"""
Datasource operations for Grafana integration.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the
License. You may obtain a copy of the License at
http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

import re
import uuid
from typing import TypedDict, cast

from config import config
from custom_types.json import JSONDict
from db_models import ApiKeyShare, GrafanaDatasource, Group, User, UserApiKey
from fastapi import HTTPException
from models.grafana.grafana_datasource_models import Datasource, DatasourceCreate, DatasourceUpdate
from services.grafana.datasource_payloads import (
    enrich_datasource_payload,
    is_safe_system_datasource,
    normalize_datasource_name,
    sanitize_datasource_payload,
)
from services.grafana.datasource_workflows import (
    DatasourceLookupContext,
    DatasourceScopeDefaultsContext,
    DatasourceVisibilityContext,
    apply_scoped_datasource_defaults,
    matches_datasource_query,
    matches_datasource_team_filter,
    persist_datasource_create,
    persist_datasource_update,
    resolve_visibility_groups,
    validate_datasource_lookup,
)
from services.grafana.grafana_bundles import (
    AccessibleDsNameConflictParams,
    DatasourceAccessCriteria,
    DatasourceCreateOptions,
    DatasourceCreateRequest,
    DatasourceListParams,
    DatasourceQueryEnforcement,
    DatasourceUpdateOptions,
    DatasourceUpdateRequest,
    GrafanaUserScope,
    HiddenToggleParams,
)
from services.grafana.proxy_client import GrafanaProxyClient
from services.grafana.shared_ops import commit_session, group_id_strs, update_hidden_members
from services.grafana.visibility import (
    group_share_change_for_scope,
    resolve_group_share_on_visibility_change,
)
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

DS_PROXY_ID_RE = re.compile(r"/api/datasources/proxy/(\d+)")


class DatasourceListContext(TypedDict, total=False):
    uid_db_datasource: GrafanaDatasource | None
    db_entries: dict[str, GrafanaDatasource]
    all_registered_uids: set[str]


def _cap(limit: int | None, offset: int) -> tuple[int, int]:
    mx = int(config.MAX_QUERY_LIMIT)
    req = int(limit) if limit is not None else int(config.DEFAULT_QUERY_LIMIT)
    return max(1, min(req, mx)), max(0, int(offset))


def _sanitize_datasource_payload(payload: JSONDict, *, is_owner: bool) -> JSONDict:
    return sanitize_datasource_payload(payload, is_owner=is_owner)


def _normalize_name(name: str | None) -> str:
    return normalize_datasource_name(name)


def _build_internal_name(display_name: str, user_id: str) -> str:
    suffix = uuid.uuid4().hex[:6]
    return f"{display_name}__bo_{str(user_id)[:8]}_{suffix}"


def _is_safe_system_datasource(datasource: object) -> bool:
    return is_safe_system_datasource(datasource)


def _db_datasource_by_uid(db: Session, tenant_id: str, uid: str) -> GrafanaDatasource | None:
    return (
        db.query(GrafanaDatasource)
        .filter(GrafanaDatasource.grafana_uid == uid, GrafanaDatasource.tenant_id == tenant_id)
        .first()
    )


def _load_allowed_scope_org_ids(db: Session, *, user_id: str, tenant_id: str) -> tuple[str, set[str]]:
    user = db.query(User).filter_by(id=user_id, tenant_id=tenant_id).first()
    if not user or not getattr(user, "is_active", False):
        raise HTTPException(status_code=403, detail="User is not active in tenant scope")

    default_scope = str(getattr(user, "org_id", "") or config.DEFAULT_ORG_ID)
    allowed: set[str] = {default_scope, str(config.DEFAULT_ORG_ID)}

    own_rows = (
        db.query(UserApiKey.key)
        .filter(
            UserApiKey.user_id == user_id,
            UserApiKey.tenant_id == tenant_id,
        )
        .all()
    )
    allowed.update(str(r[0]) for r in own_rows if r and r[0])

    shared_rows = (
        db.query(UserApiKey.key)
        .join(ApiKeyShare, ApiKeyShare.api_key_id == UserApiKey.id)
        .filter(
            ApiKeyShare.shared_user_id == user_id,
            ApiKeyShare.can_use.is_(True),
            ApiKeyShare.tenant_id == tenant_id,
            UserApiKey.tenant_id == tenant_id,
        )
        .all()
    )
    allowed.update(str(r[0]) for r in shared_rows if r and r[0])
    return default_scope, {v for v in allowed if v}


def _scope_conflicts_with_other_tenants(db: Session, *, org_id: str, tenant_id: str) -> bool:
    return (
        db.query(UserApiKey.id).filter(UserApiKey.key == org_id, UserApiKey.tenant_id != tenant_id).first() is not None
    )


def _resolve_datasource_org_scope(
    db: Session,
    *,
    requested_org_id: str | None,
    user_id: str,
    tenant_id: str,
) -> str:
    default_scope, allowed_scopes = _load_allowed_scope_org_ids(db, user_id=user_id, tenant_id=tenant_id)
    candidate = str(requested_org_id or "").strip() or default_scope
    if candidate not in allowed_scopes:
        raise HTTPException(status_code=403, detail="Requested datasource org_id is not permitted for this user")
    if _scope_conflicts_with_other_tenants(db, org_id=candidate, tenant_id=tenant_id):
        raise HTTPException(status_code=403, detail="Requested datasource org_id is ambiguous across tenants")
    return candidate


async def _has_accessible_name_conflict(
    service: GrafanaProxyClient,
    db: Session,
    params: AccessibleDsNameConflictParams,
) -> bool:
    target = normalize_datasource_name(params.name)
    if not target:
        return False

    all_datasources = await service.grafana_service.get_datasources()
    db_entries = (
        db.query(GrafanaDatasource)
        .filter(GrafanaDatasource.tenant_id == params.tenant_id)
        .limit(int(config.MAX_QUERY_LIMIT))
        .all()
    )
    db_map = {d.grafana_uid: d for d in db_entries}
    all_registered_uids = set(db_map.keys())
    accessible_uids, allow_system = get_accessible_datasource_uids(
        service,
        db,
        GrafanaUserScope(user_id=params.user_id, tenant_id=params.tenant_id, group_ids=params.group_ids),
    )
    accessible = set(accessible_uids)

    for datasource in all_datasources:
        uid = str(getattr(datasource, "uid", "") or "")
        if not uid:
            continue
        if params.exclude_uid and uid == str(params.exclude_uid):
            continue
        is_unregistered_safe = allow_system and uid not in all_registered_uids and is_safe_system_datasource(datasource)
        if uid not in accessible and not is_unregistered_safe:
            continue
        db_ds = db_map.get(uid)
        if db_ds and params.user_id in (db_ds.hidden_by or []):
            continue
        visible_name = db_ds.name if (db_ds and db_ds.name) else getattr(datasource, "name", "")
        if normalize_datasource_name(visible_name) == target:
            return True

    return False


def check_datasource_access(
    db: Session,
    datasource_uid: str,
    scope: GrafanaUserScope,
    criteria: DatasourceAccessCriteria | None = None,
) -> GrafanaDatasource | None:
    effective_criteria = criteria or DatasourceAccessCriteria(require_write=False)
    datasource = (
        db.query(GrafanaDatasource)
        .filter(
            GrafanaDatasource.grafana_uid == datasource_uid,
            GrafanaDatasource.tenant_id == scope.tenant_id,
        )
        .first()
    )
    has_access = False
    if datasource is not None:
        if datasource.created_by == scope.user_id:
            has_access = True
        elif not effective_criteria.require_write:
            if datasource.visibility == "tenant":
                has_access = True
            elif datasource.visibility == "group":
                allowed = set(group_id_strs(scope.group_ids))
                shared = {str(g.id) for g in (datasource.shared_groups or [])}
                has_access = bool(allowed.intersection(shared))
    return datasource if has_access else None


def check_datasource_access_by_id(
    db: Session,
    datasource_id: int,
    scope: GrafanaUserScope,
    criteria: DatasourceAccessCriteria | None = None,
) -> GrafanaDatasource | None:
    effective_criteria = criteria or DatasourceAccessCriteria(require_write=False)
    datasource = (
        db.query(GrafanaDatasource)
        .filter(
            GrafanaDatasource.grafana_id == datasource_id,
            GrafanaDatasource.tenant_id == scope.tenant_id,
        )
        .first()
    )
    has_access = False
    if datasource is not None:
        if datasource.created_by == scope.user_id:
            has_access = True
        elif not effective_criteria.require_write:
            if datasource.visibility == "tenant":
                has_access = True
            elif datasource.visibility == "group":
                allowed = set(group_id_strs(scope.group_ids))
                shared = {str(g.id) for g in (datasource.shared_groups or [])}
                has_access = bool(allowed.intersection(shared))
    return datasource if has_access else None


def get_accessible_datasource_uids(
    _service: GrafanaProxyClient,
    db: Session,
    scope: GrafanaUserScope,
) -> tuple[list[str], bool]:
    conditions = [GrafanaDatasource.created_by == scope.user_id, GrafanaDatasource.visibility == "tenant"]
    if scope.group_ids:
        conditions.append(
            and_(
                GrafanaDatasource.visibility == "group",
                GrafanaDatasource.shared_groups.any(Group.id.in_(scope.group_ids)),
            )
        )
    rows = (
        db.query(GrafanaDatasource.grafana_uid)
        .filter(GrafanaDatasource.tenant_id == scope.tenant_id)
        .filter(or_(*conditions))
        .limit(int(config.MAX_QUERY_LIMIT))
        .all()
    )
    return [uid for (uid,) in rows], True


def build_datasource_list_context(
    _service: GrafanaProxyClient,
    db: Session,
    *,
    tenant_id: str,
    uid: str | None = None,
) -> DatasourceListContext:
    if uid:
        return {"uid_db_datasource": _db_datasource_by_uid(db, tenant_id, uid)}
    rows = (
        db.query(GrafanaDatasource)
        .filter(GrafanaDatasource.tenant_id == tenant_id)
        .limit(int(config.MAX_QUERY_LIMIT))
        .all()
    )
    db_entries = {d.grafana_uid: d for d in rows}
    return {"db_entries": db_entries, "all_registered_uids": set(db_entries.keys())}


def collect_datasource_refs_from_query_payload(payload: object) -> set[str]:
    refs: set[str] = set()

    def walk(value: object) -> None:
        if isinstance(value, dict):
            uid = value.get("datasourceUid")
            if isinstance(uid, str) and uid:
                refs.add(uid)
            ds_obj = value.get("datasource")
            if isinstance(ds_obj, dict):
                uid_val = ds_obj.get("uid")
                if isinstance(uid_val, str) and uid_val:
                    refs.add(uid_val)
            for nested in value.values():
                walk(nested)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(payload)
    return refs


async def enforce_datasource_query_access(
    service: GrafanaProxyClient,
    db: Session,
    scope: GrafanaUserScope,
    enforcement: DatasourceQueryEnforcement,
) -> None:
    user_id = scope.user_id
    tenant_id = scope.tenant_id
    group_ids = scope.group_ids
    path = enforcement.path
    method = enforcement.method
    body = enforcement.body
    if method.upper() != "POST":
        return
    if not (path.startswith("/api/ds/query") or "/api/datasources/proxy/" in path):
        return

    referenced_uids = collect_datasource_refs_from_query_payload(body)

    id_match = DS_PROXY_ID_RE.search(path)
    if id_match:
        ds_id = int(id_match.group(1))
        ds = check_datasource_access_by_id(
            db,
            ds_id,
            GrafanaUserScope(user_id=user_id, tenant_id=tenant_id, group_ids=group_ids),
            DatasourceAccessCriteria(),
        )
        if not ds:
            maybe = (
                db.query(GrafanaDatasource)
                .filter(GrafanaDatasource.grafana_id == ds_id, GrafanaDatasource.tenant_id == tenant_id)
                .first()
            )
            if maybe is not None:
                raise HTTPException(status_code=403, detail="Datasource access denied")

    for datasource_uid in referenced_uids:
        ds = check_datasource_access(
            db,
            datasource_uid,
            GrafanaUserScope(user_id=user_id, tenant_id=tenant_id, group_ids=group_ids),
            DatasourceAccessCriteria(),
        )
        if ds:
            continue
        maybe = (
            db.query(GrafanaDatasource)
            .filter(GrafanaDatasource.grafana_uid == datasource_uid, GrafanaDatasource.tenant_id == tenant_id)
            .first()
        )
        if maybe is not None:
            raise HTTPException(status_code=403, detail="Datasource access denied")
        grafana_ds = await service.grafana_service.get_datasource(datasource_uid)
        if grafana_ds and is_safe_system_datasource(grafana_ds):
            continue
        raise HTTPException(status_code=403, detail="Datasource access denied")


async def get_datasources(
    service: GrafanaProxyClient,
    db: Session,
    scope: GrafanaUserScope,
    params: DatasourceListParams,
) -> list[Datasource]:
    user_id = scope.user_id
    tenant_id = scope.tenant_id
    group_ids = scope.group_ids
    uid = params.uid
    query = params.query
    team_id = params.team_id
    show_hidden = params.show_hidden
    limit = params.limit
    offset = params.offset
    datasource_context = params.datasource_context
    capped_limit, capped_offset = _cap(limit, offset)
    query_lc = str(query or "").strip().lower()

    effective_scope = GrafanaUserScope(user_id=user_id, tenant_id=tenant_id, group_ids=group_ids)
    if uid:
        datasource = await service.grafana_service.get_datasource(uid)
        if not datasource:
            return []
        effective_context = cast(
            DatasourceListContext,
            datasource_context or build_datasource_list_context(service, db, tenant_id=tenant_id, uid=uid),
        )
        db_ds = effective_context.get("uid_db_datasource")
        if not validate_datasource_lookup(
            db,
            DatasourceLookupContext(
                uid=uid,
                scope=effective_scope,
                datasource=datasource,
                db_ds=db_ds,
                show_hidden=show_hidden,
            ),
            access_check=check_datasource_access,
        ):
            return []
        payload = enrich_datasource_payload(datasource.model_dump(), db_ds=db_ds, user_id=user_id)
        return [Datasource.model_validate(payload)]

    all_datasources = await service.grafana_service.get_datasources()
    accessible_uids, allow_system = get_accessible_datasource_uids(
        service,
        db,
        effective_scope,
    )
    accessible = set(accessible_uids)

    effective_context = cast(
        DatasourceListContext,
        datasource_context or build_datasource_list_context(service, db, tenant_id=tenant_id),
    )
    all_registered_uids = set(effective_context.get("all_registered_uids") or set())
    db_entries = effective_context.get("db_entries") or {}

    out: list[Datasource] = []
    for d in all_datasources:
        uid_val = str(getattr(d, "uid", "") or "")
        if not uid_val:
            continue
        is_unregistered_safe = allow_system and uid_val not in all_registered_uids and is_safe_system_datasource(d)
        if uid_val not in accessible and not is_unregistered_safe:
            continue
        db_ds = db_entries.get(uid_val)
        if db_ds and not show_hidden and user_id in (db_ds.hidden_by or []):
            continue
        if not matches_datasource_team_filter(db_ds=db_ds, team_id=team_id):
            continue
        if not matches_datasource_query(d, db_ds=db_ds, uid=uid_val, query_lc=query_lc):
            continue
        payload = enrich_datasource_payload(
            d.model_dump(), db_ds=db_ds, user_id=user_id, is_unregistered_safe_system=is_unregistered_safe
        )
        out.append(Datasource.model_validate(payload))

    return out[capped_offset : capped_offset + capped_limit]


async def get_datasource(
    service: GrafanaProxyClient,
    db: Session,
    uid: str,
    scope: GrafanaUserScope,
) -> Datasource | None:
    user_id = scope.user_id
    tenant_id = scope.tenant_id
    group_ids = scope.group_ids
    db_ds = _db_datasource_by_uid(db, tenant_id, uid)
    ds = await service.grafana_service.get_datasource(uid)
    if not ds:
        return None
    if db_ds:
        if (
            check_datasource_access(
                db,
                uid,
                GrafanaUserScope(user_id=user_id, tenant_id=tenant_id, group_ids=group_ids),
                DatasourceAccessCriteria(),
            )
            is None
        ):
            return None
    elif not is_safe_system_datasource(ds):
        return None
    payload = enrich_datasource_payload(ds.model_dump(), db_ds=db_ds, user_id=user_id)
    return Datasource.model_validate(payload)


async def get_datasource_by_name(
    service: GrafanaProxyClient,
    db: Session,
    name: str,
    scope: GrafanaUserScope,
) -> Datasource | None:
    user_id = scope.user_id
    tenant_id = scope.tenant_id
    group_ids = scope.group_ids
    ds = await service.grafana_service.get_datasource_by_name(name)
    if not ds:
        return None
    uid = str(getattr(ds, "uid", "") or "")
    db_ds = _db_datasource_by_uid(db, tenant_id, uid) if uid else None
    if db_ds:
        if (
            check_datasource_access(
                db,
                uid,
                GrafanaUserScope(user_id=user_id, tenant_id=tenant_id, group_ids=group_ids),
                DatasourceAccessCriteria(),
            )
            is None
        ):
            return None
    elif not is_safe_system_datasource(ds):
        return None
    payload = enrich_datasource_payload(ds.model_dump(), db_ds=db_ds, user_id=user_id)
    return Datasource.model_validate(payload)


async def create_datasource(
    service: GrafanaProxyClient,
    db: Session,
    datasource_create: DatasourceCreate | DatasourceCreateRequest,
    *,
    scope: GrafanaUserScope | None = None,
    options: DatasourceCreateOptions | None = None,
) -> Datasource | None:
    if isinstance(datasource_create, DatasourceCreateRequest):
        request = datasource_create
        datasource_create = request.datasource_create
        scope = request.scope
        options = request.options
    if scope is None:
        raise TypeError("scope is required")
    options = options or DatasourceCreateOptions()

    user_id = scope.user_id
    tenant_id = scope.tenant_id
    group_ids = scope.group_ids
    visibility = options.visibility
    shared_group_ids = options.shared_group_ids
    is_admin = options.is_admin
    requested_name = str(getattr(datasource_create, "name", "") or "").strip()
    if requested_name and await _has_accessible_name_conflict(
        service,
        db,
        AccessibleDsNameConflictParams(
            tenant_id=tenant_id,
            user_id=user_id,
            group_ids=group_ids,
            name=requested_name,
        ),
    ):
        raise HTTPException(status_code=409, detail="Datasource name already exists in your visible scope")

    datasource_create = cast(
        DatasourceCreate,
        apply_scoped_datasource_defaults(
            db,
            DatasourceScopeDefaultsContext(
                datasource=datasource_create,
                user_id=user_id,
                tenant_id=tenant_id,
            ),
            resolve_org_scope=_resolve_datasource_org_scope,
        ),
    )
    groups = resolve_visibility_groups(
        service,
        db,
        DatasourceVisibilityContext(
            scope=GrafanaUserScope(user_id, tenant_id, group_ids),
            visibility=visibility,
            shared_group_ids=shared_group_ids,
            is_admin=is_admin,
        ),
    )
    result = await persist_datasource_create(
        service,
        datasource_create,
        requested_name=requested_name,
        user_id=user_id,
    )

    if not result:
        return None

    db_ds = GrafanaDatasource(
        tenant_id=tenant_id,
        created_by=user_id,
        grafana_uid=result.uid,
        grafana_id=result.id,
        name=requested_name or result.name,
        type=result.type,
        visibility=visibility,
    )
    if visibility == "group" and shared_group_ids:
        db_ds.shared_groups.extend(groups)

    try:
        db.add(db_ds)
        db.commit()
    except Exception:
        db.rollback()
        raise

    payload = enrich_datasource_payload(result.model_dump(), db_ds=db_ds, user_id=user_id)
    requested_json_data = dict(getattr(datasource_create, "json_data", None) or {})
    if requested_json_data and not payload.get("jsonData"):
        payload["jsonData"] = requested_json_data
    return Datasource.model_validate(payload)


async def update_datasource(
    service: GrafanaProxyClient,
    db: Session,
    request: DatasourceUpdateRequest | str,
    *,
    datasource_update: DatasourceUpdate | None = None,
    scope: GrafanaUserScope | None = None,
) -> Datasource | None:
    options: DatasourceUpdateOptions | None = None
    if isinstance(request, DatasourceUpdateRequest):
        uid = request.uid
        datasource_update = request.datasource_update
        scope = request.scope
        options = request.options
    else:
        uid = request
    if datasource_update is None or scope is None:
        raise TypeError("datasource_update and scope are required")
    options = options or DatasourceUpdateOptions()

    user_id = scope.user_id
    tenant_id = scope.tenant_id
    group_ids = scope.group_ids
    visibility = options.visibility
    shared_group_ids = options.shared_group_ids
    is_admin = options.is_admin
    db_ds = check_datasource_access(
        db,
        uid,
        GrafanaUserScope(user_id=user_id, tenant_id=tenant_id, group_ids=group_ids),
        DatasourceAccessCriteria(require_write=True),
    )
    if not db_ds:
        return None

    existing = await service.grafana_service.get_datasource(uid)
    if existing and is_safe_system_datasource(existing):
        raise HTTPException(status_code=403, detail="Default/read-only datasources cannot be modified")

    datasource_update = cast(
        DatasourceUpdate,
        apply_scoped_datasource_defaults(
            db,
            DatasourceScopeDefaultsContext(
                datasource=datasource_update,
                user_id=user_id,
                tenant_id=tenant_id,
                existing_json=dict(getattr(existing, "json_data", None) or getattr(existing, "jsonData", None) or {}),
                existing_type=str(getattr(existing, "type", "") or ""),
            ),
            resolve_org_scope=_resolve_datasource_org_scope,
        ),
    )

    requested_name: str | None = None
    if getattr(datasource_update, "name", None) is not None:
        requested_name = str(datasource_update.name or "").strip()
        if requested_name and await _has_accessible_name_conflict(
            service,
            db,
            AccessibleDsNameConflictParams(
                tenant_id=tenant_id,
                user_id=user_id,
                group_ids=group_ids,
                name=requested_name,
                exclude_uid=uid,
            ),
        ):
            raise HTTPException(status_code=409, detail="Datasource name already exists in your visible scope")

    result = await persist_datasource_update(
        service,
        uid,
        datasource_update,
        requested_name=requested_name,
        user_id=user_id,
    )

    if not result:
        return None

    db_ds.name = requested_name or db_ds.name or result.name
    db_ds.type = result.type

    if visibility:
        db_ds.visibility = visibility
        if visibility == "group" and shared_group_ids is not None:
            groups = resolve_group_share_on_visibility_change(
                service,
                db,
                group_share_change_for_scope(
                    GrafanaUserScope(user_id, tenant_id, group_ids),
                    visibility=visibility,
                    shared_group_ids=shared_group_ids,
                    is_admin=is_admin,
                ),
            )
            db_ds.shared_groups.clear()
            db_ds.shared_groups.extend(groups)
        elif visibility != "group":
            db_ds.shared_groups.clear()

    commit_session(db)

    payload = enrich_datasource_payload(result.model_dump(), db_ds=db_ds, user_id=user_id)
    requested_json_data = dict(getattr(datasource_update, "json_data", None) or {})
    if requested_json_data and not payload.get("jsonData"):
        payload["jsonData"] = requested_json_data
    return Datasource.model_validate(payload)


async def delete_datasource(
    service: GrafanaProxyClient,
    db: Session,
    uid: str,
    scope: GrafanaUserScope,
) -> bool:
    user_id = scope.user_id
    tenant_id = scope.tenant_id
    group_ids = scope.group_ids
    db_ds = check_datasource_access(
        db,
        uid,
        GrafanaUserScope(user_id=user_id, tenant_id=tenant_id, group_ids=group_ids),
        DatasourceAccessCriteria(require_write=True),
    )
    if not db_ds:
        return False
    existing = await service.grafana_service.get_datasource(uid)
    if existing and is_safe_system_datasource(existing):
        raise HTTPException(status_code=403, detail="Default/read-only datasources cannot be deleted")
    ok = await service.grafana_service.delete_datasource(uid)
    if not ok:
        return False
    db.delete(db_ds)
    commit_session(db)
    return True


async def query_datasource(service: GrafanaProxyClient, payload: JSONDict) -> JSONDict:
    result = await service.grafana_service.query_datasource(payload)
    return result if isinstance(result, dict) else {}


def toggle_datasource_hidden(
    db: Session,
    uid: str,
    scope: GrafanaUserScope,
    params: HiddenToggleParams,
) -> bool:
    db_ds = _db_datasource_by_uid(db, scope.tenant_id, uid)
    if not db_ds:
        return False
    db_ds.hidden_by = update_hidden_members(db_ds.hidden_by, scope.user_id, params.hidden)
    commit_session(db)
    return True


def get_datasource_metadata(db: Session, tenant_id: str) -> dict[str, list[str]]:
    rows = (
        db.query(GrafanaDatasource)
        .filter(GrafanaDatasource.tenant_id == tenant_id)
        .limit(int(config.MAX_QUERY_LIMIT))
        .all()
    )
    team_ids = sorted({str(g.id) for ds in rows for g in (ds.shared_groups or [])})
    return {"team_ids": team_ids}
