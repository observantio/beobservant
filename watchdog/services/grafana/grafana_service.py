"""
Proxy service for Grafana API interactions, including folder management.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the
License. You may obtain a copy of the License at
http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

import base64
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import List, Optional

import httpx

from config import config
from middleware.resilience import with_retry, with_timeout
from models.grafana.grafana_dashboard_models import DashboardCreate, DashboardSearchResult, DashboardUpdate
from models.grafana.grafana_datasource_models import Datasource, DatasourceCreate, DatasourceUpdate
from models.grafana.grafana_folder_models import Folder
from custom_types.json import JSONDict, JSONValue
from services.common.http_client import create_async_client

logger = logging.getLogger(__name__)

QueryParamScalar = str | int | float | bool | None
QueryParamValue = QueryParamScalar | Sequence[QueryParamScalar]
QueryParams = Mapping[str, QueryParamValue]


@dataclass(frozen=True, slots=True)
class GrafanaSafeRequestOpts:
    headers: Mapping[str, str] | None = None
    params: QueryParams | None = None
    json: object | None = None


@dataclass(frozen=True, slots=True)
class GrafanaDashboardSearchRequest:
    query: Optional[str] = None
    tag: Optional[str] = None
    folder_ids: Optional[List[int]] = None
    folder_uids: Optional[List[str]] = None
    dashboard_uids: Optional[List[str]] = None
    starred: Optional[bool] = None


class GrafanaAPIError(Exception):
    def __init__(self, status: int, body: JSONValue | None = None):
        self.status = status
        self.body = body
        super().__init__(f"Grafana API error {status}: {body}")


def _json_dict(value: object) -> JSONDict:
    return value if isinstance(value, dict) else {}


def _dict_list(value: object) -> list[JSONDict]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _datasource_update_payload(existing: Datasource, datasource_update: DatasourceUpdate) -> dict[str, object]:
    data = datasource_update.model_dump(by_alias=True, exclude_none=True)
    data.setdefault("type", existing.type)
    data.setdefault("name", existing.name)
    data.setdefault("url", existing.url)
    data.setdefault("access", existing.access)
    data.setdefault("isDefault", getattr(existing, "is_default", None))
    return data


def _folder_update_payload(folder: Folder, title: str) -> dict[str, object]:
    payload: dict[str, object] = {"title": title, "overwrite": True}
    if getattr(folder, "version", None) is not None:
        payload["version"] = folder.version
    return payload


class _GrafanaServiceCore:
    def __init__(
        self,
        grafana_url: str = config.GRAFANA_URL,
        *,
        username: str = config.GRAFANA_USERNAME,
        password: str = config.GRAFANA_PASSWORD,
        api_key: Optional[str] = None,
    ) -> None:
        self.grafana_url = grafana_url.rstrip("/")
        self.timeout = config.DEFAULT_TIMEOUT
        self._basic_auth_header = "Basic " + base64.b64encode(f"{username}:{password}".encode()).decode()

        resolved_key = api_key or config.GRAFANA_API_KEY
        if resolved_key:
            self.auth_header = f"Bearer {resolved_key}"
            self._using_api_key = True
            logger.info("Using Grafana API key authentication")
        else:
            self.auth_header = self._basic_auth_header
            self._using_api_key = False
            logger.info("Using Grafana Basic authentication (consider using API key)")

        self._client = create_async_client(self.timeout)

    def _headers(self) -> dict[str, str]:
        return {"Authorization": self.auth_header, "Content-Type": "application/json"}

    @staticmethod
    def _parse_error_body(exc: httpx.HTTPStatusError) -> JSONValue | None:
        try:
            body = exc.response.json()
            if isinstance(body, (dict, list, str, int, float, bool)) or body is None:
                return body
            return str(body)
        except (TypeError, ValueError):
            return exc.response.text or None

    async def _request(
        self,
        method: str,
        path: str,
        *,
        opts: GrafanaSafeRequestOpts | None = None,
    ) -> httpx.Response:
        url = f"{self.grafana_url}{path}"
        request_opts = opts or GrafanaSafeRequestOpts()
        request_headers = dict(request_opts.headers or self._headers())
        response = await self._client.request(
            method,
            url,
            headers=request_headers,
            params=request_opts.params,
            json=request_opts.json,
        )
        if (
            response.status_code == 401
            and self._using_api_key
            and request_headers.get("Authorization", "").startswith("Bearer ")
        ):
            logger.warning("Grafana API key rejected (401). Falling back to basic auth.")
            self.auth_header = self._basic_auth_header
            self._using_api_key = False
            response = await self._client.request(
                method,
                url,
                headers=self._headers(),
                params=request_opts.params,
                json=request_opts.json,
            )
        return response

    async def _safe_request(
        self,
        method: str,
        path: str,
        default: JSONValue | None = None,
        *,
        opts: GrafanaSafeRequestOpts | None = None,
    ) -> JSONValue | None:
        request_opts = opts or GrafanaSafeRequestOpts()
        try:
            response = await self._request(method, path, opts=request_opts)
            response.raise_for_status()
            payload = response.json()
            if isinstance(payload, (dict, list, str, int, float, bool)) or payload is None:
                return payload
            return default
        except (httpx.HTTPError, ValueError) as exc:
            logger.error("Grafana %s %s failed: %s", method, path, exc)
            return default

    async def _mutating_request(
        self,
        method: str,
        path: str,
        *,
        opts: GrafanaSafeRequestOpts | None = None,
    ) -> JSONValue | None:
        request_opts = opts or GrafanaSafeRequestOpts()
        try:
            response = await self._request(method, path, opts=request_opts)
            response.raise_for_status()
            payload = response.json()
            if isinstance(payload, (dict, list, str, int, float, bool)) or payload is None:
                return payload
            return None
        except httpx.HTTPStatusError as exc:
            parsed = self._parse_error_body(exc)
            logger.error("Grafana %s %s HTTP %s: %s - %s", method, path, exc.response.status_code, exc, parsed)
            raise GrafanaAPIError(exc.response.status_code, parsed) from exc


class _GrafanaDashboardAPI(_GrafanaServiceCore):
    @with_retry()
    @with_timeout()
    async def search_dashboards(
        self,
        filters: GrafanaDashboardSearchRequest | None = None,
    ) -> List[DashboardSearchResult]:
        search = filters or GrafanaDashboardSearchRequest()
        params: dict[str, QueryParamValue] = {"type": "dash-db"}
        if search.query:
            params["query"] = search.query
        if search.tag:
            params["tag"] = search.tag
        if search.folder_ids:
            params["folderIds"] = search.folder_ids
        if search.folder_uids:
            params["folderUIDs"] = search.folder_uids
        if search.dashboard_uids:
            params["dashboardUID"] = search.dashboard_uids
        if search.starred is not None:
            params["starred"] = search.starred
        data = await self._safe_request("GET", "/api/search", [], opts=GrafanaSafeRequestOpts(params=params))
        return [DashboardSearchResult.model_validate(item) for item in _dict_list(data)]

    @with_retry()
    @with_timeout()
    async def get_dashboard(self, uid: str) -> Optional[JSONDict]:
        result = await self._safe_request("GET", f"/api/dashboards/uid/{uid}")
        return result if isinstance(result, dict) or result is None else None

    @with_retry()
    @with_timeout()
    async def create_dashboard(self, dashboard_create: DashboardCreate) -> Optional[JSONDict]:
        result = await self._mutating_request(
            "POST",
            "/api/dashboards/db",
            opts=GrafanaSafeRequestOpts(json=dashboard_create.model_dump(by_alias=True, exclude_none=True)),
        )
        return result if isinstance(result, dict) or result is None else None

    @with_retry()
    @with_timeout()
    async def update_dashboard(self, uid: str, dashboard_update: DashboardUpdate) -> Optional[JSONDict]:
        if not await self.get_dashboard(uid):
            return None
        dashboard_update.dashboard.uid = uid
        result = await self._mutating_request(
            "POST",
            "/api/dashboards/db",
            opts=GrafanaSafeRequestOpts(json=dashboard_update.model_dump(by_alias=True, exclude_none=True)),
        )
        return result if isinstance(result, dict) or result is None else None

    @with_retry()
    @with_timeout()
    async def delete_dashboard(self, uid: str) -> bool:
        return await self._safe_request("DELETE", f"/api/dashboards/uid/{uid}", False) is not False


class _GrafanaDatasourceAPI(_GrafanaServiceCore):
    @with_retry()
    @with_timeout()
    async def query_datasource(self, payload: JSONDict) -> JSONDict:
        try:
            response = await self._request("POST", "/api/ds/query", opts=GrafanaSafeRequestOpts(json=payload))
            response.raise_for_status()
            payload_json = response.json()
            return payload_json if isinstance(payload_json, dict) else {}
        except httpx.HTTPStatusError as exc:
            parsed = self._parse_error_body(exc)
            logger.error("Grafana POST /api/ds/query HTTP %s: %s", exc.response.status_code, parsed)
            raise GrafanaAPIError(exc.response.status_code, parsed) from exc

    @with_retry()
    @with_timeout()
    async def get_datasources(self) -> List[Datasource]:
        data = await self._safe_request("GET", "/api/datasources", [])
        return [Datasource.model_validate(ds) for ds in _dict_list(data)]

    @with_retry()
    @with_timeout()
    async def get_datasource(self, uid: str) -> Optional[Datasource]:
        data = await self._safe_request("GET", f"/api/datasources/uid/{uid}")
        return Datasource.model_validate(data) if isinstance(data, dict) else None

    @with_retry()
    @with_timeout()
    async def get_datasource_by_name(self, name: str) -> Optional[Datasource]:
        data = await self._safe_request("GET", f"/api/datasources/name/{name}")
        return Datasource.model_validate(data) if isinstance(data, dict) else None

    @with_retry()
    @with_timeout()
    async def create_datasource(self, datasource: DatasourceCreate) -> Optional[Datasource]:
        result = await self._mutating_request(
            "POST",
            "/api/datasources",
            opts=GrafanaSafeRequestOpts(json=datasource.model_dump(by_alias=True, exclude_none=True)),
        )
        datasource_payload = _json_dict(result).get("datasource")
        return Datasource.model_validate(datasource_payload) if isinstance(datasource_payload, dict) else None

    @with_retry()
    @with_timeout()
    async def update_datasource(self, uid: str, datasource_update: DatasourceUpdate) -> Optional[Datasource]:
        existing = await self.get_datasource(uid)
        if not existing:
            return None
        result = await self._mutating_request(
            "PUT",
            f"/api/datasources/uid/{uid}",
            opts=GrafanaSafeRequestOpts(json=_datasource_update_payload(existing, datasource_update)),
        )
        datasource_payload = _json_dict(result).get("datasource")
        if isinstance(datasource_payload, dict):
            return Datasource.model_validate(datasource_payload)
        return await self.get_datasource(uid)

    @with_retry()
    @with_timeout()
    async def delete_datasource(self, uid: str) -> bool:
        return await self._safe_request("DELETE", f"/api/datasources/uid/{uid}", False) is not False


class _GrafanaFolderAPI(_GrafanaServiceCore):
    @with_retry()
    @with_timeout()
    async def get_folders(self) -> List[Folder]:
        data = await self._safe_request("GET", "/api/folders", [])
        return [Folder.model_validate(folder) for folder in _dict_list(data)]

    @with_retry()
    @with_timeout()
    async def create_folder(self, title: str) -> Optional[Folder]:
        data = await self._mutating_request("POST", "/api/folders", opts=GrafanaSafeRequestOpts(json={"title": title}))
        return Folder.model_validate(data) if isinstance(data, dict) else None

    @with_retry()
    @with_timeout()
    async def get_folder(self, uid: str) -> Optional[Folder]:
        data = await self._safe_request("GET", f"/api/folders/{uid}")
        return Folder.model_validate(data) if isinstance(data, dict) else None

    async def _update_folder_once(self, uid: str, payload: dict[str, object]) -> Optional[Folder]:
        data = await self._mutating_request("PUT", f"/api/folders/{uid}", opts=GrafanaSafeRequestOpts(json=payload))
        return Folder.model_validate(data) if isinstance(data, dict) else None

    @with_retry()
    @with_timeout()
    async def update_folder(self, uid: str, title: str) -> Optional[Folder]:
        existing = await self.get_folder(uid)
        if not existing:
            return None
        try:
            return await self._update_folder_once(uid, _folder_update_payload(existing, title))
        except GrafanaAPIError as exc:
            if exc.status != 412:
                raise
        refreshed = await self.get_folder(uid)
        if not refreshed:
            return None
        return await self._update_folder_once(uid, _folder_update_payload(refreshed, title))

    @with_retry()
    @with_timeout()
    async def delete_folder(self, uid: str) -> bool:
        return await self._safe_request("DELETE", f"/api/folders/{uid}", False) is not False


class GrafanaService(_GrafanaDashboardAPI, _GrafanaDatasourceAPI, _GrafanaFolderAPI):
    pass
