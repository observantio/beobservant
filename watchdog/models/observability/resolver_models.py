"""
Resolver models for Watchdog observability analysis.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the
License. You may obtain a copy of the License at
http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator

from custom_types.json import JSONDict

MAX_EPOCH_VALUE = 9_007_199_254_740_991
EpochInt = Annotated[StrictInt, Field(ge=0, le=MAX_EPOCH_VALUE)]


class AnalyzeRequestPayload(BaseModel):
    tenant_id: str | None = None
    start: EpochInt
    end: EpochInt
    step: str = "15s"
    config_yaml: str | None = None
    services: list[str] = Field(default_factory=list)
    log_query: str | None = None
    metric_queries: list[str] | None = None
    sensitivity: float | None = Field(default=3.0, ge=1.0, le=6.0)
    apdex_threshold_ms: float = 500.0
    slo_target: float = Field(default=0.999, ge=0.0, le=1.0)
    correlation_window_seconds: float = Field(default=60.0, ge=10.0, le=600.0)
    forecast_horizon_seconds: float = Field(default=1800.0, ge=60.0, le=86400.0)

    @model_validator(mode="after")
    def validate_time_range(self) -> AnalyzeRequestPayload:
        if self.start >= self.end:
            raise ValueError("start must be less than end")
        return self


class AnalyzeProxyPayload(BaseModel):
    model_config = ConfigDict(extra="allow")
    tenant_id: str | None = Field(None, max_length=200, pattern=r"^[^\x00-\x1F]*$")
    start: EpochInt | None = None
    end: EpochInt | None = None

    @model_validator(mode="after")
    def validate_time_range(self) -> AnalyzeProxyPayload:
        if self.start is not None and self.end is not None and self.start >= self.end:
            raise ValueError("start must be less than end")
        return self


class AnalyzeJobStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    PROCESSING = "processing"
    SUBMITTED = "submitted"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    DELETED = "deleted"

    @classmethod
    def _missing_(cls, value: object) -> AnalyzeJobStatus:
        if isinstance(value, str):
            normalized = value.strip().lower()
            aliases = {
                "success": cls.COMPLETED,
                "succeeded": cls.COMPLETED,
                "done": cls.COMPLETED,
                "finished": cls.COMPLETED,
                "complete": cls.COMPLETED,
                "in_progress": cls.RUNNING,
                "started": cls.RUNNING,
                "error": cls.FAILED,
            }
            aliased = aliases.get(normalized)
            if aliased is not None:
                return aliased
            for member in cls:
                if member.value == normalized:
                    return member
        return cls.PENDING


class AnalyzeJobCreateResponse(BaseModel):
    job_id: str
    report_id: str
    status: AnalyzeJobStatus
    created_at: datetime
    tenant_id: str
    requested_by: str


class AnalyzeJobSummary(BaseModel):
    job_id: str
    report_id: str
    status: AnalyzeJobStatus
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: int | None = None
    error: str | None = None
    summary_preview: str | None = None
    tenant_id: str
    requested_by: str


class AnalyzeJobListResponse(BaseModel):
    items: list[AnalyzeJobSummary]
    next_cursor: str | None = None


class AnalysisQualityPayload(BaseModel):
    model_config = ConfigDict(extra="allow")
    anomaly_density: dict[str, float] = Field(default_factory=dict)
    suppression_counts: dict[str, int] = Field(default_factory=dict)
    gating_profile: str | None = None
    confidence_calibration_version: str | None = None


class ServiceLatencyPayload(BaseModel):
    model_config = ConfigDict(extra="allow")
    service: str | None = None
    operation: str | None = None
    window_start: float | None = None
    window_end: float | None = None


class RootCausePayload(BaseModel):
    model_config = ConfigDict(extra="allow")
    hypothesis: str | None = None
    corroboration_summary: str | None = None
    suppression_diagnostics: JSONDict = Field(default_factory=dict)
    selection_score_components: dict[str, float] = Field(default_factory=dict)


class AnalyzeResultPayload(BaseModel):
    model_config = ConfigDict(extra="allow")
    quality: AnalysisQualityPayload | None = None
    service_latency: list[ServiceLatencyPayload] = Field(default_factory=list)
    root_causes: list[RootCausePayload] = Field(default_factory=list)


class AnalyzeJobResultResponse(BaseModel):
    job_id: str
    report_id: str
    status: AnalyzeJobStatus
    tenant_id: str
    requested_by: str
    result: AnalyzeResultPayload | JSONDict | None = None


class AnalyzeReportResponse(BaseModel):
    job_id: str
    report_id: str
    status: AnalyzeJobStatus
    tenant_id: str
    requested_by: str
    result: AnalyzeResultPayload | JSONDict | None = None


class AnalyzeReportDeleteResponse(BaseModel):
    report_id: str
    status: AnalyzeJobStatus = AnalyzeJobStatus.DELETED
    deleted: bool = True


class AnalyzeConfigTemplateResponse(BaseModel):
    version: int
    defaults: JSONDict
    template_yaml: str
    file_name: str
