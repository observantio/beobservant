"""Grafana proxy service with multi-tenancy, team scoping, and access control."""
import logging
import re
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_, and_

from services.grafana_service import GrafanaService, GrafanaAPIError
from fastapi import HTTPException
from db_models import GrafanaDashboard, GrafanaDatasource, Group
from models.access.auth_models import Permission, TokenData, Role
from models.grafana.grafana_dashboard_models import DashboardCreate, DashboardUpdate, DashboardSearchResult
from models.grafana.grafana_datasource_models import Datasource, DatasourceCreate, DatasourceUpdate
from config import config

logger = logging.getLogger(__name__)


class GrafanaProxyService:
    """Proxy service for Grafana with multi-tenant access control, team scoping,
    hide/show, and UID search."""

    def __init__(self):
        self.grafana_service = GrafanaService()

    @staticmethod
    def _raise_http_from_grafana_error(gae: GrafanaAPIError) -> None:
        body = gae.body
        message = None
        if isinstance(body, dict):
            message = body.get("message") or body.get("error") or body.get("detail")
        message = message or (body if isinstance(body, str) else None) or "Grafana API error"
        raise HTTPException(status_code=gae.status if 400 <= gae.status < 600 else 500, detail=message)

    def _validate_group_visibility(
        self,
        db: Session,
        *,
        tenant_id: str,
        group_ids: List[str] | None,
        shared_group_ids: List[str] | None,
        is_admin: bool,
    ) -> List[Group]:
        if not shared_group_ids:
            raise HTTPException(status_code=400, detail="No groups provided for group visibility")

        groups = db.query(Group).filter(Group.id.in_(shared_group_ids), Group.tenant_id == tenant_id).all()
        found_ids = {group.id for group in groups}
        missing = set(shared_group_ids) - found_ids
        if missing:
            raise HTTPException(status_code=400, detail=f"Invalid group ids: {list(missing)}")

        if not is_admin:
            user_groups = set(group_ids or [])
            not_member = [gid for gid in shared_group_ids if gid not in user_groups]
            if not_member:
                raise HTTPException(status_code=403, detail=f"User not member of groups: {not_member}")

        return groups

    def _is_admin_user(self, token_data: TokenData) -> bool:
        return token_data.role == Role.ADMIN or token_data.is_superuser

    def _is_resource_accessible(self, resource, token_data: TokenData) -> bool:
        if not resource:
            return False

        if resource.tenant_id != token_data.tenant_id:
            return False

        hidden_by = getattr(resource, "hidden_by", None) or []
        if token_data.user_id in hidden_by:
            return False

        if self._is_admin_user(token_data):
            return True

        if resource.created_by == token_data.user_id:
            return True

        visibility = getattr(resource, "visibility", "private") or "private"
        if visibility == "tenant":
            return True

        if visibility == "group":
            user_group_ids = set(token_data.group_ids or [])
            resource_group_ids = {group.id for group in (resource.shared_groups or [])}
            return bool(user_group_ids.intersection(resource_group_ids))

        return False

    def _extract_dashboard_uid(self, path: str) -> Optional[str]:
        patterns = [
            r"^/grafana/d/([^/]+)",
            r"^/grafana/d-solo/([^/]+)",
            r"^/grafana/api/dashboards/uid/([^/?]+)",
        ]
        for pattern in patterns:
            match = re.match(pattern, path)
            if match:
                return match.group(1)
        return None

    def _extract_datasource_uid(self, path: str) -> Optional[str]:
        patterns = [
            r"^/grafana/api/datasources/uid/([^/?]+)",
            r"^/grafana/api/datasources/proxy/uid/([^/?]+)",
            r"^/grafana/connections/datasources/edit/([^/?]+)",
        ]
        for pattern in patterns:
            match = re.match(pattern, path)
            if match:
                return match.group(1)
        return None

    def _extract_datasource_id(self, path: str) -> Optional[int]:
        patterns = [
            r"^/grafana/api/datasources/proxy/(\d+)(?:/|$)",
        ]
        for pattern in patterns:
            match = re.match(pattern, path)
            if match:
                try:
                    return int(match.group(1))
                except ValueError:
                    return None
        return None

    def _extract_proxy_token(self, request, token: Optional[str] = None) -> Optional[str]:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            return auth_header.split(" ", 1)[1]

        cookie_token = request.cookies.get("beobservant_token")
        if cookie_token:
            return cookie_token

        access_token = request.cookies.get("access_token")
        if access_token:
            return access_token

        return request.headers.get("X-Auth-Token") or token

    def authorize_proxy_request(
        self,
        request,
        db: Session,
        auth_service,
        token: Optional[str] = None,
        orig: Optional[str] = None,
    ) -> Dict[str, str]:
        token_to_verify = self._extract_proxy_token(request, token)
        if not token_to_verify:
            raise HTTPException(status_code=401, detail="Authentication required")

        token_data = auth_service.decode_token(token_to_verify)
        if not token_data:
            raise HTTPException(status_code=401, detail="Invalid authentication token")

        if isinstance(token_data, dict):
            token_data = TokenData(**token_data)

        user_permissions = set(token_data.permissions or [])
        allowed_grafana_perms = {
            Permission.READ_DASHBOARDS.value,
            Permission.CREATE_DASHBOARDS.value,
            Permission.UPDATE_DASHBOARDS.value,
            Permission.DELETE_DASHBOARDS.value,
            Permission.READ_DATASOURCES.value,
            Permission.QUERY_DATASOURCES.value,
            Permission.READ_FOLDERS.value,
            Permission.CREATE_FOLDERS.value,
            Permission.DELETE_FOLDERS.value,
            Permission.WRITE_DASHBOARDS.value,
        }
        if not user_permissions.intersection(allowed_grafana_perms) and not token_data.is_superuser:
            raise HTTPException(status_code=403, detail="Insufficient permissions")

        is_admin = self._is_admin_user(token_data)
        original_uri = orig or request.headers.get("X-Original-URI", "")
        original_path = original_uri.split("?", 1)[0] if original_uri else ""

        if not is_admin:
            dashboard_uid = self._extract_dashboard_uid(original_path)
            if dashboard_uid:
                dashboard = db.query(GrafanaDashboard).options(joinedload(GrafanaDashboard.shared_groups)).filter(
                    GrafanaDashboard.grafana_uid == dashboard_uid
                ).first()
                if dashboard and not self._is_resource_accessible(dashboard, token_data):
                    raise HTTPException(status_code=403, detail="Dashboard access denied")

            datasource_uid = self._extract_datasource_uid(original_path)
            if datasource_uid:
                datasource = db.query(GrafanaDatasource).options(joinedload(GrafanaDatasource.shared_groups)).filter(
                    GrafanaDatasource.grafana_uid == datasource_uid
                ).first()
                if datasource and not self._is_resource_accessible(datasource, token_data):
                    raise HTTPException(status_code=403, detail="Datasource access denied")

            datasource_id = self._extract_datasource_id(original_path)
            if datasource_id is not None:
                datasource = db.query(GrafanaDatasource).options(joinedload(GrafanaDatasource.shared_groups)).filter(
                    GrafanaDatasource.grafana_id == datasource_id
                ).first()
                if datasource and not self._is_resource_accessible(datasource, token_data):
                    raise HTTPException(status_code=403, detail="Datasource access denied")

        grafana_role = "Viewer"
        if is_admin:
            grafana_role = "Admin"
        elif user_permissions.intersection({
            Permission.CREATE_DASHBOARDS.value,
            Permission.UPDATE_DASHBOARDS.value,
            Permission.DELETE_DASHBOARDS.value,
            Permission.CREATE_DATASOURCES.value,
            Permission.UPDATE_DATASOURCES.value,
            Permission.DELETE_DATASOURCES.value,
            Permission.CREATE_FOLDERS.value,
            Permission.DELETE_FOLDERS.value,
            Permission.WRITE_DASHBOARDS.value,
        }):
            grafana_role = "Editor"

        return {
            "X-WEBAUTH-USER": token_data.username,
            "X-WEBAUTH-TENANT": token_data.tenant_id,
            "X-WEBAUTH-ROLE": grafana_role,
        }

    # ------------------------------------------------------------------
    # Access check helpers
    # ------------------------------------------------------------------

    def _check_dashboard_access(
        self,
        db: Session,
        dashboard_uid: str,
        user_id: str,
        tenant_id: str,
        group_ids: List[str],
        require_write: bool = False
    ) -> Optional[GrafanaDashboard]:
        """Check if user has access to a dashboard."""
        dashboard = db.query(GrafanaDashboard).filter(
            GrafanaDashboard.grafana_uid == dashboard_uid,
            GrafanaDashboard.tenant_id == tenant_id
        ).first()

        if not dashboard:
            return None

        # Owner always has full access
        if dashboard.created_by == user_id:
            return dashboard

        # Non-owners cannot write
        if require_write:
            return None

        # Tenant-wide visibility
        if dashboard.visibility == "tenant":
            return dashboard
        elif dashboard.visibility == "group":
            shared_group_ids = [g.id for g in dashboard.shared_groups]
            if any(gid in shared_group_ids for gid in group_ids):
                return dashboard

        return None

    def _check_datasource_access(
        self,
        db: Session,
        datasource_uid: str,
        user_id: str,
        tenant_id: str,
        group_ids: List[str],
        require_write: bool = False
    ) -> Optional[GrafanaDatasource]:
        """Check if user has access to a datasource."""
        datasource = db.query(GrafanaDatasource).filter(
            GrafanaDatasource.grafana_uid == datasource_uid,
            GrafanaDatasource.tenant_id == tenant_id
        ).first()

        if not datasource:
            return None

        if datasource.created_by == user_id:
            return datasource

        if require_write:
            return None

        if datasource.visibility == "tenant":
            return datasource
        elif datasource.visibility == "group":
            shared_group_ids = [g.id for g in datasource.shared_groups]
            if any(gid in shared_group_ids for gid in group_ids):
                return datasource

        return None

    def _check_datasource_access_by_id(
        self,
        db: Session,
        datasource_id: int,
        user_id: str,
        tenant_id: str,
        group_ids: List[str],
        require_write: bool = False,
    ) -> Optional[GrafanaDatasource]:
        datasource = db.query(GrafanaDatasource).filter(
            GrafanaDatasource.grafana_id == datasource_id,
            GrafanaDatasource.tenant_id == tenant_id,
        ).first()

        if not datasource:
            return None

        if datasource.created_by == user_id:
            return datasource

        if require_write:
            return None

        if datasource.visibility == "tenant":
            return datasource
        if datasource.visibility == "group":
            shared_group_ids = [group.id for group in datasource.shared_groups]
            if any(group_id in shared_group_ids for group_id in group_ids):
                return datasource

        return None

    def enforce_datasource_query_access(
        self,
        db: Session,
        payload: Dict[str, Any],
        user_id: str,
        tenant_id: str,
        group_ids: List[str],
        is_admin: bool = False,
    ) -> None:
        if is_admin:
            return

        datasource_uids: set[str] = set()
        datasource_ids: set[int] = set()

        def collect(node: Any) -> None:
            if isinstance(node, dict):
                datasource = node.get("datasource")
                if isinstance(datasource, dict):
                    uid = datasource.get("uid")
                    if isinstance(uid, str) and uid:
                        datasource_uids.add(uid)
                    dsid = datasource.get("id")
                    if isinstance(dsid, int):
                        datasource_ids.add(dsid)
                    elif isinstance(dsid, str) and dsid.isdigit():
                        datasource_ids.add(int(dsid))

                for uid_key in ("datasourceUid", "datasourceUID"):
                    value = node.get(uid_key)
                    if isinstance(value, str) and value:
                        datasource_uids.add(value)

                dsid_value = node.get("datasourceId")
                if isinstance(dsid_value, int):
                    datasource_ids.add(dsid_value)
                elif isinstance(dsid_value, str) and dsid_value.isdigit():
                    datasource_ids.add(int(dsid_value))

                for child in node.values():
                    collect(child)
            elif isinstance(node, list):
                for child in node:
                    collect(child)

        collect(payload)

        for uid in datasource_uids:
            registered = db.query(GrafanaDatasource).filter(GrafanaDatasource.grafana_uid == uid).first()
            if not registered:
                continue
            if registered.tenant_id != tenant_id:
                raise HTTPException(status_code=403, detail="Datasource access denied")
            if self._check_datasource_access(db, uid, user_id, tenant_id, group_ids) is None:
                raise HTTPException(status_code=403, detail="Datasource access denied")

        for datasource_id in datasource_ids:
            registered = db.query(GrafanaDatasource).filter(GrafanaDatasource.grafana_id == datasource_id).first()
            if not registered:
                continue
            if registered.tenant_id != tenant_id:
                raise HTTPException(status_code=403, detail="Datasource access denied")
            if self._check_datasource_access_by_id(db, datasource_id, user_id, tenant_id, group_ids) is None:
                raise HTTPException(status_code=403, detail="Datasource access denied")

    def _get_accessible_dashboard_uids(
        self,
        db: Session,
        user_id: str,
        tenant_id: str,
        group_ids: List[str]
    ) -> tuple[List[str], bool]:
        """Get list of dashboard UIDs accessible to user."""
        query = db.query(GrafanaDashboard).filter(
            GrafanaDashboard.tenant_id == tenant_id
        )

        conditions = [
            GrafanaDashboard.created_by == user_id,
            GrafanaDashboard.visibility == "tenant"
        ]

        if group_ids:
            conditions.append(
                and_(
                    GrafanaDashboard.visibility == "group",
                    GrafanaDashboard.shared_groups.any(Group.id.in_(group_ids))
                )
            )

        query = query.filter(or_(*conditions))
        dashboards = query.all()

        return [d.grafana_uid for d in dashboards], True

    def _get_accessible_datasource_uids(
        self,
        db: Session,
        user_id: str,
        tenant_id: str,
        group_ids: List[str]
    ) -> tuple[List[str], bool]:
        """Get list of datasource UIDs accessible to user."""
        query = db.query(GrafanaDatasource).filter(
            GrafanaDatasource.tenant_id == tenant_id
        )

        conditions = [
            GrafanaDatasource.created_by == user_id,
            GrafanaDatasource.visibility == "tenant"
        ]

        if group_ids:
            conditions.append(
                and_(
                    GrafanaDatasource.visibility == "group",
                    GrafanaDatasource.shared_groups.any(Group.id.in_(group_ids))
                )
            )

        query = query.filter(or_(*conditions))
        datasources = query.all()

        return [d.grafana_uid for d in datasources], True

    # ------------------------------------------------------------------
        # Dashboard CRUD with hide/show, UID search

    async def search_dashboards(
        self,
        db: Session,
        user_id: str,
        tenant_id: str,
        group_ids: List[str],
        query: Optional[str] = None,
        tag: Optional[str] = None,
        starred: Optional[bool] = None,
        uid: Optional[str] = None,
        team_id: Optional[str] = None,
        show_hidden: bool = False,
        is_admin: bool = False,
    ) -> List[DashboardSearchResult]:
        """Search dashboards with multi-tenant filtering, UID search, teams."""

        # If searching by UID directly, skip the broad Grafana search
        if uid:
            dashboard = await self.grafana_service.get_dashboard(uid)
            if not dashboard:
                return []
            db_dash = db.query(GrafanaDashboard).filter(
                GrafanaDashboard.grafana_uid == uid
            ).first()
            if db_dash:
                if not self._check_dashboard_access(db, uid, user_id, tenant_id, group_ids):
                    return []
                if not show_hidden and user_id in (db_dash.hidden_by or []):
                    return []
            dash_data = dashboard.get("dashboard", {})
            meta = dashboard.get("meta", {})

            created_by = db_dash.created_by if db_dash else None
            is_hidden = bool(db_dash and user_id in (db_dash.hidden_by or []))
            is_owned = bool(db_dash and db_dash.created_by == user_id)

            return [DashboardSearchResult(
                id=dash_data.get("id", 0),
                uid=uid,
                title=dash_data.get("title", ""),
                uri=f"db/{meta.get('slug', '')}",
                url=meta.get("url", f"/d/{uid}"),
                slug=meta.get("slug", ""),
                type="dash-db",
                tags=dash_data.get("tags", []),
                is_starred=meta.get("isStarred", False),
                folder_id=meta.get("folderId"),
                folder_uid=meta.get("folderUid"),
                folder_title=meta.get("folderTitle"),
                created_by=created_by,
                is_hidden=is_hidden,
                is_owned=is_owned,
            )]

        all_dashboards = await self.grafana_service.search_dashboards(
            query=query, tag=tag, starred=starred
        )

        # Admin users see ALL dashboards
        logger.info(
            "search_dashboards: user_id=%s, is_admin=%s, total_dashboards=%d",
            user_id,
            is_admin,
            len(all_dashboards),
        )
        if is_admin:
            accessible_uids = {d.uid for d in all_dashboards}
            allow_system = True
            logger.info("Admin user - granting access to all %d dashboards", len(accessible_uids))
        else:
            accessible_uids, allow_system = self._get_accessible_dashboard_uids(
                db, user_id, tenant_id, group_ids
            )
            accessible_uids = set(accessible_uids)
            logger.info(
                "Non-admin user - accessible_uids=%d, allow_system=%s",
                len(accessible_uids),
                allow_system,
            )

        all_registered_uids = {
            d.grafana_uid
            for d in db.query(GrafanaDashboard).filter(GrafanaDashboard.tenant_id == tenant_id).all()
        }

        db_dashboards = {
            d.grafana_uid: d
            for d in db.query(GrafanaDashboard).filter(
                GrafanaDashboard.tenant_id == tenant_id
            ).all()
        }

        filtered = []
        for d in all_dashboards:
            if d.uid not in accessible_uids and not (allow_system and d.uid not in all_registered_uids):
                continue

            db_dash = db_dashboards.get(d.uid)

            if db_dash and not show_hidden and user_id in (db_dash.hidden_by or []):
                continue

            if team_id:
                if not db_dash:
                    continue
                shared_ids = [g.id for g in db_dash.shared_groups]
                if team_id not in shared_ids:
                    continue

            # Enhance result with proxy-specific metadata
            payload = d.model_dump()
            payload["created_by"] = db_dash.created_by if db_dash else None
            payload["is_hidden"] = bool(db_dash and user_id in (db_dash.hidden_by or []))
            payload["is_owned"] = bool(db_dash and db_dash.created_by == user_id)

            filtered.append(DashboardSearchResult(**payload))

        logger.info("User %s has access to %d/%d dashboards", user_id, len(filtered), len(all_dashboards))
        return filtered

    async def get_dashboard(
        self, db: Session, uid: str, user_id: str, tenant_id: str, group_ids: List[str]
    ) -> Optional[Dict[str, Any]]:
        """Get a dashboard with access control."""
        db_dashboard = db.query(GrafanaDashboard).filter(GrafanaDashboard.grafana_uid == uid).first()
        if db_dashboard:
            if not self._check_dashboard_access(db, uid, user_id, tenant_id, group_ids):
                return None
        return await self.grafana_service.get_dashboard(uid)

    async def create_dashboard(
        self, db: Session, dashboard_create: DashboardCreate, user_id: str, tenant_id: str,
        group_ids: List[str], visibility: str = "private",
        shared_group_ids: List[str] = None, is_admin: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """Create a dashboard with ownership tracking and Grafana permissions."""
        try:
            # Validate group visibility settings
            groups: List[Group] = []
            if visibility == "group":
                groups = self._validate_group_visibility(
                    db,
                    tenant_id=tenant_id,
                    group_ids=group_ids,
                    shared_group_ids=shared_group_ids,
                    is_admin=is_admin,
                )
            
            try:
                result = await self.grafana_service.create_dashboard(dashboard_create)
            except GrafanaAPIError as gae:
                self._raise_http_from_grafana_error(gae)
            if not result:
                return None

            dashboard_data = result.get("dashboard", {})
            uid = result.get("uid") or dashboard_data.get("uid")
            if not uid:
                return result

            folder_uid = result.get("folderUid") or dashboard_data.get("folderUid")
            if not folder_uid:
                folder_id = getattr(dashboard_create, "folder_id", None)
                try:
                    if folder_id:
                        folders = await self.grafana_service.get_folders()
                        for f in folders:
                            if f.id == folder_id:
                                folder_uid = f.uid
                                break
                except Exception as exc:
                    logger.debug("Unable to resolve folder uid for created dashboard: %s", exc)

            db_dashboard = GrafanaDashboard(
                tenant_id=tenant_id, created_by=user_id, grafana_uid=uid,
                grafana_id=result.get("id"),
                title=dashboard_data.get("title", "Untitled"),
                folder_uid=folder_uid, visibility=visibility,
                tags=dashboard_data.get("tags", []),
                hidden_by=[],
            )

            if visibility == "group" and shared_group_ids:
                db_dashboard.shared_groups.extend(groups)
                # Grafana dashboard-permissions sync removed (feature deprecated)

            db.add(db_dashboard)
            db.commit()
            logger.info("Created dashboard %s for user %s (visibility=%s)", uid, user_id, visibility)
            return result
        except HTTPException:
            # Re-raise HTTP errors we intentionally raised above so they propagate to the router
            raise
        except Exception as e:
            logger.error("Error creating dashboard: %s", e, exc_info=True)
            db.rollback()
            return None

    async def update_dashboard(
        self, db: Session, uid: str, dashboard_update: DashboardUpdate,
        user_id: str, tenant_id: str, group_ids: List[str],
        visibility: Optional[str] = None, shared_group_ids: Optional[List[str]] = None,
        is_admin: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """Update a dashboard with access control and label support."""
        db_dashboard = self._check_dashboard_access(db, uid, user_id, tenant_id, group_ids, require_write=True)
        if not db_dashboard:
            return None

        try:
            result = await self.grafana_service.update_dashboard(uid, dashboard_update)
        except GrafanaAPIError as gae:
            self._raise_http_from_grafana_error(gae)
        if not result:
            return None

        dashboard_data = result.get("dashboard", {})
        db_dashboard.title = dashboard_data.get("title", db_dashboard.title)
        db_dashboard.tags = dashboard_data.get("tags", [])

        if visibility:
            db_dashboard.visibility = visibility
            if visibility == "group" and shared_group_ids is not None:
                groups = self._validate_group_visibility(
                    db,
                    tenant_id=tenant_id,
                    group_ids=group_ids,
                    shared_group_ids=shared_group_ids,
                    is_admin=is_admin,
                )
                db_dashboard.shared_groups.clear()
                db_dashboard.shared_groups.extend(groups)
                # Grafana dashboard-permissions sync removed (feature deprecated)
            elif visibility != "group":
                db_dashboard.shared_groups.clear()

        db.commit()
        return result

    async def delete_dashboard(
        self, db: Session, uid: str, user_id: str, tenant_id: str, group_ids: List[str]
    ) -> bool:
        """Delete a dashboard with access control."""
        db_dashboard = self._check_dashboard_access(db, uid, user_id, tenant_id, group_ids, require_write=True)
        if not db_dashboard:
            return False
        success = await self.grafana_service.delete_dashboard(uid)
        if success:
            db.delete(db_dashboard)
            db.commit()
        return success

    # ------------------------------------------------------------------
        # Dashboard hide/show

    def toggle_dashboard_hidden(self, db: Session, uid: str, user_id: str, tenant_id: str, hidden: bool) -> bool:
        db_dash = db.query(GrafanaDashboard).filter(
            GrafanaDashboard.grafana_uid == uid, GrafanaDashboard.tenant_id == tenant_id
        ).first()
        if not db_dash:
            return False
        hidden_list = list(db_dash.hidden_by or [])
        if hidden and user_id not in hidden_list:
            hidden_list.append(user_id)
        elif not hidden and user_id in hidden_list:
            hidden_list.remove(user_id)
        db_dash.hidden_by = hidden_list
        db.commit()
        return True

    # ------------------------------------------------------------------
        # Datasource CRUD with hide/show, UID search

    async def get_datasources(
        self, db: Session, user_id: str, tenant_id: str, group_ids: List[str],
        uid: Optional[str] = None, team_id: Optional[str] = None,
        show_hidden: bool = False, is_admin: bool = False,
    ) -> List[Datasource]:
        """Get datasources with filtering."""
        if uid:
            ds = await self.grafana_service.get_datasource(uid)
            if not ds:
                return []
            db_ds = db.query(GrafanaDatasource).filter(GrafanaDatasource.grafana_uid == uid).first()
            if db_ds:
                if not self._check_datasource_access(db, uid, user_id, tenant_id, group_ids):
                    return []
                if not show_hidden and user_id in (db_ds.hidden_by or []):
                    return []
            payload = ds.model_dump()
            payload["created_by"] = db_ds.created_by if db_ds else None
            payload["is_hidden"] = bool(db_ds and user_id in (db_ds.hidden_by or []))
            payload["is_owned"] = bool(db_ds and db_ds.created_by == user_id)
            return [Datasource(**payload)]

        all_datasources = await self.grafana_service.get_datasources()
        
        # Admin users see ALL datasources
        if is_admin:
            accessible_uids = {ds.uid for ds in all_datasources}
            allow_system = True
        else:
            accessible_uids, allow_system = self._get_accessible_datasource_uids(db, user_id, tenant_id, group_ids)
            accessible_uids = set(accessible_uids)
        
        all_registered_uids = {
            ds.grafana_uid
            for ds in db.query(GrafanaDatasource).filter(GrafanaDatasource.tenant_id == tenant_id).all()
        }
        db_datasources = {d.grafana_uid: d for d in db.query(GrafanaDatasource).filter(GrafanaDatasource.tenant_id == tenant_id).all()}

        filtered = []
        for ds in all_datasources:
            if ds.uid not in accessible_uids and not (allow_system and ds.uid not in all_registered_uids):
                continue
            db_ds = db_datasources.get(ds.uid)
            if db_ds and not show_hidden and user_id in (db_ds.hidden_by or []):
                continue
            if team_id:
                if not db_ds:
                    continue
                shared_ids = [g.id for g in db_ds.shared_groups]
                if team_id not in shared_ids:
                    continue

            payload = ds.model_dump()
            payload["created_by"] = db_ds.created_by if db_ds else None
            payload["is_hidden"] = bool(db_ds and user_id in (db_ds.hidden_by or []))
            payload["is_owned"] = bool(db_ds and db_ds.created_by == user_id)

            filtered.append(Datasource(**payload))

        return filtered

    async def get_datasource(self, db: Session, uid: str, user_id: str, tenant_id: str, group_ids: List[str]) -> Optional[Datasource]:
        db_datasource = db.query(GrafanaDatasource).filter(GrafanaDatasource.grafana_uid == uid).first()
        if db_datasource:
            if not self._check_datasource_access(db, uid, user_id, tenant_id, group_ids):
                return None
        return await self.grafana_service.get_datasource(uid)

    async def create_datasource(
        self, db: Session, datasource_create: DatasourceCreate, user_id: str, tenant_id: str,
        group_ids: List[str], visibility: str = "private",
        shared_group_ids: List[str] = None, is_admin: bool = False,
    ) -> Optional[Datasource]:
        try:
            if datasource_create.type in {"prometheus", "loki", "tempo"}:
                org_id = getattr(datasource_create, 'org_id', None) or config.DEFAULT_ORG_ID
                json_data = dict(datasource_create.json_data or {})
                secure_json_data = dict(datasource_create.secure_json_data or {})
                json_data.setdefault("httpHeaderName1", "X-Scope-OrgID")
                secure_json_data.setdefault("httpHeaderValue1", org_id)
                datasource_create = datasource_create.model_copy(update={"json_data": json_data, "secure_json_data": secure_json_data})

            groups: List[Group] = []
            if visibility == "group":
                groups = self._validate_group_visibility(
                    db,
                    tenant_id=tenant_id,
                    group_ids=group_ids,
                    shared_group_ids=shared_group_ids,
                    is_admin=is_admin,
                )

            try:
                datasource = await self.grafana_service.create_datasource(datasource_create)
            except GrafanaAPIError as gae:
                self._raise_http_from_grafana_error(gae)
            if not datasource:
                return None

            db_datasource = GrafanaDatasource(
                tenant_id=tenant_id, created_by=user_id,
                grafana_uid=datasource.uid, grafana_id=datasource.id,
                name=datasource.name, type=datasource.type,
                visibility=visibility, hidden_by=[],
            )
            if visibility == "group" and shared_group_ids:
                db_datasource.shared_groups.extend(groups)
            db.add(db_datasource)
            db.commit()
            return datasource
        except HTTPException:
            # Propagate HTTPExceptions (e.g. mapped Grafana errors)
            raise
        except Exception as e:
            logger.error("Error creating datasource: %s", e, exc_info=True)
            db.rollback()
            return None

    async def update_datasource(
        self, db: Session, uid: str, datasource_update: DatasourceUpdate,
        user_id: str, tenant_id: str, group_ids: List[str],
        visibility: Optional[str] = None, shared_group_ids: Optional[List[str]] = None,
        is_admin: bool = False,
    ) -> Optional[Datasource]:
        db_datasource = self._check_datasource_access(db, uid, user_id, tenant_id, group_ids, require_write=True)
        if not db_datasource:
            return None

        if db_datasource.type in {"prometheus", "loki", "tempo"}:
            org_id = getattr(datasource_update, "org_id", None)
            if org_id is not None:
                json_data = dict(datasource_update.json_data or {})
                secure_json_data = dict(datasource_update.secure_json_data or {})
                json_data.setdefault("httpHeaderName1", "X-Scope-OrgID")
                secure_json_data["httpHeaderValue1"] = org_id
                datasource_update = datasource_update.model_copy(update={"json_data": json_data, "secure_json_data": secure_json_data})

        try:
            datasource = await self.grafana_service.update_datasource(uid, datasource_update)
        except GrafanaAPIError as gae:
            self._raise_http_from_grafana_error(gae)

        if not datasource:
            return None

        db_datasource.name = datasource.name
        db_datasource.type = datasource.type

        if visibility:
            if visibility == "group" and shared_group_ids is not None:
                groups = self._validate_group_visibility(
                    db,
                    tenant_id=tenant_id,
                    group_ids=group_ids,
                    shared_group_ids=shared_group_ids,
                    is_admin=is_admin,
                )
                db_datasource.visibility = visibility
                db_datasource.shared_groups.clear()
                db_datasource.shared_groups.extend(groups)
            else:
                db_datasource.visibility = visibility
                if visibility != "group":
                    db_datasource.shared_groups.clear()

        db.commit()
        return datasource

    async def delete_datasource(self, db: Session, uid: str, user_id: str, tenant_id: str, group_ids: List[str]) -> bool:
        db_datasource = self._check_datasource_access(db, uid, user_id, tenant_id, group_ids, require_write=True)
        if not db_datasource:
            return False
        success = await self.grafana_service.delete_datasource(uid)
        if success:
            db.delete(db_datasource)
            db.commit()
        return success

    # ------------------------------------------------------------------
        # Datasource hide/show

    def toggle_datasource_hidden(self, db: Session, uid: str, user_id: str, tenant_id: str, hidden: bool) -> bool:
        db_ds = db.query(GrafanaDatasource).filter(GrafanaDatasource.grafana_uid == uid, GrafanaDatasource.tenant_id == tenant_id).first()
        if not db_ds:
            return False
        hidden_list = list(db_ds.hidden_by or [])
        if hidden and user_id not in hidden_list:
            hidden_list.append(user_id)
        elif not hidden and user_id in hidden_list:
            hidden_list.remove(user_id)
        db_ds.hidden_by = hidden_list
        db.commit()
        return True

    # ------------------------------------------------------------------
    # Metadata for filtering UI
    # ------------------------------------------------------------------

    def get_dashboard_metadata(self, db: Session, tenant_id: str) -> Dict[str, Any]:
        dashboards = db.query(GrafanaDashboard).filter(GrafanaDashboard.tenant_id == tenant_id).all()
        all_teams = set()
        for d in dashboards:
            for g in d.shared_groups:
                all_teams.add(g.id)
        return {
            "team_ids": sorted(all_teams),
        }

    def get_datasource_metadata(self, db: Session, tenant_id: str) -> Dict[str, Any]:
        datasources = db.query(GrafanaDatasource).filter(GrafanaDatasource.tenant_id == tenant_id).all()
        all_teams = set()
        for ds in datasources:
            for g in ds.shared_groups:
                all_teams.add(g.id)
        return {
            "team_ids": sorted(all_teams),
        }


