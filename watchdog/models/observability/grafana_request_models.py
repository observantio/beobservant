"""
Grafana request models for Watchdog observability integration.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the
License. You may obtain a copy of the License at
http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field
from custom_types.json import JSONDict


class GrafanaBootstrapSessionRequest(BaseModel):
    next: Optional[str] = None


class GrafanaBootstrapSessionResponse(BaseModel):
    launch_url: str
    org_key: str


class GrafanaDatasourceQueryRequest(BaseModel):
    model_config = ConfigDict(extra="allow")


class GrafanaDashboardPayloadRequest(BaseModel):
    dashboard: Optional[JSONDict] = None
    folder_id: Optional[int] = Field(None, alias="folderId")
    folder_uid: Optional[str] = Field(None, alias="folderUid")
    overwrite: Optional[bool] = None
    message: Optional[str] = None
    inputs: Optional[list[JSONDict]] = None
    model_config = ConfigDict(extra="allow", populate_by_name=True)


class GrafanaHiddenToggleRequest(BaseModel):
    hidden: bool = True


class GrafanaCreateFolderRequest(BaseModel):
    title: str
    allow_dashboard_writes: bool = Field(False, alias="allowDashboardWrites")
    model_config = ConfigDict(populate_by_name=True)


class GrafanaUpdateFolderRequest(BaseModel):
    title: Optional[str] = None
    allow_dashboard_writes: Optional[bool] = Field(None, alias="allowDashboardWrites")
    model_config = ConfigDict(populate_by_name=True)
