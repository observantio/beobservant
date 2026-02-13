"""Proxy authorization and path extraction operations for GrafanaProxyService."""

import re
from typing import Dict, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session, joinedload

from db_models import GrafanaDashboard, GrafanaDatasource
from models.access.auth_models import Permission, TokenData, Role


def is_admin_user(service, token_data: TokenData) -> bool:
    return token_data.role == Role.ADMIN or token_data.is_superuser


def is_resource_accessible(service, resource, token_data: TokenData) -> bool:
    if not resource:
        return False

    if resource.tenant_id != token_data.tenant_id:
        return False

    hidden_by = getattr(resource, "hidden_by", None) or []
    if token_data.user_id in hidden_by:
        return False

    if is_admin_user(service, token_data):
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


def extract_dashboard_uid(service, path: str) -> Optional[str]:
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


def extract_datasource_uid(service, path: str) -> Optional[str]:
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


def extract_datasource_id(service, path: str) -> Optional[int]:
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


def extract_proxy_token(service, request, token: Optional[str] = None) -> Optional[str]:
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
    service,
    request,
    db: Session,
    auth_service,
    token: Optional[str] = None,
    orig: Optional[str] = None,
) -> Dict[str, str]:
    token_to_verify = extract_proxy_token(service, request, token)
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

    is_admin = is_admin_user(service, token_data)
    original_uri = orig or request.headers.get("X-Original-URI", "")
    original_path = original_uri.split("?", 1)[0] if original_uri else ""

    if not is_admin:
        dashboard_uid = extract_dashboard_uid(service, original_path)
        if dashboard_uid:
            dashboard = db.query(GrafanaDashboard).options(joinedload(GrafanaDashboard.shared_groups)).filter(
                GrafanaDashboard.grafana_uid == dashboard_uid
            ).first()
            if dashboard and not is_resource_accessible(service, dashboard, token_data):
                raise HTTPException(status_code=403, detail="Dashboard access denied")

        datasource_uid = extract_datasource_uid(service, original_path)
        if datasource_uid:
            datasource = db.query(GrafanaDatasource).options(joinedload(GrafanaDatasource.shared_groups)).filter(
                GrafanaDatasource.grafana_uid == datasource_uid
            ).first()
            if datasource and not is_resource_accessible(service, datasource, token_data):
                raise HTTPException(status_code=403, detail="Datasource access denied")

        datasource_id = extract_datasource_id(service, original_path)
        if datasource_id is not None:
            datasource = db.query(GrafanaDatasource).options(joinedload(GrafanaDatasource.shared_groups)).filter(
                GrafanaDatasource.grafana_id == datasource_id
            ).first()
            if datasource and not is_resource_accessible(service, datasource, token_data):
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
