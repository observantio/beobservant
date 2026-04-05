"""
Map Grafana proxy URL paths to required Watchdog permissions.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the
License. You may obtain a copy of the License at
http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

from typing import Optional, Set

from models.access.auth_models import Permission


def _proxy_perms_static_prefixes(p: str, m: str) -> Optional[Set[str]]:
    if p.startswith("/grafana/d/") or p.startswith("/grafana/d-solo/"):
        return {Permission.READ_DASHBOARDS.value}
    if p.startswith("/grafana/connections/datasources/edit/"):
        return {Permission.UPDATE_DATASOURCES.value, Permission.CREATE_DATASOURCES.value}
    if p.startswith("/grafana/api/search"):
        return {Permission.READ_DASHBOARDS.value}
    if p.startswith("/grafana/api/ds/query"):
        return {Permission.QUERY_DATASOURCES.value}
    if p.startswith("/grafana/api/query-history"):
        if m in {"POST", "PUT", "PATCH", "DELETE"}:
            return {Permission.QUERY_DATASOURCES.value}
        return {Permission.QUERY_DATASOURCES.value, Permission.READ_DASHBOARDS.value}
    if p.startswith("/grafana/api/frontend-metrics"):
        return {Permission.READ_DASHBOARDS.value}
    if p.startswith("/grafana/api/datasources/proxy/"):
        return {Permission.QUERY_DATASOURCES.value}
    return None


def _proxy_perms_dashboard_writes(p: str, m: str) -> Optional[Set[str]]:
    if p.startswith("/grafana/api/dashboards/db") and m == "POST":
        return {
            Permission.CREATE_DASHBOARDS.value,
            Permission.UPDATE_DASHBOARDS.value,
            Permission.WRITE_DASHBOARDS.value,
        }
    if p.startswith("/grafana/api/dashboards/uid/"):
        if m == "GET":
            return {Permission.READ_DASHBOARDS.value}
        if m == "DELETE":
            return {Permission.DELETE_DASHBOARDS.value}
    return None


def _proxy_perms_datasource_uid(p: str, m: str) -> Optional[Set[str]]:
    if not p.startswith("/grafana/api/datasources/uid/"):
        return None
    if "/resources/" in p or "/health" in p or p.endswith("/resources"):
        if m in {"GET", "HEAD", "OPTIONS"}:
            return {Permission.READ_DATASOURCES.value}
        return {Permission.QUERY_DATASOURCES.value}
    if m == "GET":
        return {Permission.READ_DATASOURCES.value}
    if m == "PUT":
        return {Permission.UPDATE_DATASOURCES.value}
    if m == "DELETE":
        return {Permission.DELETE_DATASOURCES.value}
    return None


def _proxy_perms_datasource_collection(p: str, m: str) -> Optional[Set[str]]:
    if not p.startswith("/grafana/api/datasources"):
        return None
    if m == "GET":
        return {Permission.READ_DATASOURCES.value}
    if m == "POST":
        return {Permission.CREATE_DATASOURCES.value}
    return None


def _proxy_perms_f_api(p: str, m: str) -> Optional[Set[str]]:
    if p.startswith("/grafana/api/folders"):
        if m == "GET":
            return {Permission.READ_FOLDERS.value}
        if m == "POST":
            return {Permission.CREATE_FOLDERS.value}
        if m == "DELETE":
            return {Permission.DELETE_FOLDERS.value}
        return None
    if p.startswith("/grafana/api/live"):
        return {Permission.READ_DASHBOARDS.value}
    if m in {"GET", "HEAD", "OPTIONS"}:
        return {
            Permission.READ_DASHBOARDS.value,
            Permission.READ_DATASOURCES.value,
            Permission.READ_FOLDERS.value,
        }
    return set()


def required_permissions_for_path(path: str, method: str) -> Set[str]:
    p = (path or "").lower()
    m = (method or "GET").upper()
    for fn in (
        _proxy_perms_static_prefixes,
        _proxy_perms_dashboard_writes,
        _proxy_perms_datasource_uid,
        _proxy_perms_datasource_collection,
        _proxy_perms_f_api,
    ):
        hit = fn(p, m)
        if hit is not None:
            return hit
    return set()
