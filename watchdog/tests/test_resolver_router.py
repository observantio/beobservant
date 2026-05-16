"""
Copyright (c) 2026 Stefan Kumarasinghe.

Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the
License. You may obtain a copy of the License at
http://www.apache.org/licenses/LICENSE-2.0
"""

from tests._env import ensure_test_env

ensure_test_env()
import pytest
from routers.observability import resolver_router
from starlette.requests import Request
from tests._proxy_stubs import unpack_resolver_json_request

from models.access.auth_models import Role, TokenData


def _request(
    path: str = "/api/resolver/anomalies/metrics",
    method: str = "POST",
    headers: dict[str, str] | None = None,
) -> Request:
    encoded_headers = [
        (name.lower().encode("latin-1"), value.encode("latin-1")) for name, value in (headers or {}).items()
    ]
    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "headers": encoded_headers,
    }
    return Request(scope)


def _user() -> TokenData:
    return TokenData(
        user_id="u1",
        username="user-1",
        tenant_id="tenant-a",
        org_id="tenant-a",
        role=Role.USER,
        permissions=["read:rca", "create:rca"],
        group_ids=[],
        is_superuser=False,
        is_mfa_setup=False,
    )


@pytest.mark.asyncio
async def test_proxy_post_overrides_payload_tenant(monkeypatch):
    captured = {}

    async def fake_request_json(req, **_kwargs):
        kwargs = unpack_resolver_json_request(req)
        captured.update(kwargs)
        return {"ok": True}

    monkeypatch.setattr(resolver_router.resolver_proxy_service, "request_json", fake_request_json)

    current_user = _user()
    request = _request(headers={"x-correlation-id": "corr-123"})
    payload = resolver_router.AnalyzeProxyPayload.model_validate(
        {
            "tenant_id": "spoofed",
            "start": 1,
            "end": 2,
            "query": "up",
            "optional": None,
        }
    )

    result = await resolver_router.anomalies_metrics(
        request=request,
        payload=payload,
        current_user=current_user,
    )
    assert result == {"ok": True}
    assert captured["method"] == "POST"
    assert captured["upstream_path"] == "/api/v1/anomalies/metrics"
    assert captured["current_user"] is current_user
    assert captured["tenant_id"] == "tenant-a"
    assert captured["audit_action"] == "resolver.proxy.metrics"
    assert captured["correlation_id"] == "corr-123"
    assert captured["payload"]["tenant_id"] == "tenant-a"
    assert captured["payload"]["query"] == "up"
    assert captured["payload"]["start"] == 1
    assert captured["payload"]["end"] == 2
    assert "optional" not in captured["payload"]


@pytest.mark.asyncio
async def test_proxy_post_accepts_raw_dict_payload(monkeypatch):
    captured = {}

    async def fake_request_json(req, **_kwargs):
        captured.update(unpack_resolver_json_request(req))
        return {"ok": True}

    monkeypatch.setattr(resolver_router.resolver_proxy_service, "request_json", fake_request_json)

    current_user = _user()
    result = await resolver_router._proxy_post(
        request=_request(path="/api/resolver/correlate"),
        current_user=current_user,
        upstream_path="/api/v1/correlate",
        payload={"raw": True, "tenant_id": "spoofed"},
        audit_action="resolver.proxy.correlate",
    )
    assert result == {"ok": True}
    assert captured["payload"] == {"raw": True, "tenant_id": "tenant-a"}


@pytest.mark.asyncio
async def test_job_result_requires_completed_status(monkeypatch):
    captured = {}

    async def fake_request_json(req, **_kwargs):
        kwargs = unpack_resolver_json_request(req)
        captured.update(kwargs)
        return {
            "job_id": "job-1",
            "report_id": "rep-1",
            "status": "completed",
            "tenant_id": "tenant-a",
            "requested_by": "u1",
            "result": {"summary": "ok"},
        }

    monkeypatch.setattr(resolver_router.resolver_proxy_service, "request_json", fake_request_json)

    result = await resolver_router.get_analyze_job_result(
        job_id="job-1",
        request=_request(),
        current_user=_user(),
    )
    assert result.job_id == "job-1"
    assert result.report_id == "rep-1"
    assert captured["upstream_path"] == "/api/v1/jobs/job-1/result"


@pytest.mark.asyncio
async def test_get_report_by_id_proxies(monkeypatch):
    captured = {}

    async def fake_request_json(req, **_kwargs):
        kwargs = unpack_resolver_json_request(req)
        captured.update(kwargs)
        return {
            "job_id": "job-1",
            "report_id": "rep-1",
            "status": "completed",
            "tenant_id": "tenant-a",
            "requested_by": "u1",
            "result": {"summary": "ok"},
        }

    monkeypatch.setattr(resolver_router.resolver_proxy_service, "request_json", fake_request_json)
    result = await resolver_router.get_report_by_id("rep-1", _request(), _user())
    assert result.report_id == "rep-1"
    assert captured["upstream_path"] == "/api/v1/reports/rep-1"


@pytest.mark.asyncio
async def test_delete_report_by_id_proxies(monkeypatch):
    captured = {}

    async def fake_request_json(req, **_kwargs):
        kwargs = unpack_resolver_json_request(req)
        captured.update(kwargs)
        return {"report_id": "rep-1", "status": "deleted", "deleted": True}

    monkeypatch.setattr(resolver_router.resolver_proxy_service, "request_json", fake_request_json)
    result = await resolver_router.delete_report_by_id("rep-1", _request(), _user())
    assert result.deleted is True
    assert captured["upstream_path"] == "/api/v1/reports/rep-1"


@pytest.mark.asyncio
async def test_get_analyze_job_result_tolerates_unknown_running_status(monkeypatch):
    async def fake_request_json(_req, **_kwargs):
        return {
            "job_id": "job-2",
            "report_id": "rep-2",
            "status": "in_progress",
            "tenant_id": "tenant-a",
            "requested_by": "u1",
            "result": None,
        }

    monkeypatch.setattr(resolver_router.resolver_proxy_service, "request_json", fake_request_json)
    result = await resolver_router.get_analyze_job_result(
        job_id="job-2",
        request=_request(),
        current_user=_user(),
    )
    assert result.status.value == "running"


@pytest.mark.asyncio
async def test_get_analyze_job_result_maps_succeeded_status_to_completed(monkeypatch):
    async def fake_request_json(_req, **_kwargs):
        return {
            "job_id": "job-2b",
            "report_id": "rep-2b",
            "status": "succeeded",
            "tenant_id": "tenant-a",
            "requested_by": "u1",
            "result": {"summary": "ok"},
        }

    monkeypatch.setattr(resolver_router.resolver_proxy_service, "request_json", fake_request_json)
    result = await resolver_router.get_analyze_job_result(
        job_id="job-2b",
        request=_request(),
        current_user=_user(),
    )
    assert result.status.value == "completed"
    assert result.result == {"summary": "ok"}


@pytest.mark.asyncio
async def test_get_analyze_job_result_maps_conflict_to_job_summary(monkeypatch):
    calls = []

    async def fake_request_json(req, **_kwargs):
        kwargs = unpack_resolver_json_request(req)
        calls.append(kwargs["upstream_path"])
        if kwargs["upstream_path"] == "/api/v1/jobs/job-3/result":
            raise resolver_router.HTTPException(status_code=409, detail="result not ready")
        return {
            "job_id": "job-3",
            "report_id": "rep-3",
            "status": "completed",
            "created_at": "2026-03-08T00:00:00Z",
            "tenant_id": "tenant-a",
            "requested_by": "u1",
            "result": None,
        }

    monkeypatch.setattr(resolver_router.resolver_proxy_service, "request_json", fake_request_json)
    result = await resolver_router.get_analyze_job_result(
        job_id="job-3",
        request=_request(),
        current_user=_user(),
    )
    assert result.job_id == "job-3"
    assert result.report_id == "rep-3"
    assert result.status.value == "completed"
    assert result.result is None
    assert "result" in result.model_fields_set
    assert calls == ["/api/v1/jobs/job-3/result", "/api/v1/jobs/job-3"]


@pytest.mark.asyncio
async def test_get_analyze_job_result_reraises_non_conflict(monkeypatch):
    async def fake_request_json(_req, **_kwargs):
        raise resolver_router.HTTPException(status_code=502, detail="upstream down")

    monkeypatch.setattr(resolver_router.resolver_proxy_service, "request_json", fake_request_json)

    with pytest.raises(resolver_router.HTTPException) as exc:
        await resolver_router.get_analyze_job_result(
            job_id="job-4",
            request=_request(),
            current_user=_user(),
        )
    assert exc.value.status_code == 502


@pytest.mark.asyncio
async def test_ml_weights_feedback_proxies(monkeypatch):
    captured = {}

    async def fake_request_json(req, **_kwargs):
        kwargs = unpack_resolver_json_request(req)
        captured.update(kwargs)
        return {"updated_weights": {"metrics": 0.5}, "update_count": 1}

    monkeypatch.setattr(resolver_router.resolver_proxy_service, "request_json", fake_request_json)
    result = await resolver_router.ml_weights_feedback(
        request=_request(),
        signal="metrics",
        was_correct=True,
        current_user=_user(),
    )
    assert result["update_count"] == 1
    assert captured["upstream_path"] == "/api/v1/ml/weights/feedback"
    assert captured["params"]["tenant_id"] == "tenant-a"
    assert captured["params"]["signal"] == "metrics"
    assert captured["params"]["was_correct"] == "true"


@pytest.mark.asyncio
async def test_ml_weights_reset_proxies(monkeypatch):
    captured = {}

    async def fake_request_json(req, **_kwargs):
        kwargs = unpack_resolver_json_request(req)
        captured.update(kwargs)
        return {"weights": {"metrics": 0.3, "logs": 0.35, "traces": 0.35}, "update_count": 0}

    monkeypatch.setattr(resolver_router.resolver_proxy_service, "request_json", fake_request_json)
    user = TokenData(
        user_id="u1",
        username="user-1",
        tenant_id="tenant-a",
        org_id="tenant-a",
        role=Role.USER,
        permissions=["delete:rca", "read:rca", "create:rca"],
        group_ids=[],
        is_superuser=False,
        is_mfa_setup=False,
    )
    result = await resolver_router.ml_weights_reset(
        request=_request(),
        current_user=user,
    )
    assert result["update_count"] == 0
    assert captured["upstream_path"] == "/api/v1/ml/weights/reset"
    assert captured["params"]["tenant_id"] == "tenant-a"
