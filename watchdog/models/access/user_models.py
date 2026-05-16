"""
User models for access management, including user creation, updates, and authentication-related data structures.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the
License. You may obtain a copy of the License at
http://www.apache.org/licenses/LICENSE-2.0
"""

import re
from datetime import UTC, datetime

from config import config
from pydantic import BaseModel, ConfigDict, EmailStr, Field, StrictBool, field_serializer, field_validator

from .api_key_models import ApiKey
from .auth_models import Permission, Role

_USERNAME_RE = re.compile(r"^[a-z0-9._-]{3,50}$")


def _serialize_datetime(value: datetime) -> str:
    if getattr(value, "tzinfo", None) is None:
        value = value.replace(tzinfo=UTC)
    return value.isoformat()


def _normalize_username(v: str, *, full_check: bool = True) -> str:
    if v is None:
        raise ValueError("username is required")
    if not isinstance(v, str):
        raise ValueError("username must be a string")
    uname = v.strip().lower()
    if " " in uname:
        raise ValueError("username must not contain spaces")
    if full_check and not _USERNAME_RE.match(uname):
        raise ValueError(
            "username must be 3-50 chars and contain only lowercase letters, " + "numbers, dot, underscore or hyphen"
        )
    return uname


def _normalize_username_input(value: object, *, full_check: bool) -> str:
    if not isinstance(value, str):
        raise ValueError("username must be a string")
    return _normalize_username(value, full_check=full_check)


class UserBase(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    full_name: str | None = None
    org_id: str = Field(
        default=config.DEFAULT_ORG_ID, max_length=100, description="Organization ID for multi-tenant observability"
    )
    role: Role = Role.USER
    group_ids: list[str] = Field(default_factory=list)
    is_active: StrictBool = True

    @field_validator("username", mode="before")
    @classmethod
    def normalize_username(cls, v: object) -> str:
        return _normalize_username_input(v, full_check=True)


class UserCreate(UserBase):
    password: str | None = Field(None, min_length=8)
    must_setup_mfa: StrictBool | None = None
    model_config = ConfigDict(extra="forbid")


class UserUpdate(BaseModel):
    username: str | None = Field(None, min_length=3, max_length=50)
    email: EmailStr | None = None
    full_name: str | None = None
    org_id: str | None = None
    role: Role | None = None
    group_ids: list[str] | None = None
    is_active: StrictBool | None = None
    must_setup_mfa: StrictBool | None = None
    model_config = ConfigDict(extra="forbid")

    @field_validator("username", mode="before")
    @classmethod
    def normalize_update_username(cls, v: object) -> str | None:
        if v is None:
            return None
        return _normalize_username_input(v, full_check=True)


class UserPasswordUpdate(BaseModel):
    current_password: str | None = None
    new_password: str = Field(..., min_length=8)


class User(UserBase):
    id: str
    tenant_id: str
    created_at: datetime
    updated_at: datetime
    last_login: datetime | None = None
    needs_password_change: bool = False
    password_changed_at: datetime | None = None
    session_invalid_before: datetime | None = None
    grafana_user_id: int | None = None
    api_keys: list[ApiKey] = Field(default_factory=list)
    mfa_enabled: bool = False
    must_setup_mfa: bool = False
    auth_provider: str | None = "local"
    model_config = ConfigDict(from_attributes=True)


class UserInDB(User):
    hashed_password: str


class UserResponse(BaseModel):
    id: str
    username: str
    email: str
    full_name: str | None
    role: Role
    group_ids: list[str]
    is_active: bool
    org_id: str
    tenant_id: str
    created_at: datetime
    last_login: datetime | None
    permissions: list[Permission]
    direct_permissions: list[str] = Field(default_factory=list)
    needs_password_change: bool = False
    api_keys: list[ApiKey] = Field(default_factory=list)
    mfa_enabled: bool = False
    must_setup_mfa: bool = False
    auth_provider: str | None = "local"

    @field_serializer(
        "created_at",
        "last_login",
        when_used="json",
    )
    def _serialize_datetimes(self, value: datetime | None) -> str | None:
        if value is None:
            return None
        return _serialize_datetime(value)


class LoginRequest(BaseModel):
    username: str
    password: str
    mfa_code: str | None = None

    @field_validator("username", mode="before")
    @classmethod
    def normalize_login_username(cls, v: object) -> str:
        return _normalize_username_input(v, full_check=False)


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=8)
    full_name: str | None = None

    @field_validator("username", mode="before")
    @classmethod
    def normalize_register_username(cls, v: object) -> str:
        return _normalize_username_input(v, full_check=True)


class TotpEnrollResponse(BaseModel):
    otpauth_url: str
    secret: str


class MfaVerifyRequest(BaseModel):
    code: str


class MfaDisableRequest(BaseModel):
    current_password: str | None = None
    code: str | None = None


class RecoveryCodesResponse(BaseModel):
    recovery_codes: list[str]


class TempPasswordResetResponse(BaseModel):
    email_sent: bool
    message: str
