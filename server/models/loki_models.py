"""Loki/Logging related models."""
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum

class LogLevel(str, Enum):
    """Log level enum."""
    DEBUG = "debug"
    INFO = "info"
    WARN = "warn"
    ERROR = "error"
    FATAL = "fatal"

class LogDirection(str, Enum):
    """Log query direction."""
    FORWARD = "forward"
    BACKWARD = "backward"

class LogEntry(BaseModel):
    """Single log entry."""
    timestamp: str = Field(..., description="Timestamp of the log entry")
    line: str = Field(..., description="Content of the log line")
    labels: Optional[Dict[str, str]] = Field(default_factory=dict, description="Labels associated with the log entry")

class LogStream(BaseModel):
    """Log stream with entries."""
    stream: Dict[str, str] = Field(..., description="Labels that identify this stream")
    values: List[List[str]] = Field(..., description="List of [timestamp, line] pairs")

class LogQuery(BaseModel):
    """Query parameters for log search."""
    query: str = Field(..., description="LogQL query string")
    limit: int = Field(100, ge=1, le=5000, description="Maximum number of log entries to return")
    start: Optional[int] = Field(None, description="Start time in nanoseconds")
    end: Optional[int] = Field(None, description="End time in nanoseconds")
    direction: LogDirection = Field(LogDirection.BACKWARD, description="Direction to search logs")
    step: Optional[int] = Field(None, description="Query resolution step in seconds")

class LogStatsResponse(BaseModel):
    """Log statistics."""
    total_entries: int = Field(..., description="Total number of log entries")
    total_bytes: int = Field(..., description="Total size of log data in bytes")
    streams: int = Field(..., description="Number of log streams")
    chunks: int = Field(..., description="Number of log chunks")

class LogResponse(BaseModel):
    """Response containing log streams."""
    status: str = Field(..., description="Response status")
    data: Dict[str, Any] = Field(..., description="Log data containing streams and statistics")
    stats: Optional[LogStatsResponse] = None

class LogLabelsResponse(BaseModel):
    """Available log labels."""
    status: str = Field(..., description="Response status")
    data: List[str] = Field(..., description="List of available label names")

class LogLabelValuesResponse(BaseModel):
    """Values for a specific log label."""
    status: str = Field(..., description="Response status")
    data: List[str] = Field(..., description="List of values for the label")

class LogFilterRequest(BaseModel):
    """Request model for log filtering."""
    labels: Dict[str, str] = Field(..., description="Labels to filter logs by")
    filters: Optional[List[str]] = Field(None, description="Additional filter expressions")
    start: Optional[int] = Field(None, description="Start time in nanoseconds")
    end: Optional[int] = Field(None, description="End time in nanoseconds")
    limit: int = Field(100, ge=1, le=5000, description="Maximum number of log entries to return")

class LogSearchRequest(BaseModel):
    """Request model for log searching."""
    pattern: str = Field(..., description="Search pattern or LogQL query")
    labels: Optional[Dict[str, str]] = Field(None, description="Labels to filter search results")
    start: Optional[int] = Field(None, description="Start time in nanoseconds")
    end: Optional[int] = Field(None, description="End time in nanoseconds")
    limit: int = Field(100, ge=1, le=5000, description="Maximum number of log entries to return")