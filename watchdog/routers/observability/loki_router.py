"""
Router for Loki log querying, label exploration, and log searching/filtering with multi-tenant access control and query
validation.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the
License. You may obtain a copy of the License at
http://www.apache.org/licenses/LICENSE-2.0
"""

from collections.abc import Awaitable
from typing import Annotated, TypeVar

from config import config
from custom_types.json import JSONDict
from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query, Request, status
from middleware.dependencies import require_permission_with_scope, resolve_tenant_id
from models.access.auth_models import Permission, TokenData
from models.observability.loki_models import (
    LogDirection,
    LogFilterRequest,
    LogLabelsResponse,
    LogLabelValuesResponse,
    LogQuery,
    LogResponse,
    LogSearchRequest,
)
from services.loki_service import (
    AggregateLogsParams,
    FilterLogsParams,
    InstantLogQueryParams,
    LogVolumeParams,
    LokiService,
    SearchLogsByPatternParams,
)
from services.loki_service import (
    LabelValuesParams as ServiceLabelValuesParams,
)

START_TIME_DESC = "Start time in nanoseconds"
END_TIME_DESC = "End time in nanoseconds"

router = APIRouter(prefix="/api/loki", tags=["loki"])

loki_service = LokiService()

ResponseT = TypeVar("ResponseT")


async def _handle_timeout(coro: Awaitable[ResponseT], detail: str) -> ResponseT:
    try:
        return await coro
    except TimeoutError as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=detail,
        ) from exc


async def _read_logs_tenant_id(
    request: Request,
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_LOGS, "loki")),
) -> str:
    return await resolve_tenant_id(request, current_user)


class QueryLogsCoreParams:
    def __init__(
        self,
        query: str = Query(..., description="LogQL query string"),
        limit: int = Query(
            config.DEFAULT_QUERY_LIMIT, ge=1, le=config.MAX_QUERY_LIMIT, description="Maximum log lines to return"
        ),
        direction: LogDirection = Query(LogDirection.BACKWARD, description="Query direction"),
    ) -> None:
        self.query = query
        self.limit = limit
        self.direction = direction


class QueryLogsRangeParams:
    def __init__(
        self,
        start: int | None = Query(None, description=START_TIME_DESC),
        end: int | None = Query(None, description=END_TIME_DESC),
        step: int | None = Query(None, description="Query resolution step in seconds"),
    ) -> None:
        self.start = start
        self.end = end
        self.step = step


class InstantQueryParams:
    def __init__(
        self,
        query: str = Query(..., description="LogQL query string"),
        time: int | None = Query(None, description="Query time in nanoseconds"),
        limit: int = Query(
            config.DEFAULT_QUERY_LIMIT,
            ge=1,
            le=config.MAX_QUERY_LIMIT,
            description="Maximum log lines to return",
        ),
    ) -> None:
        self.query = query
        self.time = time
        self.limit = limit


class LabelValuesParams:
    def __init__(
        self,
        start: int | None = Query(None, description=START_TIME_DESC),
        end: int | None = Query(None, description=END_TIME_DESC),
        query: str | None = Query(None, description="Optional LogQL query filter"),
    ) -> None:
        self.start = start
        self.end = end
        self.query = query


class AggregateQueryParams:
    def __init__(
        self,
        query: str = Query(..., description="LogQL aggregation query"),
        step: int = Query(60, ge=1, description="Query resolution step in seconds"),
    ) -> None:
        self.query = query
        self.step = step


class VolumeQueryParams:
    def __init__(
        self,
        query: str = Query(..., description="LogQL selector query"),
        step: int = Query(300, ge=1, description="Time step in seconds"),
    ) -> None:
        self.query = query
        self.step = step


@router.get("/query", response_model=LogResponse)
async def query_logs(
    tenant_id: Annotated[str, Depends(_read_logs_tenant_id)],
    log_core: Annotated[QueryLogsCoreParams, Depends()],
    log_range: Annotated[QueryLogsRangeParams, Depends()],
) -> LogResponse:
    log_query = LogQuery(
        query=log_core.query,
        limit=log_core.limit,
        start=log_range.start,
        end=log_range.end,
        direction=log_core.direction,
        step=log_range.step,
    )
    return await _handle_timeout(
        loki_service.query_logs(log_query, tenant_id=tenant_id),
        "Loki query timed out",
    )


@router.get("/query_instant", response_model=LogResponse)
async def query_logs_instant(
    tenant_id: Annotated[str, Depends(_read_logs_tenant_id)],
    query_params: Annotated[InstantQueryParams, Depends()],
) -> LogResponse:
    return await _handle_timeout(
        loki_service.query_logs_instant(
            InstantLogQueryParams(
                query=query_params.query,
                at_time=query_params.time,
                limit=query_params.limit,
            ),
            tenant_id=tenant_id,
        ),
        "Loki instant query timed out",
    )


@router.get("/labels", response_model=LogLabelsResponse)
async def get_labels(
    tenant_id: Annotated[str, Depends(_read_logs_tenant_id)],
    start: int | None = Query(None, description=START_TIME_DESC),
    end: int | None = Query(None, description=END_TIME_DESC),
) -> LogLabelsResponse:
    return await _handle_timeout(
        loki_service.get_labels(start, end, tenant_id=tenant_id),
        "Loki labels lookup timed out",
    )


@router.get("/label/{label}/values", response_model=LogLabelValuesResponse)
async def get_label_values(
    tenant_id: Annotated[str, Depends(_read_logs_tenant_id)],
    label_values_params: Annotated[LabelValuesParams, Depends()],
    label: str = Path(..., min_length=1, max_length=128, pattern=r"^[A-Za-z_][A-Za-z0-9_]*$"),
) -> LogLabelValuesResponse:
    return await _handle_timeout(
        loki_service.get_label_values(
            ServiceLabelValuesParams(
                label=label,
                start=label_values_params.start,
                end=label_values_params.end,
                query=label_values_params.query,
            ),
            tenant_id=tenant_id,
        ),
        f"Loki label values lookup timed out for {label}",
    )


@router.post("/search")
async def search_logs(
    tenant_id: Annotated[str, Depends(_read_logs_tenant_id)],
    payload: LogSearchRequest = Body(..., description="Log search request"),
) -> LogResponse:
    return await _handle_timeout(
        loki_service.search_logs_by_pattern(
            SearchLogsByPatternParams(
                pattern=payload.pattern,
                labels=payload.labels or {},
                start=payload.start,
                end=payload.end,
                limit=payload.limit,
                tenant_id=tenant_id,
            ),
        ),
        "Loki search timed out",
    )


@router.post("/filter")
async def filter_logs(
    tenant_id: Annotated[str, Depends(_read_logs_tenant_id)],
    payload: LogFilterRequest = Body(..., description="Log filtering request"),
) -> LogResponse:
    return await _handle_timeout(
        loki_service.filter_logs(
            FilterLogsParams(
                labels=payload.labels or {},
                filters=payload.filters,
                start=payload.start,
                end=payload.end,
                limit=payload.limit,
                tenant_id=tenant_id,
            ),
        ),
        "Loki filter query timed out",
    )


@router.get("/aggregate")
async def aggregate_logs(
    tenant_id: Annotated[str, Depends(_read_logs_tenant_id)],
    query_params: Annotated[AggregateQueryParams, Depends()],
    start: int | None = Query(None, description=START_TIME_DESC),
    end: int | None = Query(None, description=END_TIME_DESC),
) -> JSONDict:
    return await _handle_timeout(
        loki_service.aggregate_logs(
            AggregateLogsParams(
                query=query_params.query,
                start=start,
                end=end,
                step=query_params.step,
            ),
            tenant_id=tenant_id,
        ),
        "Loki aggregation timed out",
    )


@router.get("/volume")
async def get_log_volume(
    tenant_id: Annotated[str, Depends(_read_logs_tenant_id)],
    query_params: Annotated[VolumeQueryParams, Depends()],
    start: int | None = Query(None, description=START_TIME_DESC),
    end: int | None = Query(None, description=END_TIME_DESC),
) -> JSONDict:
    return await _handle_timeout(
        loki_service.get_log_volume(
            LogVolumeParams(
                query=query_params.query,
                start=start,
                end=end,
                step=query_params.step,
            ),
            tenant_id=tenant_id,
        ),
        "Loki volume query timed out",
    )
