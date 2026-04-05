"""
Structural type for Grafana proxy *ops* entrypoints.

Matches ``_GrafanaProxyCore`` / ``GrafanaProxyService``: HTTP delegation, visibility checks, structured Grafana errors,
and logging. Satisfies ``visibility._GroupVisibilityService`` for resolve/share helpers.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the
License. You may obtain a copy of the License at
http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

import logging
from typing import Protocol

from services.grafana.grafana_service import GrafanaService
from services.grafana.visibility import _GroupVisibilityService


class GrafanaProxyClient(_GroupVisibilityService, Protocol):
    """Proxy core surface used across dashboard, datasource, and folder ops."""

    grafana_service: GrafanaService
    logger: logging.Logger

    def raise_http_from_grafana_error(self, exc: Exception) -> None: ...
