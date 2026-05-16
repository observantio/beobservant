"""
Grafana datasource workflow helpers.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the
License. You may obtain a copy of the License at
http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from custom_types.json import JSONDict
from db_models import GrafanaDatasource, Group
from models.grafana.grafana_datasource_models import Datasource, DatasourceCreate, DatasourceUpdate
from services.grafana.datasource_payloads import (
    build_internal_datasource_name,
    is_safe_system_datasource,
    merge_json_payload,
)
from services.grafana.grafana_bundles import DatasourceAccessCriteria, GrafanaUserScope
from services.grafana.grafana_service import GrafanaAPIError
from services.grafana.proxy_client import GrafanaProxyClient
from services.grafana.visibility import resolve_visibility_groups_for_scope, visibility_group_resolve_context
from sqlalchemy.orm import Session


@dataclass(frozen=True, slots=True)
class DatasourceLookupContext:
    uid: str
    scope: GrafanaUserScope
    datasource: object
    db_ds: GrafanaDatasource | None
    show_hidden: bool


@dataclass(frozen=True, slots=True)
class DatasourceVisibilityContext:
    scope: GrafanaUserScope
    visibility: str
    shared_group_ids: list[str] | None
    is_admin: bool


@dataclass(frozen=True, slots=True)
class DatasourceScopeDefaultsContext:
    datasource: DatasourceCreate | DatasourceUpdate
    user_id: str
    tenant_id: str
    existing_json: JSONDict | None = None
    existing_type: str | None = None


def validate_datasource_lookup(
    db: Session,
    ctx: DatasourceLookupContext,
    *,
    access_check: Callable[..., GrafanaDatasource | None],
) -> bool:
    if ctx.db_ds:
        has_access = access_check(db, ctx.uid, ctx.scope, DatasourceAccessCriteria()) is not None
        if not has_access:
            return False
        return ctx.show_hidden or ctx.scope.user_id not in (ctx.db_ds.hidden_by or [])
    return is_safe_system_datasource(ctx.datasource)


def matches_datasource_query(
    datasource: object,
    *,
    db_ds: GrafanaDatasource | None,
    uid: str,
    query_lc: str,
) -> bool:
    if not query_lc:
        return True
    name_value = str((db_ds.name if db_ds and db_ds.name else getattr(datasource, "name", "")) or "").lower()
    return any(
        query_lc in candidate
        for candidate in (
            name_value,
            str(getattr(datasource, "type", "") or "").lower(),
            str(getattr(datasource, "url", "") or "").lower(),
            uid.lower(),
        )
    )


def matches_datasource_team_filter(*, db_ds: GrafanaDatasource | None, team_id: object) -> bool:
    if team_id is None:
        return True
    if not db_ds:
        return False
    return str(team_id) in {str(group.id) for group in (db_ds.shared_groups or [])}


def resolve_visibility_groups(
    service: GrafanaProxyClient,
    db: Session,
    ctx: DatasourceVisibilityContext,
) -> list[Group]:
    return resolve_visibility_groups_for_scope(
        service,
        db,
        visibility_group_resolve_context(
            ctx.scope,
            visibility=ctx.visibility,
            shared_group_ids=ctx.shared_group_ids,
            is_admin=ctx.is_admin,
        ),
    )


def apply_scoped_datasource_defaults(
    db: Session,
    ctx: DatasourceScopeDefaultsContext,
    *,
    resolve_org_scope: Callable[..., str],
) -> DatasourceCreate | DatasourceUpdate:
    datasource = ctx.datasource
    datasource_type = str(getattr(datasource, "type", "") or ctx.existing_type or "")
    if datasource_type not in {"prometheus", "loki", "tempo"}:
        return datasource

    requested_org_id = getattr(datasource, "org_id", None)
    incoming_json = dict(getattr(datasource, "json_data", None) or {})
    merged_json = merge_json_payload(ctx.existing_json, incoming_json)
    scoped_org_candidate = requested_org_id or merged_json.get("watchdogScopeKey") or None
    org_id = resolve_org_scope(
        db,
        requested_org_id=scoped_org_candidate,
        user_id=ctx.user_id,
        tenant_id=ctx.tenant_id,
    )
    secure_json_data = dict(getattr(datasource, "secure_json_data", None) or {})
    merged_json.setdefault("httpHeaderName1", "X-Scope-OrgID")
    merged_json["watchdogScopeKey"] = org_id
    if "watchdogApiKeyName" in merged_json:
        merged_json["watchdogApiKeyName"] = str(merged_json.get("watchdogApiKeyName") or "").strip()
    secure_json_data["httpHeaderValue1"] = org_id
    return datasource.model_copy(
        update={"org_id": org_id, "json_data": merged_json, "secure_json_data": secure_json_data}
    )


async def persist_datasource_create(
    service: GrafanaProxyClient,
    datasource_create: DatasourceCreate,
    *,
    requested_name: str,
    user_id: str,
) -> Datasource | None:
    try:
        return await service.grafana_service.create_datasource(datasource_create)
    except GrafanaAPIError as exc:
        if exc.status not in {409, 412}:
            service.raise_http_from_grafana_error(exc)
            return None
        internal_name = build_internal_datasource_name(requested_name or datasource_create.name, user_id)
        try:
            return await service.grafana_service.create_datasource(
                datasource_create.model_copy(update={"name": internal_name})
            )
        except GrafanaAPIError as retry_exc:
            service.raise_http_from_grafana_error(retry_exc)
            return None


async def persist_datasource_update(
    service: GrafanaProxyClient,
    uid: str,
    datasource_update: DatasourceUpdate,
    *,
    requested_name: str | None,
    user_id: str,
) -> Datasource | None:
    try:
        return await service.grafana_service.update_datasource(uid, datasource_update)
    except GrafanaAPIError as exc:
        if exc.status not in {409, 412} or not requested_name:
            service.raise_http_from_grafana_error(exc)
            return None
        internal_name = build_internal_datasource_name(requested_name, user_id)
        try:
            return await service.grafana_service.update_datasource(
                uid,
                datasource_update.model_copy(update={"name": internal_name}),
            )
        except GrafanaAPIError as retry_exc:
            service.raise_http_from_grafana_error(retry_exc)
            return None
