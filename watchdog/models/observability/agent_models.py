"""
Module defines Pydantic models for Agent-related data structures used in the API layer.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the
License. You may obtain a copy of the License at
http://www.apache.org/licenses/LICENSE-2.0
"""

from datetime import datetime
from typing import Annotated, Dict, Optional, List, Any
from pydantic import BaseModel, Field, field_validator


class AgentHeartbeat(BaseModel):
    name: Annotated[str, Field(min_length=1, description="Agent name")]
    tenant_id: Annotated[str, Field(min_length=1, description="Tenant ID (API key) associated with the agent")]
    signal: Optional[str] = Field(None, description="Signal type (logs, traces, metrics)")
    attributes: Dict[str, str] = Field(default_factory=dict)
    timestamp: Optional[datetime] = None

    @field_validator("timestamp", mode="before")
    @classmethod
    def _reject_numeric_timestamps(cls, value: Any) -> Any:
        if isinstance(value, (bool, int, float)):
            raise ValueError("timestamp must be an ISO-8601 datetime value")
        return value


class AgentInfo(BaseModel):
    id: str
    name: str
    tenant_id: str
    host_name: Optional[str] = None
    last_seen: datetime
    signals: List[str] = Field(default_factory=list)
    attributes: Dict[str, str] = Field(default_factory=dict)
