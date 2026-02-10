"""Grafana proxy service with multi-tenancy and access control."""
import logging
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_

from services.grafana_service import GrafanaService
from db_models import GrafanaDashboard, GrafanaDatasource, Group
from models.grafana_models import (
    DashboardCreate, DashboardUpdate, DashboardSearchResult,
    Datasource, DatasourceCreate, DatasourceUpdate
)
from config import config

logger = logging.getLogger(__name__)


class GrafanaProxyService:
    """Proxy service for Grafana with multi-tenant access control."""
    
    def __init__(self):
        """Initialize Grafana proxy service."""
        self.grafana_service = GrafanaService()
    
    def _check_dashboard_access(
        self,
        db: Session,
        dashboard_uid: str,
        user_id: str,
        tenant_id: str,
        group_ids: List[str],
        require_write: bool = False
    ) -> Optional[GrafanaDashboard]:
        """Check if user has access to a dashboard.
        
        Args:
            db: Database session
            dashboard_uid: Grafana dashboard UID
            user_id: User ID
            tenant_id: Tenant ID
            group_ids: User's group IDs
            require_write: Whether write access is required
            
        Returns:
            GrafanaDashboard if accessible, None otherwise
        """
        dashboard = db.query(GrafanaDashboard).filter(
            GrafanaDashboard.grafana_uid == dashboard_uid,
            GrafanaDashboard.tenant_id == tenant_id
        ).first()
        
        if not dashboard:
            return None
        
        
        if dashboard.created_by == user_id:
            return dashboard
        
        
        if require_write:
            return None
        
        
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
        """Check if user has access to a datasource.
        
        Args:
            db: Database session
            datasource_uid: Grafana datasource UID
            user_id: User ID
            tenant_id: Tenant ID
            group_ids: User's group IDs
            require_write: Whether write access is required
            
        Returns:
            GrafanaDatasource if accessible, None otherwise
        """
        datasource = db.query(GrafanaDatasource).filter(
            GrafanaDatasource.grafana_uid == datasource_uid,
            GrafanaDatasource.tenant_id == tenant_id
        ).first()
        
        if not datasource:
            logger.warning(f"Datasource {datasource_uid} not found in tenant {tenant_id}")
            return None
        
        logger.info(f"Checking access for datasource {datasource_uid}: created_by={datasource.created_by}, user_id={user_id}, require_write={require_write}")
        
        
        if datasource.created_by == user_id:
            logger.info(f"User {user_id} is owner of datasource {datasource_uid}")
            return datasource
        
        
        if require_write:
            logger.warning(f"User {user_id} denied write access to datasource {datasource_uid} (not owner)")
            return None
        
        
        if datasource.visibility == "tenant":
            return datasource
        elif datasource.visibility == "group":
            shared_group_ids = [g.id for g in datasource.shared_groups]
            if any(gid in shared_group_ids for gid in group_ids):
                return datasource
        
        return None
    
    def _get_accessible_dashboard_uids(
        self,
        db: Session,
        user_id: str,
        tenant_id: str,
        group_ids: List[str]
    ) -> tuple[List[str], bool]:
        """Get list of dashboard UIDs accessible to user.
        
        Args:
            db: Database session
            user_id: User ID
            tenant_id: Tenant ID
            group_ids: User's group IDs
            
        Returns:
            Tuple of (List of accessible Grafana dashboard UIDs, allow_all_system_dashboards)
        """
        
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
        """Get list of datasource UIDs accessible to user.
        
        Args:
            db: Database session
            user_id: User ID
            tenant_id: Tenant ID
            group_ids: User's group IDs
            
        Returns:
            Tuple of (List of accessible Grafana datasource UIDs, allow_all_system_datasources)
        """
        
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
    
    async def search_dashboards(
        self,
        db: Session,
        user_id: str,
        tenant_id: str,
        group_ids: List[str],
        query: Optional[str] = None,
        tag: Optional[str] = None,
        starred: Optional[bool] = None
    ) -> List[DashboardSearchResult]:
        """Search dashboards with multi-tenant filtering.
        
        Args:
            db: Database session
            user_id: User ID
            tenant_id: Tenant ID
            group_ids: User's group IDs
            query: Search query
            tag: Tag filter
            starred: Starred filter
            
        Returns:
            List of accessible dashboards
        """
        
        all_dashboards = await self.grafana_service.search_dashboards(
            query=query,
            tag=tag,
            starred=starred
        )
        
        
        accessible_uids, allow_system = self._get_accessible_dashboard_uids(
            db, user_id, tenant_id, group_ids
        )
        
        
        all_registered_uids = {dash.grafana_uid for dash in db.query(GrafanaDashboard).all()}
        
        
        filtered_dashboards = []
        for d in all_dashboards:
            
            if d.uid in accessible_uids or (allow_system and d.uid not in all_registered_uids):
                filtered_dashboards.append(d)
        
        logger.info(f"User {user_id} has access to {len(filtered_dashboards)}/{len(all_dashboards)} dashboards")
        return filtered_dashboards
    
    async def get_dashboard(
        self,
        db: Session,
        uid: str,
        user_id: str,
        tenant_id: str,
        group_ids: List[str]
    ) -> Optional[Dict[str, Any]]:
        """Get a dashboard with access control.
        
        Args:
            db: Database session
            uid: Dashboard UID
            user_id: User ID
            tenant_id: Tenant ID
            group_ids: User's group IDs
            
        Returns:
            Dashboard data if accessible, None otherwise
        """
        
        db_dashboard = db.query(GrafanaDashboard).filter(
            GrafanaDashboard.grafana_uid == uid
        ).first()
        
        
        if db_dashboard:
            if not self._check_dashboard_access(db, uid, user_id, tenant_id, group_ids):
                logger.warning(f"User {user_id} denied access to dashboard {uid}")
                return None
        
        else:
            logger.info(f"Allowing access to system dashboard {uid} for user {user_id}")
        
        
        return await self.grafana_service.get_dashboard(uid)
    
    async def create_dashboard(
        self,
        db: Session,
        dashboard_create: DashboardCreate,
        user_id: str,
        tenant_id: str,
        group_ids: List[str],
        visibility: str = "private",
        shared_group_ids: List[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Create a dashboard with ownership tracking.
        
        Args:
            db: Database session
            dashboard_create: Dashboard creation data
            user_id: User ID
            tenant_id: Tenant ID
            group_ids: User's group IDs
            visibility: Visibility scope (private, group, tenant)
            shared_group_ids: Group IDs to share with
            
        Returns:
            Created dashboard info or None if error
        """
        try:
            
            result = await self.grafana_service.create_dashboard(dashboard_create)
            
            if not result:
                logger.error("Failed to create dashboard in Grafana")
                return None
            
            
            dashboard_data = result.get("dashboard", {})
            uid = result.get("uid") or dashboard_data.get("uid")
            
            if not uid:
                logger.error("No UID in dashboard creation response")
                return result
            
            
            folder_uid = (
                result.get("folderUid")
                or dashboard_data.get("folderUid")
                or None
            )

            if not folder_uid:
                
                folder_id = getattr(dashboard_create, "folder_id", None)
                try:
                    if folder_id:
                        folders = await self.grafana_service.get_folders()
                        for f in folders:
                            
                            if f.id == folder_id:
                                folder_uid = f.uid
                                break
                except Exception:
                    logger.warning(f"Failed to resolve folder UID for folderId {folder_id}: ", exc_info=True)
                    
            
            db_dashboard = GrafanaDashboard(
                tenant_id=tenant_id,
                created_by=user_id,
                grafana_uid=uid,
                grafana_id=result.get("id"),
                title=dashboard_data.get("title", "Untitled"),
                folder_uid=folder_uid,
                visibility=visibility,
                tags=dashboard_data.get("tags", [])
            )
            
            
            if visibility == "group" and shared_group_ids:
                groups = db.query(Group).filter(
                    Group.id.in_(shared_group_ids),
                    Group.tenant_id == tenant_id
                ).all()
                db_dashboard.shared_groups.extend(groups)
            
            db.add(db_dashboard)
            db.commit()
            
            logger.info(f"Created dashboard {uid} for user {user_id} with visibility={visibility}")
            return result
        except Exception as e:
            logger.error(f"Error creating dashboard: {e}", exc_info=True)
            db.rollback()
            return None
    
    async def update_dashboard(
        self,
        db: Session,
        uid: str,
        dashboard_update: DashboardUpdate,
        user_id: str,
        tenant_id: str,
        group_ids: List[str],
        visibility: Optional[str] = None,
        shared_group_ids: Optional[List[str]] = None
    ) -> Optional[Dict[str, Any]]:
        """Update a dashboard with access control.
        
        Args:
            db: Database session
            uid: Dashboard UID
            dashboard_update: Dashboard update data
            user_id: User ID
            tenant_id: Tenant ID
            group_ids: User's group IDs
            visibility: New visibility scope (optional)
            shared_group_ids: New group IDs to share with (optional)
            
        Returns:
            Updated dashboard info or None if error
        """
        
        db_dashboard = self._check_dashboard_access(
            db, uid, user_id, tenant_id, group_ids, require_write=True
        )
        
        if not db_dashboard:
            logger.warning(f"User {user_id} denied write access to dashboard {uid}")
            return None
        
        
        result = await self.grafana_service.update_dashboard(uid, dashboard_update)
        
        if not result:
            return None
        
        
        dashboard_data = result.get("dashboard", {})
        db_dashboard.title = dashboard_data.get("title", db_dashboard.title)
        db_dashboard.tags = dashboard_data.get("tags", [])
        
        
        if visibility:
            db_dashboard.visibility = visibility
            
            
            if visibility == "group" and shared_group_ids is not None:
                db_dashboard.shared_groups.clear()
                if shared_group_ids:
                    groups = db.query(Group).filter(
                        Group.id.in_(shared_group_ids),
                        Group.tenant_id == tenant_id
                    ).all()
                    db_dashboard.shared_groups.extend(groups)
            elif visibility != "group":
                
                db_dashboard.shared_groups.clear()
        
        db.commit()
        
        logger.info(f"Updated dashboard {uid} by user {user_id}")
        return result
    
    async def delete_dashboard(
        self,
        db: Session,
        uid: str,
        user_id: str,
        tenant_id: str,
        group_ids: List[str]
    ) -> bool:
        """Delete a dashboard with access control.
        
        Args:
            db: Database session
            uid: Dashboard UID
            user_id: User ID
            tenant_id: Tenant ID
            group_ids: User's group IDs
            
        Returns:
            True if successful, False otherwise
        """
        
        db_dashboard = self._check_dashboard_access(
            db, uid, user_id, tenant_id, group_ids, require_write=True
        )
        
        if not db_dashboard:
            logger.warning(f"User {user_id} denied delete access to dashboard {uid}")
            return False
        
        
        success = await self.grafana_service.delete_dashboard(uid)
        
        if success:
            
            db.delete(db_dashboard)
            db.commit()
            logger.info(f"Deleted dashboard {uid} by user {user_id}")
        
        return success
    
    
    
    async def get_datasources(
        self,
        db: Session,
        user_id: str,
        tenant_id: str,
        group_ids: List[str]
    ) -> List[Datasource]:
        """Get datasources with multi-tenant filtering.
        
        Args:
            db: Database session
            user_id: User ID
            tenant_id: Tenant ID
            group_ids: User's group IDs
            
        Returns:
            List of accessible datasources
        """
        all_datasources = await self.grafana_service.get_datasources()
        accessible_uids, allow_system = self._get_accessible_datasource_uids(
            db, user_id, tenant_id, group_ids
        )
        
        all_registered_uids = {ds.grafana_uid for ds in db.query(GrafanaDatasource).all()}
        filtered_datasources = []
        for ds in all_datasources:
            if ds.uid in accessible_uids or (allow_system and ds.uid not in all_registered_uids):
                filtered_datasources.append(ds)
        
        logger.info(f"User {user_id} has access to {len(filtered_datasources)}/{len(all_datasources)} datasources")
        return filtered_datasources
    
    async def get_datasource(
        self,
        db: Session,
        uid: str,
        user_id: str,
        tenant_id: str,
        group_ids: List[str]
    ) -> Optional[Datasource]:
        """Get a datasource with access control.
        
        Args:
            db: Database session
            uid: Datasource UID
            user_id: User ID
            tenant_id: Tenant ID
            group_ids: User's group IDs
            
        Returns:
            Datasource if accessible, None otherwise
        """
        
        db_datasource = db.query(GrafanaDatasource).filter(
            GrafanaDatasource.grafana_uid == uid
        ).first()
        
        
        if db_datasource:
            if not self._check_datasource_access(db, uid, user_id, tenant_id, group_ids):
                logger.warning(f"User {user_id} denied access to datasource {uid}")
                return None
        
        else:
            logger.info(f"Allowing access to system datasource {uid} for user {user_id}")
        
        
        return await self.grafana_service.get_datasource(uid)
    
    async def create_datasource(
        self,
        db: Session,
        datasource_create: DatasourceCreate,
        user_id: str,
        tenant_id: str,
        group_ids: List[str],
        visibility: str = "private",
        shared_group_ids: List[str] = None
    ) -> Optional[Datasource]:
        """Create a datasource with ownership tracking.
        
        Args:
            db: Database session
            datasource_create: Datasource creation data
            user_id: User ID
            tenant_id: Tenant ID
            group_ids: User's group IDs
            visibility: Visibility scope (private, group, tenant)
            shared_group_ids: Group IDs to share with
            
        Returns:
            Created datasource or None if error
        """
        try:
            if datasource_create.type in {"prometheus", "loki", "tempo"}:
                org_id = getattr(datasource_create, 'org_id', None) or config.DEFAULT_ORG_ID
                json_data = dict(datasource_create.json_data or {})
                secure_json_data = dict(datasource_create.secure_json_data or {})

                json_data.setdefault("httpHeaderName1", "X-Scope-OrgID")
                secure_json_data.setdefault("httpHeaderValue1", org_id)

                datasource_create = datasource_create.model_copy(
                    update={
                        "json_data": json_data,
                        "secure_json_data": secure_json_data
                    }
                )
                
                logger.info(f"Creating multi-tenant datasource {datasource_create.name} with org_id={org_id}")

            
            if visibility == "group":
                if not shared_group_ids:
                    logger.warning(f"Datasource create: visibility='group' but no shared_group_ids provided by user {user_id}")
                    raise ValueError("No groups provided for group visibility")

                
                groups = db.query(Group).filter(
                    Group.id.in_(shared_group_ids),
                    Group.tenant_id == tenant_id
                ).all()
                found_ids = {g.id for g in groups}

                
                missing = set(shared_group_ids) - found_ids
                if missing:
                    logger.warning(f"Datasource create: some group ids not found in tenant {tenant_id}: {missing}")
                    raise ValueError(f"Invalid group ids for tenant: {missing}")

                
                not_member = [gid for gid in shared_group_ids if gid not in (group_ids or [])]
                if not_member:
                    logger.warning(f"User {user_id} attempted to share datasource with groups they don't belong to: {not_member}")
                    raise ValueError(f"User not member of groups: {not_member}")

            datasource = await self.grafana_service.create_datasource(datasource_create)
            
            if not datasource:
                logger.error("Failed to create datasource in Grafana")
                return None
            
            db_datasource = GrafanaDatasource(
                tenant_id=tenant_id,
                created_by=user_id,
                grafana_uid=datasource.uid,
                grafana_id=datasource.id,
                name=datasource.name,
                type=datasource.type,
                visibility=visibility
            )
            
            if visibility == "group" and shared_group_ids:
                
                groups = db.query(Group).filter(
                    Group.id.in_(shared_group_ids),
                    Group.tenant_id == tenant_id
                ).all()
                db_datasource.shared_groups.extend(groups)
            
            db.add(db_datasource)
            db.commit()
            
            logger.info(f"Created datasource {datasource.uid} for user {user_id} with visibility={visibility}")
            return datasource
        except Exception as e:
            logger.error(f"Error creating datasource: {e}", exc_info=True)
            db.rollback()
            return None
    
    async def update_datasource(
        self,
        db: Session,
        uid: str,
        datasource_update: DatasourceUpdate,
        user_id: str,
        tenant_id: str,
        group_ids: List[str],
        visibility: Optional[str] = None,
        shared_group_ids: Optional[List[str]] = None
    ) -> Optional[Datasource]:
        """Update a datasource with access control.
        
        Args:
            db: Database session
            uid: Datasource UID
            datasource_update: Datasource update data
            user_id: User ID
            tenant_id: Tenant ID
            group_ids: User's group IDs
            visibility: New visibility scope (optional)
            shared_group_ids: New group IDs to share with (optional)
            
        Returns:
            Updated datasource or None if error
        """
        
        db_datasource = self._check_datasource_access(
            db, uid, user_id, tenant_id, group_ids, require_write=True
        )
        
        if not db_datasource:
            logger.warning(f"User {user_id} denied write access to datasource {uid}")
            return None
        
        
        if db_datasource.type in {"prometheus", "loki", "tempo"}:
            org_id = getattr(datasource_update, "org_id", None)
            if org_id is not None:
                json_data = dict(datasource_update.json_data or {})
                secure_json_data = dict(datasource_update.secure_json_data or {})
                json_data.setdefault("httpHeaderName1", "X-Scope-OrgID")
                secure_json_data["httpHeaderValue1"] = org_id
                datasource_update = datasource_update.model_copy(
                    update={
                        "json_data": json_data,
                        "secure_json_data": secure_json_data
                    }
                )

        datasource = await self.grafana_service.update_datasource(uid, datasource_update)
        
        if not datasource:
            return None
        
        
        db_datasource.name = datasource.name
        db_datasource.type = datasource.type
        
        
        if visibility:
            
            if visibility == "group" and shared_group_ids is not None:
                if not shared_group_ids:
                    logger.warning(f"Datasource update: visibility='group' but no shared_group_ids provided by user {user_id}")
                    return None

                groups = db.query(Group).filter(
                    Group.id.in_(shared_group_ids),
                    Group.tenant_id == tenant_id
                ).all()
                found_ids = {g.id for g in groups}
                missing = set(shared_group_ids) - found_ids
                if missing:
                    logger.warning(f"Datasource update: some group ids not found in tenant {tenant_id}: {missing}")
                    return None

                not_member = [gid for gid in shared_group_ids if gid not in (group_ids or [])]
                if not_member:
                    logger.warning(f"User {user_id} attempted to share datasource with groups they don't belong to: {not_member}")
                    return None

                db_datasource.visibility = visibility
                db_datasource.shared_groups.clear()
                db_datasource.shared_groups.extend(groups)
            else:
                db_datasource.visibility = visibility
                
                if visibility != "group":
                    db_datasource.shared_groups.clear()
        
        db.commit()
        
        logger.info(f"Updated datasource {uid} by user {user_id}")
        return datasource
    
    async def delete_datasource(
        self,
        db: Session,
        uid: str,
        user_id: str,
        tenant_id: str,
        group_ids: List[str]
    ) -> bool:
        """Delete a datasource with access control.
        
        Args:
            db: Database session
            uid: Datasource UID
            user_id: User ID
            tenant_id: Tenant ID
            group_ids: User's group IDs
            
        Returns:
            True if successful, False otherwise
        """
        
        db_datasource = self._check_datasource_access(
            db, uid, user_id, tenant_id, group_ids, require_write=True
        )
        
        if not db_datasource:
            logger.warning(f"User {user_id} denied delete access to datasource {uid}")
            return False
        
        
        success = await self.grafana_service.delete_datasource(uid)
        
        if success:
            
            db.delete(db_datasource)
            db.commit()
            logger.info(f"Deleted datasource {uid} by user {user_id}")
        
        return success
