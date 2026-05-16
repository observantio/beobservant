"""
This module defines Pydantic models for group-related data structures used in the API layer.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the
License. You may obtain a copy of the License at
http://www.apache.org/licenses/LICENSE-2.0
"""

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field, field_serializer


def _serialize_datetime(value: datetime) -> str:
    if getattr(value, "tzinfo", None) is None:
        value = value.replace(tzinfo=UTC)
    return value.isoformat()


class GroupBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, pattern=r"^[A-Za-z0-9 _.:-]+$")
    description: str | None = Field(None, max_length=500, pattern=r"^[^\x00-\x1F]*$")
    model_config = ConfigDict(extra="forbid")


class GroupCreate(GroupBase):
    pass


class GroupUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100, pattern=r"^[A-Za-z0-9 _.:-]+$")
    description: str | None = Field(None, max_length=500, pattern=r"^[^\x00-\x1F]*$")
    is_active: bool | None = None
    model_config = ConfigDict(extra="forbid")


class GroupMembersUpdate(BaseModel):
    user_ids: list[str] = Field(default_factory=list)


class PermissionInfo(BaseModel):
    id: str
    name: str
    display_name: str
    description: str | None = None
    resource_type: str
    action: str
    model_config = ConfigDict(from_attributes=True)


class Group(GroupBase):
    id: str
    tenant_id: str
    created_at: datetime
    updated_at: datetime
    permissions: list[PermissionInfo] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)

    @field_serializer("created_at", "updated_at", when_used="json")
    def _serialize_datetimes(self, value: datetime) -> str:
        return _serialize_datetime(value)
