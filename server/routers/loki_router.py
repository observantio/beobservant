"""Loki API router."""
from fastapi import APIRouter, HTTPException, Query, Body, Depends, status
from typing import Optional, List, Dict

from models.loki_models import (
    LogQuery, LogResponse, LogLabelsResponse, 
    LogLabelValuesResponse, LogDirection, LogFilterRequest, LogSearchRequest
)
from services.loki_service import LokiService
from middleware.auth import verify_api_key
from config import config, constants

router = APIRouter(
    prefix="/api/loki",
    tags=["loki"],
    dependencies=[Depends(verify_api_key)]
)
loki_service = LokiService()


@router.get(
    "/query",
    response_model=LogResponse,
    summary="Query logs",
    description="Query logs using LogQL. Supports full LogQL syntax including label matchers, line filters, and parsers"
)
async def query_logs(
    query: str = Query(..., description="LogQL query string"),
    limit: int = Query(config.DEFAULT_QUERY_LIMIT, ge=1, le=config.MAX_QUERY_LIMIT, description="Maximum log lines to return"),
    start: Optional[int] = Query(None, description="Start time in nanoseconds"),
    end: Optional[int] = Query(None, description="End time in nanoseconds"),
    direction: LogDirection = Query(LogDirection.BACKWARD, description="Query direction"),
    step: Optional[int] = Query(None, description="Query resolution step in seconds")
) -> LogResponse:
    log_query = LogQuery(
        query=query,
        limit=limit,
        start=start,
        end=end,
        direction=direction,
        step=step
    )
    
    result = await loki_service.query_logs(log_query)
    return result


@router.get("/query_instant", response_model=LogResponse)
async def query_logs_instant(
    query: str = Query(..., description="LogQL query string"),
    time: Optional[int] = Query(None, description="Query time in nanoseconds")
):
    """Query logs at a specific point in time.
    
    Returns logs matching the query at the specified timestamp (or now if not provided).
    """
    result = await loki_service.query_logs_instant(query, time)
    return result


@router.get("/labels", response_model=LogLabelsResponse)
async def get_labels(
    start: Optional[int] = Query(None, description="Start time in nanoseconds"),
    end: Optional[int] = Query(None, description="End time in nanoseconds")
):
    """Get all available log labels.
    
    Returns a list of label names that can be used in queries.
    """
    result = await loki_service.get_labels(start, end)
    return result


@router.get("/label/{label}/values", response_model=LogLabelValuesResponse)
async def get_label_values(
    label: str,
    start: Optional[int] = Query(None, description="Start time in nanoseconds"),
    end: Optional[int] = Query(None, description="End time in nanoseconds"),
    query: Optional[str] = Query(None, description="Optional LogQL query filter")
):
    """Get all values for a specific label.
    
    Returns all unique values for the given label within the time range.
    """
    result = await loki_service.get_label_values(label, start, end, query)
    return result


@router.post("/search")
async def search_logs(request: LogSearchRequest = Body(..., description="Log search request")):
    """Search logs by text pattern with optional label filters.
    
    Searches for logs containing the specified pattern, optionally filtered by labels.
    """
    result = await loki_service.search_logs_by_pattern(
        pattern=request.pattern,
        labels=request.labels,
        start=request.start,
        end=request.end,
        limit=request.limit
    )
    return result


@router.post("/filter")
async def filter_logs(request: LogFilterRequest = Body(..., description="Log filtering request")):
    """Filter logs by labels and optional text filters.
    
    Apply label-based filtering with optional additional text filters.
    Example labels: {"app": "nginx", "level": "error"}
    """
    result = await loki_service.filter_logs(
        labels=request.labels,
        filters=request.filters,
        start=request.start,
        end=request.end,
        limit=request.limit
    )
    return result


@router.get("/aggregate")
async def aggregate_logs(
    query: str = Query(..., description="LogQL aggregation query"),
    start: Optional[int] = Query(None, description="Start time in nanoseconds"),
    end: Optional[int] = Query(None, description="End time in nanoseconds"),
    step: int = Query(60, ge=1, description="Query resolution step in seconds")
):
    """Aggregate logs using LogQL aggregation functions.
    
    Supports aggregation functions like rate(), count_over_time(), bytes_over_time(), etc.
    Example: rate({app="nginx"}[5m])
    """
    result = await loki_service.aggregate_logs(query, start, end, step)
    return result


@router.get("/volume")
async def get_log_volume(
    query: str = Query(..., description="LogQL selector query"),
    start: Optional[int] = Query(None, description="Start time in nanoseconds"),
    end: Optional[int] = Query(None, description="End time in nanoseconds"),
    step: int = Query(300, ge=1, description="Time step in seconds")
):
    """Get log volume over time.
    
    Returns the number of log entries over time for the given query.
    """
    result = await loki_service.get_log_volume(query, start, end, step)
    return result
