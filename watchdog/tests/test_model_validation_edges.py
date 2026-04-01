from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from tests._env import ensure_test_env

ensure_test_env()

from models.access.user_models import (
    LoginRequest,
    RegisterRequest,
    TempPasswordResetResponse,
    UserCreate,
    UserUpdate,
    _normalize_username,
    _normalize_username_input,
)
from models.access import group_models
from models.access import user_models
from models.observability.agent_models import AgentHeartbeat, AgentInfo
from models.observability.resolver_models import (
    AnalyzeJobCreateResponse,
    AnalyzeJobStatus,
    AnalyzeRequestPayload,
)


@pytest.mark.parametrize(
    ("value", "message"),
    [
        (None, "username is required"),
        (123, "username must be a string"),
        ("bad name", "username must not contain spaces"),
        ("UP", "username must be 3-50 chars"),
    ],
)
def test_username_normalization_rejects_invalid_values(value, message):
    with pytest.raises(ValueError, match=message):
        _normalize_username(value)  # type: ignore[arg-type]


def test_username_input_normalization_and_model_validators():
    assert _normalize_username_input(" User.Name ", full_check=True) == "user.name"
    assert LoginRequest(username=" User ", password="password123").username == "user"
    assert UserCreate(username=" User.Name ", email="user@example.com", password="password123").username == "user.name"
    assert UserUpdate(username=None).username is None

    with pytest.raises(ValueError, match="username must be a string"):
        _normalize_username_input(1, full_check=False)

    with pytest.raises(ValidationError, match="username must not contain spaces"):
        RegisterRequest(username="Bad Name", email="user@example.com", password="password123")


def test_misc_model_payloads_cover_status_aliases_and_time_validation():
    response = TempPasswordResetResponse(
        temporary_password="TempPassword123!",
        email_sent=True,
        message="sent",
    )
    assert response.email_sent is True

    with pytest.raises(ValidationError, match="start must be less than end"):
        AnalyzeRequestPayload(start=10, end=10)

    created = AnalyzeJobCreateResponse(
        job_id="job-1",
        report_id="report-1",
        status="success",
        created_at=datetime.now(timezone.utc),
        tenant_id="tenant-a",
        requested_by="user-1",
    )
    assert created.status is AnalyzeJobStatus.COMPLETED
    assert AnalyzeJobStatus("completed") is AnalyzeJobStatus.COMPLETED
    assert AnalyzeJobStatus(" completed ") is AnalyzeJobStatus.COMPLETED
    assert AnalyzeJobStatus("error") is AnalyzeJobStatus.FAILED
    assert AnalyzeJobStatus(" started ") is AnalyzeJobStatus.RUNNING
    assert AnalyzeJobStatus("unknown-status") is AnalyzeJobStatus.PENDING
    assert AnalyzeJobStatus._missing_(object()) is AnalyzeJobStatus.PENDING


def test_datetime_serializers_and_agent_model_edges():
    naive = datetime(2026, 1, 1, 0, 0, 0)
    assert group_models._serialize_datetime(naive).endswith("+00:00")
    assert user_models._serialize_datetime(naive).endswith("+00:00")

    with pytest.raises(ValidationError, match="ISO-8601"):
        AgentHeartbeat(name="agent-a", tenant_id="tenant-a", timestamp=0)

    heartbeat = AgentHeartbeat(name="agent-a", tenant_id="tenant-a", timestamp="2026-01-01T00:00:00Z")
    assert heartbeat.timestamp is not None

    info = AgentInfo(id="a1", name="agent-a", tenant_id="tenant-a", last_seen=datetime.now(timezone.utc))
    assert info.signals == []
