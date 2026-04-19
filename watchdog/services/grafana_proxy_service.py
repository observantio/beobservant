"""
Grafana Proxy Service for forwarding requests to Grafana API with authentication, error handling, and audit logging.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the
License. You may obtain a copy of the License at
http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, TYPE_CHECKING

from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from db_models import GrafanaDashboard, GrafanaDatasource, GrafanaFolder, Group, User, user_groups
from models.access.auth_models import TokenData
from models.grafana.grafana_dashboard_models import DashboardSearchResult
from models.grafana.grafana_datasource_models import Datasource
from models.grafana.grafana_folder_models import Folder
from custom_types.json import JSONDict
from services.grafana import proxy_auth_ops as _proxy_auth_ops
from services.grafana.dashboard_helpers import DashboardSearchContext, build_dashboard_search_context
from services.grafana.grafana_bundles import (
    DashboardCreateRequest,
    DashboardSearchParams,
    DashboardUpdateRequest,
    DatasourceCreateRequest,
    DatasourceListParams,
    DatasourceQueryEnforcement,
    DatasourceUpdateRequest,
    FolderAccessibilityRequest,
    FolderAccessRequest,
    FolderCreateRequest,
    FolderDeleteRequest,
    FolderGetRequest,
    FolderListParams,
    FolderUpdateRequest,
    GrafanaUserScope,
    GroupVisibilityValidation,
    HiddenToggleRequest,
)
from services.grafana.grafana_service import GrafanaService
from services.grafana.dashboard_ops import (
    create_dashboard,
    delete_dashboard,
    get_dashboard,
    get_dashboard_metadata,
    search_dashboards,
    toggle_dashboard_hidden,
    update_dashboard,
)
from services.grafana.datasource_ops import (
    DatasourceListContext,
    build_datasource_list_context,
    create_datasource,
    delete_datasource,
    enforce_datasource_query_access,
    get_datasource,
    get_datasource_by_name,
    get_datasource_metadata,
    get_datasources,
    query_datasource,
    toggle_datasource_hidden,
    update_datasource,
)
from services.grafana.folder_ops import (
    check_folder_access,
    create_folder,
    delete_folder,
    get_folder,
    get_folders,
    is_folder_accessible,
    toggle_folder_hidden,
    update_folder,
)

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from services.database_auth_service import DatabaseAuthService

is_admin_user = _proxy_auth_ops.is_admin_user
is_resource_accessible = _proxy_auth_ops.is_resource_accessible
extract_dashboard_uid = _proxy_auth_ops.extract_dashboard_uid
extract_datasource_uid = _proxy_auth_ops.extract_datasource_uid
extract_datasource_id = _proxy_auth_ops.extract_datasource_id
extract_proxy_token = _proxy_auth_ops.extract_proxy_token
authorize_proxy_request = _proxy_auth_ops.authorize_proxy_request
clear_proxy_auth_cache = getattr(_proxy_auth_ops, "clear_proxy_auth_cache", lambda: None)


@dataclass(frozen=True, slots=True)
class ProxyAuthorizationRequest:
    request: Request
    auth_service: DatabaseAuthService
    token: Optional[str] = None
    orig: Optional[str] = None


class _GrafanaProxyCore:
    def __init__(self) -> None:
        self.logger = logger
        self.grafana_service = GrafanaService()

    @staticmethod
    def _normalize_group_ids(group_ids: Optional[List[str]]) -> List[str]:
        out: List[str] = []
        seen = set()
        for gid in group_ids or []:
            val = str(gid or "").strip()
            if not val or val in seen:
                continue
            seen.add(val)
            out.append(val)
        return out

    def _effective_group_ids(
        self,
        db: Session,
        *,
        user_id: str,
        tenant_id: str,
        group_ids: Optional[List[str]] = None,
    ) -> List[str]:
        fallback = self._normalize_group_ids(group_ids)
        user_exists = (
            db.query(User.id)
            .filter(
                User.id == str(user_id),
                User.tenant_id == str(tenant_id),
            )
            .first()
        )
        if not user_exists:
            return fallback
        live_rows = (
            db.query(user_groups.c.group_id)
            .join(Group, Group.id == user_groups.c.group_id)
            .filter(
                user_groups.c.user_id == str(user_id),
                Group.tenant_id == str(tenant_id),
            )
            .all()
        )
        return self._normalize_group_ids([gid for (gid,) in live_rows])

    @staticmethod
    def raise_http_from_grafana_error(exc: Exception) -> None:
        status = getattr(exc, "status", None)
        body = getattr(exc, "body", None)
        if status is None and body is None:
            raise exc

        message = (
            (isinstance(body, dict) and (body.get("message") or body.get("error") or body.get("detail")))
            or (isinstance(body, str) and body)
            or "Grafana API error"
        )
        normalized_status = int(status) if isinstance(status, int) else 500
        raise HTTPException(status_code=normalized_status if 400 <= normalized_status < 600 else 500, detail=message)

    def validate_group_visibility(self, db: Session, validation: GroupVisibilityValidation) -> List[Group]:
        if not validation.shared_group_ids:
            raise HTTPException(status_code=400, detail="No groups provided for group visibility")
        groups = (
            db.query(Group)
            .filter(Group.id.in_(validation.shared_group_ids), Group.tenant_id == validation.tenant_id)
            .all()
        )
        if len(groups) != len(validation.shared_group_ids):
            raise HTTPException(status_code=400, detail="One or more group ids are invalid")
        if not validation.is_admin:
            effective_groups = (
                self._effective_group_ids(
                    db,
                    user_id=str(validation.user_id),
                    tenant_id=str(validation.tenant_id),
                    group_ids=validation.group_ids,
                )
                if validation.user_id
                else self._normalize_group_ids(validation.group_ids)
            )
            user_group_set = set(effective_groups)
            not_member = [gid for gid in validation.shared_group_ids if gid not in user_group_set]
            if not_member:
                raise HTTPException(status_code=403, detail="User is not a member of one or more specified groups")
        return groups

    def _is_admin_user(self, token_data: TokenData) -> bool:
        return is_admin_user(token_data)

    def _is_resource_accessible(self, resource: object, token_data: TokenData) -> bool:
        if isinstance(resource, (GrafanaDashboard, GrafanaDatasource, GrafanaFolder)):
            return is_resource_accessible(resource, token_data)
        return False

    def _extract_dashboard_uid(self, path: str) -> Optional[str]:
        return extract_dashboard_uid(path)

    def _extract_datasource_uid(self, path: str) -> Optional[str]:
        return extract_datasource_uid(path)

    def _extract_datasource_id(self, path: str) -> Optional[int]:
        return extract_datasource_id(path)

    def _extract_proxy_token(self, request: Request, token: Optional[str] = None) -> Optional[str]:
        return extract_proxy_token(request, token)

    async def authorize_proxy_request(
        self,
        auth_request: ProxyAuthorizationRequest,
    ) -> Dict[str, str]:
        return await authorize_proxy_request(
            self,
            auth_request.request,
            auth_request.auth_service,
            token=auth_request.token,
            orig=auth_request.orig,
        )

    def clear_proxy_auth_cache(self) -> None:
        clear_proxy_auth_cache()

    def build_dashboard_search_context(
        self,
        db: Session,
        *,
        tenant_id: str,
        uid: Optional[str] = None,
    ) -> DashboardSearchContext:
        return build_dashboard_search_context(db, tenant_id=tenant_id, uid=uid)

    def build_datasource_list_context(
        self,
        db: Session,
        *,
        tenant_id: str,
        uid: Optional[str] = None,
    ) -> DatasourceListContext:
        return build_datasource_list_context(self, db, tenant_id=tenant_id, uid=uid)


class _GrafanaProxyDashboardMixin(_GrafanaProxyCore):
    async def search_dashboards(
        self,
        db: Session,
        subject: GrafanaUserScope,
        params: DashboardSearchParams,
    ) -> List[DashboardSearchResult]:
        effective_group_ids = self._effective_group_ids(
            db,
            user_id=subject.user_id,
            tenant_id=subject.tenant_id,
            group_ids=subject.group_ids,
        )
        scoped = GrafanaUserScope(subject.user_id, subject.tenant_id, effective_group_ids)
        return await search_dashboards(self, db, scoped, params)

    async def get_dashboard(
        self,
        db: Session,
        uid: str,
        subject: GrafanaUserScope,
        *,
        is_admin: bool = False,
    ) -> Optional[JSONDict]:
        effective_group_ids = self._effective_group_ids(
            db,
            user_id=subject.user_id,
            tenant_id=subject.tenant_id,
            group_ids=subject.group_ids,
        )
        scope = GrafanaUserScope(subject.user_id, subject.tenant_id, effective_group_ids)
        return await get_dashboard(self, db, uid, scope, is_admin=is_admin)

    async def create_dashboard(
        self,
        db: Session,
        request: DashboardCreateRequest,
    ) -> Optional[JSONDict]:
        effective_group_ids = self._effective_group_ids(
            db,
            user_id=request.scope.user_id,
            tenant_id=request.scope.tenant_id,
            group_ids=request.scope.group_ids,
        )
        scope = GrafanaUserScope(request.scope.user_id, request.scope.tenant_id, effective_group_ids)
        return await create_dashboard(
            self,
            db,
            request.dashboard_create,
            scope=scope,
            options=request.options,
        )

    async def update_dashboard(
        self,
        db: Session,
        request: DashboardUpdateRequest,
    ) -> Optional[JSONDict]:
        effective_group_ids = self._effective_group_ids(
            db,
            user_id=request.scope.user_id,
            tenant_id=request.scope.tenant_id,
            group_ids=request.scope.group_ids,
        )
        scope = GrafanaUserScope(request.scope.user_id, request.scope.tenant_id, effective_group_ids)
        return await update_dashboard(
            self,
            db,
            DashboardUpdateRequest(
                uid=request.uid,
                dashboard_update=request.dashboard_update,
                scope=scope,
                options=request.options,
            ),
        )

    async def delete_dashboard(
        self,
        db: Session,
        uid: str,
        subject: GrafanaUserScope,
    ) -> bool:
        effective_group_ids = self._effective_group_ids(
            db,
            user_id=subject.user_id,
            tenant_id=subject.tenant_id,
            group_ids=subject.group_ids,
        )
        scope = GrafanaUserScope(subject.user_id, subject.tenant_id, effective_group_ids)
        return await delete_dashboard(self, db, uid, scope)

    def toggle_dashboard_hidden(
        self,
        db: Session,
        request: HiddenToggleRequest,
    ) -> bool:
        return toggle_dashboard_hidden(db, request.uid, request.scope, request.params)

    def get_dashboard_metadata(self, db: Session, tenant_id: str) -> JSONDict:
        metadata = get_dashboard_metadata(db, tenant_id)
        return {str(key): value for key, value in metadata.items()}


class _GrafanaProxyDatasourceMixin(_GrafanaProxyCore):
    async def get_datasources(
        self,
        db: Session,
        scope: GrafanaUserScope,
        params: DatasourceListParams,
    ) -> List[Datasource]:
        effective_group_ids = self._effective_group_ids(
            db,
            user_id=scope.user_id,
            tenant_id=scope.tenant_id,
            group_ids=scope.group_ids,
        )
        scoped = GrafanaUserScope(scope.user_id, scope.tenant_id, effective_group_ids)
        return await get_datasources(self, db, scoped, params)

    async def get_datasource(self, db: Session, uid: str, scope: GrafanaUserScope) -> Optional[Datasource]:
        effective_group_ids = self._effective_group_ids(
            db,
            user_id=scope.user_id,
            tenant_id=scope.tenant_id,
            group_ids=scope.group_ids,
        )
        scoped = GrafanaUserScope(scope.user_id, scope.tenant_id, effective_group_ids)
        return await get_datasource(self, db, uid, scoped)

    async def get_datasource_by_name(
        self, db: Session, name: str, scope: GrafanaUserScope
    ) -> Optional[Datasource]:
        effective_group_ids = self._effective_group_ids(
            db,
            user_id=scope.user_id,
            tenant_id=scope.tenant_id,
            group_ids=scope.group_ids,
        )
        scoped = GrafanaUserScope(scope.user_id, scope.tenant_id, effective_group_ids)
        return await get_datasource_by_name(self, db, name, scoped)

    async def create_datasource(
        self,
        db: Session,
        request: DatasourceCreateRequest,
    ) -> Optional[Datasource]:
        effective_group_ids = self._effective_group_ids(
            db,
            user_id=request.scope.user_id,
            tenant_id=request.scope.tenant_id,
            group_ids=request.scope.group_ids,
        )
        scoped = GrafanaUserScope(request.scope.user_id, request.scope.tenant_id, effective_group_ids)
        return await create_datasource(
            self,
            db,
            request.datasource_create,
            scope=scoped,
            options=request.options,
        )

    async def update_datasource(
        self,
        db: Session,
        request: DatasourceUpdateRequest,
    ) -> Optional[Datasource]:
        effective_group_ids = self._effective_group_ids(
            db,
            user_id=request.scope.user_id,
            tenant_id=request.scope.tenant_id,
            group_ids=request.scope.group_ids,
        )
        scoped = GrafanaUserScope(request.scope.user_id, request.scope.tenant_id, effective_group_ids)
        return await update_datasource(
            self,
            db,
            DatasourceUpdateRequest(
                uid=request.uid,
                datasource_update=request.datasource_update,
                scope=scoped,
                options=request.options,
            ),
        )

    async def delete_datasource(self, db: Session, uid: str, scope: GrafanaUserScope) -> bool:
        effective_group_ids = self._effective_group_ids(
            db,
            user_id=scope.user_id,
            tenant_id=scope.tenant_id,
            group_ids=scope.group_ids,
        )
        scoped = GrafanaUserScope(scope.user_id, scope.tenant_id, effective_group_ids)
        return await delete_datasource(self, db, uid, scoped)

    def toggle_datasource_hidden(
        self,
        db: Session,
        request: HiddenToggleRequest,
    ) -> bool:
        return toggle_datasource_hidden(db, request.uid, request.scope, request.params)

    def get_datasource_metadata(self, db: Session, tenant_id: str) -> JSONDict:
        metadata = get_datasource_metadata(db, tenant_id)
        return {str(key): value for key, value in metadata.items()}

    async def query_datasource(self, payload: JSONDict) -> JSONDict:
        return await query_datasource(self, payload)

    async def enforce_datasource_query_access(
        self,
        db: Session,
        scope: GrafanaUserScope,
        enforcement: DatasourceQueryEnforcement,
    ) -> None:
        effective_group_ids = self._effective_group_ids(
            db,
            user_id=scope.user_id,
            tenant_id=scope.tenant_id,
            group_ids=scope.group_ids,
        )
        scoped = GrafanaUserScope(scope.user_id, scope.tenant_id, effective_group_ids)
        await enforce_datasource_query_access(self, db, scoped, enforcement)


class _GrafanaProxyFolderMixin(_GrafanaProxyCore):
    async def get_folders(
        self,
        db: Session,
        scope: GrafanaUserScope,
        params: FolderListParams,
    ) -> List[Folder]:
        effective_group_ids = self._effective_group_ids(
            db,
            user_id=scope.user_id,
            tenant_id=scope.tenant_id,
            group_ids=scope.group_ids,
        )
        scoped = GrafanaUserScope(scope.user_id, scope.tenant_id, effective_group_ids)
        return await get_folders(self, db, scoped, params)

    async def get_folder(
        self,
        db: Session,
        request: FolderGetRequest,
    ) -> Optional[Folder]:
        effective_group_ids = self._effective_group_ids(
            db,
            user_id=request.scope.user_id,
            tenant_id=request.scope.tenant_id,
            group_ids=request.scope.group_ids,
        )
        scoped = GrafanaUserScope(
            request.scope.user_id,
            request.scope.tenant_id,
            effective_group_ids,
        )
        return await get_folder(
            self,
            db,
            FolderGetRequest(uid=request.uid, scope=scoped, params=request.params),
        )

    async def create_folder(
        self,
        db: Session,
        request: FolderCreateRequest,
    ) -> Optional[Folder]:
        effective_group_ids = self._effective_group_ids(
            db,
            user_id=request.scope.user_id,
            tenant_id=request.scope.tenant_id,
            group_ids=request.scope.group_ids,
        )
        scoped = GrafanaUserScope(
            request.scope.user_id,
            request.scope.tenant_id,
            effective_group_ids,
        )
        return await create_folder(
            self,
            db,
            FolderCreateRequest(title=request.title, scope=scoped, options=request.options),
        )

    async def delete_folder(
        self,
        db: Session,
        request: FolderDeleteRequest,
    ) -> bool:
        effective_group_ids = self._effective_group_ids(
            db,
            user_id=request.scope.user_id,
            tenant_id=request.scope.tenant_id,
            group_ids=request.scope.group_ids,
        )
        scoped = GrafanaUserScope(
            request.scope.user_id,
            request.scope.tenant_id,
            effective_group_ids,
        )
        return await delete_folder(
            self,
            db,
            FolderDeleteRequest(uid=request.uid, scope=scoped, options=request.options),
        )

    async def update_folder(
        self,
        db: Session,
        request: FolderUpdateRequest,
    ) -> Optional[Folder]:
        effective_group_ids = self._effective_group_ids(
            db,
            user_id=request.scope.user_id,
            tenant_id=request.scope.tenant_id,
            group_ids=request.scope.group_ids,
        )
        scoped = GrafanaUserScope(
            request.scope.user_id,
            request.scope.tenant_id,
            effective_group_ids,
        )
        return await update_folder(
            self,
            db,
            FolderUpdateRequest(uid=request.uid, scope=scoped, options=request.options),
        )

    def check_folder_access(
        self,
        db: Session,
        request: FolderAccessRequest,
    ) -> Optional[GrafanaFolder]:
        effective_group_ids = self._effective_group_ids(
            db,
            user_id=request.scope.user_id,
            tenant_id=request.scope.tenant_id,
            group_ids=request.scope.group_ids,
        )
        scoped = GrafanaUserScope(request.scope.user_id, request.scope.tenant_id, effective_group_ids)
        return check_folder_access(db, request.uid, scoped, request.criteria)

    def is_folder_accessible(
        self,
        db: Session,
        request: FolderAccessibilityRequest,
    ) -> bool:
        effective_group_ids = self._effective_group_ids(
            db,
            user_id=request.scope.user_id,
            tenant_id=request.scope.tenant_id,
            group_ids=request.scope.group_ids,
        )
        scoped = GrafanaUserScope(request.scope.user_id, request.scope.tenant_id, effective_group_ids)
        return is_folder_accessible(db, request.uid, scoped, request.criteria)

    def toggle_folder_hidden(
        self,
        db: Session,
        request: HiddenToggleRequest,
    ) -> bool:
        return toggle_folder_hidden(db, request.uid, request.scope, request.params)


class GrafanaProxyService(
    _GrafanaProxyDashboardMixin,
    _GrafanaProxyDatasourceMixin,
    _GrafanaProxyFolderMixin,
):
    """Composed Grafana proxy: dashboards, datasources, and folders."""
