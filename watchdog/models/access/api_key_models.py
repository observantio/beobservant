"""
This manages the API key models for the server, including creation, updating, and sharing of API keys with users and
groups.

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


class ApiKeyBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, pattern=r"^[^\x00-\x1F]+$")


class ApiKeyCreate(ApiKeyBase):
    key: str | None = Field(
        None,
        min_length=3,
        max_length=100,
        pattern=r"^[^\x00-\x1F]+$",
        description="Optional custom API key value (org_id / X-Scope-OrgID)",
    )


class ApiKeyUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(None, min_length=1, max_length=100, pattern=r"^[^\x00-\x1F]+$")
    is_enabled: bool | None = None
    is_default: bool | None = None


class ApiKeyShareUser(BaseModel):
    user_id: str
    username: str | None = None
    email: str | None = None
    can_use: bool = True
    created_at: datetime

    @field_serializer("created_at", when_used="json")
    def _serialize_created_at(self, value: datetime) -> str:
        return _serialize_datetime(value)


class ApiKeyShareUpdateRequest(BaseModel):
    user_ids: list[str] = Field(default_factory=list)
    group_ids: list[str] = Field(default_factory=list)


class ApiKey(ApiKeyBase):
    id: str
    key: str
    otlp_token: str | None = Field(None, description="Secure OTLP ingest token for gateway authentication")
    owner_user_id: str | None = None
    owner_username: str | None = None
    is_shared: bool = False
    can_use: bool = True
    shared_with: list[ApiKeyShareUser] = Field(default_factory=list)
    is_default: bool = False
    is_enabled: bool = True
    is_hidden: bool = False
    created_at: datetime
    updated_at: datetime | None = None

    @field_serializer("created_at", "updated_at", when_used="json")
    def _serialize_datetimes(self, value: datetime | None) -> str | None:
        if value is None:
            return None
        return _serialize_datetime(value)
