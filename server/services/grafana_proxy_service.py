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
        
        # Owner always has full access
        if dashboard.created_by == user_id:
            return dashboard
        
        # For writes, only owner can modify
        if require_write:
            return None
        
        # Check visibility for read access
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
        
        # Owner always has full access
        if datasource.created_by == user_id:
            logger.info(f"User {user_id} is owner of datasource {datasource_uid}")
            return datasource
        
        # For writes, only owner can modify
        if require_write:
            logger.warning(f"User {user_id} denied write access to datasource {datasource_uid} (not owner)")
            return None
        
        # Check visibility for read access
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
        # Build query for accessible dashboards
        query = db.query(GrafanaDashboard).filter(
            GrafanaDashboard.tenant_id == tenant_id
        )
        
        # Filter by visibility
        conditions = [
            GrafanaDashboard.created_by == user_id,  # Owner
            GrafanaDashboard.visibility == "tenant"   # Tenant-wide
        ]
        
        # Add group visibility if user has groups
        if group_ids:
            conditions.append(
                and_(
                    GrafanaDashboard.visibility == "group",
                    GrafanaDashboard.shared_groups.any(Group.id.in_(group_ids))
                )
            )
        
        query = query.filter(or_(*conditions))
        dashboards = query.all()
        
        # Return owned dashboards + flag to allow system dashboards
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
        # Build query for accessible datasources
        query = db.query(GrafanaDatasource).filter(
            GrafanaDatasource.tenant_id == tenant_id
        )
        
        # Filter by visibility
        conditions = [
            GrafanaDatasource.created_by == user_id,  # Owner
            GrafanaDatasource.visibility == "tenant"   # Tenant-wide
        ]
        
        # Add group visibility if user has groups
        if group_ids:
            conditions.append(
                and_(
                    GrafanaDatasource.visibility == "group",
                    GrafanaDatasource.shared_groups.any(Group.id.in_(group_ids))
                )
            )
        
        query = query.filter(or_(*conditions))
        datasources = query.all()
        
        # Return owned datasources + flag to allow system datasources
        # System datasources are those without ownership records (default datasources)
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
        # Get all dashboards from Grafana
        all_dashboards = await self.grafana_service.search_dashboards(
            query=query,
            tag=tag,
            starred=starred
        )
        
        # Get accessible dashboard UIDs and system flag
        accessible_uids, allow_system = self._get_accessible_dashboard_uids(
            db, user_id, tenant_id, group_ids
        )
        
        # Get all registered dashboard UIDs
        all_registered_uids = {dash.grafana_uid for dash in db.query(GrafanaDashboard).all()}
        
        # Filter dashboards
        filtered_dashboards = []
        for d in all_dashboards:
            # Allow if owned by user
            if d.uid in accessible_uids:
                filtered_dashboards.append(d)
            # Allow if system dashboard (not registered) and system access allowed
            elif allow_system and d.uid not in all_registered_uids:
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
        # Check if it's a registered dashboard
        db_dashboard = db.query(GrafanaDashboard).filter(
            GrafanaDashboard.grafana_uid == uid
        ).first()
        
        # If registered, check access
        if db_dashboard:
            if not self._check_dashboard_access(db, uid, user_id, tenant_id, group_ids):
                logger.warning(f"User {user_id} denied access to dashboard {uid}")
                return None
        # If not registered, it's a system dashboard - allow access
        else:
            logger.info(f"Allowing access to system dashboard {uid} for user {user_id}")
        
        # Get dashboard from Grafana
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
            # Create in Grafana
            result = await self.grafana_service.create_dashboard(dashboard_create)
            
            if not result:
                logger.error("Failed to create dashboard in Grafana")
                return None
            
            # Extract dashboard info
            dashboard_data = result.get("dashboard", {})
            uid = result.get("uid") or dashboard_data.get("uid")
            
            if not uid:
                logger.error("No UID in dashboard creation response")
                return result
            
            # Determine folder UID: prefer response values, else resolve from provided folderId
            folder_uid = (
                result.get("folderUid")
                or dashboard_data.get("folderUid")
                or None
            )

            if not folder_uid:
                # Try resolving from the provided folderId on the create payload
                folder_id = getattr(dashboard_create, "folder_id", None)
                try:
                    if folder_id:
                        folders = await self.grafana_service.get_folders()
                        for f in folders:
                            # Folder.id from model may be int
                            if f.id == folder_id:
                                folder_uid = f.uid
                                break
                except Exception:
                    # If folder resolution fails, leave folder_uid as None
                    folder_uid = folder_uid

            # Store ownership in database
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
            
            # Add shared groups if visibility is group
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
        # Check write access (only owner can update)
        db_dashboard = self._check_dashboard_access(
            db, uid, user_id, tenant_id, group_ids, require_write=True
        )
        
        if not db_dashboard:
            logger.warning(f"User {user_id} denied write access to dashboard {uid}")
            return None
        
        # Update in Grafana
        result = await self.grafana_service.update_dashboard(uid, dashboard_update)
        
        if not result:
            return None
        
        # Update metadata in database
        dashboard_data = result.get("dashboard", {})
        db_dashboard.title = dashboard_data.get("title", db_dashboard.title)
        db_dashboard.tags = dashboard_data.get("tags", [])
        
        # Update visibility if provided
        if visibility:
            db_dashboard.visibility = visibility
            
            # Update shared groups
            if visibility == "group" and shared_group_ids is not None:
                db_dashboard.shared_groups.clear()
                if shared_group_ids:
                    groups = db.query(Group).filter(
                        Group.id.in_(shared_group_ids),
                        Group.tenant_id == tenant_id
                    ).all()
                    db_dashboard.shared_groups.extend(groups)
            elif visibility != "group":
                # Clear shared groups if not group visibility
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
        # Check write access (only owner can delete)
        db_dashboard = self._check_dashboard_access(
            db, uid, user_id, tenant_id, group_ids, require_write=True
        )
        
        if not db_dashboard:
            logger.warning(f"User {user_id} denied delete access to dashboard {uid}")
            return False
        
        # Delete from Grafana
        success = await self.grafana_service.delete_dashboard(uid)
        
        if success:
            # Remove from database
            db.delete(db_dashboard)
            db.commit()
            logger.info(f"Deleted dashboard {uid} by user {user_id}")
        
        return success
    
    # Datasource methods
    
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
        # Get all datasources from Grafana
        all_datasources = await self.grafana_service.get_datasources()
        
        # Get accessible datasource UIDs and system flag
        accessible_uids, allow_system = self._get_accessible_datasource_uids(
            db, user_id, tenant_id, group_ids
        )
        
        # Get all registered datasource UIDs
        all_registered_uids = {ds.grafana_uid for ds in db.query(GrafanaDatasource).all()}
        
        # Filter datasources
        filtered_datasources = []
        for ds in all_datasources:
            # Allow if owned by user
            if ds.uid in accessible_uids:
                filtered_datasources.append(ds)
            # Allow if system datasource (not registered) and system access allowed
            elif allow_system and ds.uid not in all_registered_uids:
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
        # Check if it's a registered datasource
        db_datasource = db.query(GrafanaDatasource).filter(
            GrafanaDatasource.grafana_uid == uid
        ).first()
        
        # If registered, check access
        if db_datasource:
            if not self._check_datasource_access(db, uid, user_id, tenant_id, group_ids):
                logger.warning(f"User {user_id} denied access to datasource {uid}")
                return None
        # If not registered, it's a system datasource - allow access
        else:
            logger.info(f"Allowing access to system datasource {uid} for user {user_id}")
        
        # Get datasource from Grafana
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
            # Create in Grafana
            datasource = await self.grafana_service.create_datasource(datasource_create)
            
            if not datasource:
                logger.error("Failed to create datasource in Grafana")
                return None
            
            # Store ownership in database
            db_datasource = GrafanaDatasource(
                tenant_id=tenant_id,
                created_by=user_id,
                grafana_uid=datasource.uid,
                grafana_id=datasource.id,
                name=datasource.name,
                type=datasource.type,
                visibility=visibility
            )
            
            # Add shared groups if visibility is group
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
        # Check write access (only owner can update)
        db_datasource = self._check_datasource_access(
            db, uid, user_id, tenant_id, group_ids, require_write=True
        )
        
        if not db_datasource:
            logger.warning(f"User {user_id} denied write access to datasource {uid}")
            return None
        
        # Update in Grafana
        datasource = await self.grafana_service.update_datasource(uid, datasource_update)
        
        if not datasource:
            return None
        
        # Update metadata in database
        db_datasource.name = datasource.name
        db_datasource.type = datasource.type
        
        # Update visibility if provided
        if visibility:
            db_datasource.visibility = visibility
            
            # Update shared groups
            if visibility == "group" and shared_group_ids is not None:
                db_datasource.shared_groups.clear()
                if shared_group_ids:
                    groups = db.query(Group).filter(
                        Group.id.in_(shared_group_ids),
                        Group.tenant_id == tenant_id
                    ).all()
                    db_datasource.shared_groups.extend(groups)
            elif visibility != "group":
                # Clear shared groups if not group visibility
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
        # Check write access (only owner can delete)
        db_datasource = self._check_datasource_access(
            db, uid, user_id, tenant_id, group_ids, require_write=True
        )
        
        if not db_datasource:
            logger.warning(f"User {user_id} denied delete access to datasource {uid}")
            return False
        
        # Delete from Grafana
        success = await self.grafana_service.delete_datasource(uid)
        
        if success:
            # Remove from database
            db.delete(db_datasource)
            db.commit()
            logger.info(f"Deleted datasource {uid} by user {user_id}")
        
        return success
