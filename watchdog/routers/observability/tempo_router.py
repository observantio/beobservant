"""
Router for Tempo trace querying, trace retrieval by ID, and service/operation listing with multi-tenant access control
and query validation.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the
License. You may obtain a copy of the License at
http://www.apache.org/licenses/LICENSE-2.0
"""

import asyncio
from contextlib import asynccontextmanager
from typing import Annotated, AsyncGenerator, List, Optional

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Path, Query, Request, status

from config import config
from middleware.dependencies import require_permission_with_scope, resolve_tenant_id
from models.access.auth_models import Permission, TokenData
from models.observability.tempo_models import Trace, TraceQuery, TraceResponse
from services.tempo_service import TempoService

tempo_service = TempoService()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    yield
    await tempo_service.aclose()


router = APIRouter(prefix="/api/tempo", tags=["tempo"])


class SearchTracesShapeParams:
    def __init__(
        self,
        service: Optional[str] = Query(None),
        operation: Optional[str] = Query(None),
        min_duration: Optional[str] = Query(None, alias="minDuration"),
        max_duration: Optional[str] = Query(None, alias="maxDuration"),
    ) -> None:
        self.service = service
        self.operation = operation
        self.min_duration = min_duration
        self.max_duration = max_duration


class SearchTracesWindowParams:
    def __init__(
        self,
        start: Optional[int] = Query(None, description="Start time in microseconds"),
        end: Optional[int] = Query(None, description="End time in microseconds"),
        limit: int = Query(config.DEFAULT_QUERY_LIMIT, ge=1, le=config.MAX_QUERY_LIMIT),
        fetch_full: bool = Query(False, alias="fetchFull"),
    ) -> None:
        self.start = start
        self.end = end
        self.limit = limit
        self.fetch_full = fetch_full


@router.get("/traces/search", response_model=TraceResponse)
async def search_traces(
    request: Request,
    search_shape: Annotated[SearchTracesShapeParams, Depends()],
    search_window: Annotated[SearchTracesWindowParams, Depends()],
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_TRACES, "tempo")),
) -> TraceResponse:
    query = TraceQuery(
        service=search_shape.service,
        operation=search_shape.operation,
        tags=None,
        minDuration=search_shape.min_duration,
        maxDuration=search_shape.max_duration,
        start=search_window.start,
        end=search_window.end,
        limit=search_window.limit,
    )
    tenant_id = await resolve_tenant_id(request, current_user)
    try:
        return await tempo_service.search_traces(
            query, tenant_id=tenant_id, fetch_full_traces=search_window.fetch_full
        )
    except asyncio.TimeoutError as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Tempo search timed out",
        ) from exc


@router.get("/traces/{trace_id}", response_model=Trace)
async def get_trace(
    trace_id: Annotated[str, Path(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9_-]+$")],
    request: Request,
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_TRACES, "tempo")),
) -> Trace:
    tenant_id = await resolve_tenant_id(request, current_user)
    try:
        trace = await tempo_service.get_trace(trace_id, tenant_id=tenant_id)
    except asyncio.TimeoutError as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=f"Tempo trace lookup timed out for {trace_id}",
        ) from exc
    if not trace:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Trace {trace_id} not found")
    return trace


@router.get("/services", response_model=List[str])
async def get_services(
    request: Request,
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_TRACES, "tempo")),
) -> List[str]:
    tenant_id = await resolve_tenant_id(request, current_user)
    try:
        return await tempo_service.get_services(tenant_id=tenant_id)
    except asyncio.TimeoutError as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Tempo services lookup timed out",
        ) from exc


@router.get("/services/{service}/operations", response_model=List[str])
async def get_operations(
    service: str,
    request: Request,
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_TRACES, "tempo")),
) -> List[str]:
    tenant_id = await resolve_tenant_id(request, current_user)
    try:
        return await tempo_service.get_operations(service, tenant_id=tenant_id)
    except asyncio.TimeoutError as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=f"Tempo operations lookup timed out for service {service}",
        ) from exc
