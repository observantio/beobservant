"""
Module defines Pydantic models for Tempo-related data structures used in the API layer.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the
License. You may obtain a copy of the License at
http://www.apache.org/licenses/LICENSE-2.0
"""

from pydantic import BaseModel, ConfigDict, Field

from custom_types.json import JSONDict, JSONValue


class SpanAttribute(BaseModel):
    key: str = Field(..., description="Attribute key")
    value: JSONValue = Field(..., description="Attribute value")


class Span(BaseModel):
    span_id: str = Field(..., alias="spanID", description="Unique identifier for the span")
    trace_id: str = Field(..., alias="traceID", description="Identifier of the trace this span belongs to")
    parent_span_id: str | None = Field(None, alias="parentSpanID", description="Parent span ID if this is a child span")
    operation_name: str = Field(..., alias="operationName", description="Name of the operation this span represents")
    start_time: int = Field(..., alias="startTime", description="Start time of the span in microseconds")
    duration: int = Field(..., description="Duration of the span in microseconds")
    tags: list[SpanAttribute] = Field(default_factory=list, description="Tags associated with the span")
    service_name: str | None = Field(None, alias="serviceName", description="Service name that emitted this span")
    attributes: JSONDict | None = Field(None, description="Span attributes as a key-value map")
    process_id: str | None = Field(
        None, alias="processID", description="Identifier of the process that created this span"
    )
    warnings: list[str] | None = Field(None, description="Warnings related to this span")
    model_config = ConfigDict(populate_by_name=True)


class Trace(BaseModel):
    trace_id: str = Field(..., alias="traceID", description="Unique identifier for the trace")
    spans: list[Span] = Field(..., description="List of spans in this trace")
    processes: JSONDict | None = Field(default_factory=dict, description="Process information for spans in this trace")
    warnings: list[str] | None = Field(None, description="Warnings related to this trace")
    model_config = ConfigDict(populate_by_name=True)


class TraceQuery(BaseModel):
    service: str | None = Field(None, description="Service name to filter traces")
    operation: str | None = Field(None, description="Operation name to filter spans")
    tags: dict[str, str] | None = Field(None, description="Tags to filter traces")
    start: int | None = Field(None, description="Start time in microseconds")
    end: int | None = Field(None, description="End time in microseconds")
    min_duration: str | None = Field(None, alias="minDuration", description="Minimum duration filter (e.g., '0ms')")
    max_duration: str | None = Field(None, alias="maxDuration", description="Maximum duration filter (e.g., '1s')")
    limit: int = Field(100, ge=1, le=1000, description="Maximum number of traces to return")
    model_config = ConfigDict(populate_by_name=True)


class TraceResponse(BaseModel):
    data: list[Trace] = Field(..., description="List of traces matching the query")
    total: int = Field(..., description="Total number of traces available")
    limit: int = Field(..., description="Maximum number of traces requested")
    offset: int = Field(0, description="Offset for pagination")
    errors: list[str] | None = Field(None, description="Errors that occurred during the query")
