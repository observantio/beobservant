"""
Map Grafana proxy URL paths to required Watchdog permissions.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the
License. You may obtain a copy of the License at
http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

from models.access.auth_models import Permission


def _proxy_perms_static_prefixes(p: str, m: str) -> set[str] | None:
    path_rules: tuple[tuple[str, set[str]], ...] = (
        ("/grafana/d/", {Permission.READ_DASHBOARDS.value}),
        ("/grafana/d-solo/", {Permission.READ_DASHBOARDS.value}),
        (
            "/grafana/connections/datasources/edit/",
            {Permission.UPDATE_DATASOURCES.value, Permission.CREATE_DATASOURCES.value},
        ),
        ("/grafana/api/search", {Permission.READ_DASHBOARDS.value}),
        ("/grafana/api/ds/query", {Permission.QUERY_DATASOURCES.value}),
        ("/grafana/api/frontend-metrics", {Permission.READ_DASHBOARDS.value}),
        ("/grafana/api/datasources/proxy/", {Permission.QUERY_DATASOURCES.value}),
    )
    for prefix, permissions in path_rules:
        if p.startswith(prefix):
            return permissions

    if p.startswith("/grafana/api/query-history"):
        return (
            {Permission.QUERY_DATASOURCES.value}
            if m in {"POST", "PUT", "PATCH", "DELETE"}
            else {Permission.QUERY_DATASOURCES.value, Permission.READ_DASHBOARDS.value}
        )
    return None


def _proxy_perms_dashboard_writes(p: str, m: str) -> set[str] | None:
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


def _proxy_perms_datasource_uid(p: str, m: str) -> set[str] | None:
    if not p.startswith("/grafana/api/datasources/uid/"):
        return None
    if "/resources/" in p or "/health" in p or p.endswith("/resources"):
        return (
            {Permission.READ_DATASOURCES.value}
            if m in {"GET", "HEAD", "OPTIONS"}
            else {Permission.QUERY_DATASOURCES.value}
        )
    mapping: dict[str, set[str]] = {
        "GET": {Permission.READ_DATASOURCES.value},
        "PUT": {Permission.UPDATE_DATASOURCES.value},
        "DELETE": {Permission.DELETE_DATASOURCES.value},
    }
    return mapping.get(m)


def _proxy_perms_datasource_collection(p: str, m: str) -> set[str] | None:
    if not p.startswith("/grafana/api/datasources"):
        return None
    if m == "GET":
        return {Permission.READ_DATASOURCES.value}
    if m == "POST":
        return {Permission.CREATE_DATASOURCES.value}
    return None


def _proxy_perms_f_api(p: str, m: str) -> set[str] | None:
    if p.startswith("/grafana/api/folders"):
        mapping: dict[str, set[str]] = {
            "GET": {Permission.READ_FOLDERS.value},
            "POST": {Permission.CREATE_FOLDERS.value},
            "DELETE": {Permission.DELETE_FOLDERS.value},
        }
        return mapping.get(m)
    if p.startswith("/grafana/api/live"):
        return {Permission.READ_DASHBOARDS.value}
    return (
        {
            Permission.READ_DASHBOARDS.value,
            Permission.READ_DATASOURCES.value,
            Permission.READ_FOLDERS.value,
        }
        if m in {"GET", "HEAD", "OPTIONS"}
        else set()
    )


def required_permissions_for_path(path: str, method: str) -> set[str]:
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
