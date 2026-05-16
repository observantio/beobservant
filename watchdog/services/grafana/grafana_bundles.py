"""
Typed parameter bundles for Grafana proxy/ops

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the
License. You may obtain a copy of the License at
http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from db_models import GrafanaDashboard
from models.grafana.grafana_dashboard_models import DashboardCreate, DashboardSearchResult, DashboardUpdate
from models.grafana.grafana_datasource_models import DatasourceCreate, DatasourceUpdate


@dataclass(frozen=True, slots=True)
class GrafanaUserScope:
    user_id: str
    tenant_id: str
    group_ids: list[str]


@dataclass(frozen=True, slots=True)
class DashboardSearchParams:
    query: str | None = None
    tag: str | None = None
    starred: bool | None = None
    folder_ids: list[int] | None = None
    folder_uids: list[str] | None = None
    dashboard_uids: list[str] | None = None
    uid: str | None = None
    team_id: str | None = None
    show_hidden: bool = False
    limit: int | None = None
    offset: int = 0
    search_context: object | None = None
    is_admin: bool = False
    exclude_foldered_dashboards: bool = False


@dataclass(slots=True)
class DashboardSearchAppendContext:
    db: Session
    tenant_id: str
    user_id: str
    gids: list[str]
    is_admin: bool
    folder_uid_set: set[str]
    folder_id_set: set[int]
    exclude_foldered_dashboards: bool
    accessible: set[str]
    allow_system: bool
    all_registered_uids: set[str]
    db_dashboards: dict[str, GrafanaDashboard]
    show_hidden: bool
    team_id_s: str | None
    out: list[DashboardSearchResult]
    folder_updates: list[GrafanaDashboard]


@dataclass(frozen=True, slots=True)
class GroupVisibilityValidation:
    user_id: str | None
    tenant_id: str
    group_ids: list[str] | None
    shared_group_ids: list[str] | None
    is_admin: bool


@dataclass(frozen=True, slots=True)
class VisibilityGroupResolveContext:
    user_id: str
    tenant_id: str
    visibility: str
    group_ids: list[str]
    shared_group_ids: list[str] | None
    is_admin: bool


@dataclass(frozen=True, slots=True)
class AccessibleTitleConflictParams:
    tenant_id: str
    user_id: str
    group_ids: list[str]
    title: str
    visibility: str | None = None
    shared_group_ids: list[str] | None = None
    exclude_uid: str | None = None


@dataclass(frozen=True, slots=True)
class DashboardCreateOptions:
    visibility: str = "private"
    shared_group_ids: list[str] | None = None
    is_admin: bool = False
    actor_permissions: list[str] | None = None


@dataclass(frozen=True, slots=True)
class DashboardUpdateOptions:
    visibility: str | None = None
    shared_group_ids: list[str] | None = None
    is_admin: bool = False
    actor_permissions: list[str] | None = None


@dataclass(frozen=True, slots=True)
class DashboardCreateRequest:
    dashboard_create: DashboardCreate
    scope: GrafanaUserScope
    options: DashboardCreateOptions


@dataclass(frozen=True, slots=True)
class DashboardUpdateRequest:
    uid: str
    dashboard_update: DashboardUpdate
    scope: GrafanaUserScope
    options: DashboardUpdateOptions


@dataclass(frozen=True, slots=True)
class DatasourceListParams:
    uid: str | None = None
    query: str | None = None
    team_id: str | None = None
    show_hidden: bool = False
    limit: int | None = None
    offset: int = 0
    datasource_context: object | None = None


@dataclass(frozen=True, slots=True)
class DatasourceCreateOptions:
    visibility: str = "private"
    shared_group_ids: list[str] | None = None
    is_admin: bool = False


@dataclass(frozen=True, slots=True)
class DatasourceUpdateOptions:
    visibility: str | None = None
    shared_group_ids: list[str] | None = None
    is_admin: bool = False


@dataclass(frozen=True, slots=True)
class DatasourceCreateRequest:
    datasource_create: DatasourceCreate
    scope: GrafanaUserScope
    options: DatasourceCreateOptions


@dataclass(frozen=True, slots=True)
class DatasourceUpdateRequest:
    uid: str
    datasource_update: DatasourceUpdate
    scope: GrafanaUserScope
    options: DatasourceUpdateOptions


@dataclass(frozen=True, slots=True)
class DatasourceAccessCriteria:
    require_write: bool = False


@dataclass(frozen=True, slots=True)
class DatasourceQueryEnforcement:
    path: str
    method: str
    body: object


@dataclass(frozen=True, slots=True)
class AccessibleDsNameConflictParams:
    tenant_id: str
    user_id: str
    group_ids: list[str]
    name: str
    exclude_uid: str | None = None


@dataclass(frozen=True, slots=True)
class FolderListParams:
    show_hidden: bool = False
    is_admin: bool = False


@dataclass(frozen=True, slots=True)
class FolderCreateOptions:
    visibility: str = "private"
    shared_group_ids: list[str] | None = None
    allow_dashboard_writes: bool = False
    is_admin: bool = False


@dataclass(frozen=True, slots=True)
class FolderUpdateOptions:
    title: str | None = None
    visibility: str | None = None
    shared_group_ids: list[str] | None = None
    allow_dashboard_writes: bool | None = None
    is_admin: bool = False


@dataclass(frozen=True, slots=True)
class FolderDeleteOptions:
    is_admin: bool = False


@dataclass(frozen=True, slots=True)
class FolderAccessCriteria:
    require_write: bool = False
    is_admin: bool = False
    include_hidden: bool = False


@dataclass(frozen=True, slots=True)
class FolderGetParams:
    is_admin: bool = False


@dataclass(frozen=True, slots=True)
class FolderGetRequest:
    uid: str
    scope: GrafanaUserScope
    params: FolderGetParams


@dataclass(frozen=True, slots=True)
class FolderCreateRequest:
    title: str
    scope: GrafanaUserScope
    options: FolderCreateOptions


@dataclass(frozen=True, slots=True)
class FolderDeleteRequest:
    uid: str
    scope: GrafanaUserScope
    options: FolderDeleteOptions


@dataclass(frozen=True, slots=True)
class FolderUpdateRequest:
    uid: str
    scope: GrafanaUserScope
    options: FolderUpdateOptions


@dataclass(frozen=True, slots=True)
class FolderAccessRequest:
    uid: str
    scope: GrafanaUserScope
    criteria: FolderAccessCriteria


@dataclass(frozen=True, slots=True)
class FolderAccessibilityRequest:
    uid: str | None
    scope: GrafanaUserScope
    criteria: FolderAccessCriteria


@dataclass(frozen=True, slots=True)
class HiddenToggleParams:
    hidden: bool


@dataclass(frozen=True, slots=True)
class HiddenToggleRequest:
    uid: str
    scope: GrafanaUserScope
    params: HiddenToggleParams


@dataclass(frozen=True, slots=True)
class DashboardAccessCriteria:
    require_write: bool = False


@dataclass(frozen=True, slots=True)
class GroupVisibilityShareChange:
    visibility: str
    shared_group_ids: list[str] | None
    user_id: str
    tenant_id: str
    group_ids: list[str]
    is_admin: bool
