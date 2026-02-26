from __future__ import annotations

import asyncio
import jwt
import pytest
from fastapi.responses import Response
from starlette.requests import Request

from tests._env import ensure_test_env

ensure_test_env()

from config import config
from models.access.auth_models import Role, TokenData
from services.benotified_proxy_service import BeNotifiedProxyService


def _user(*, tenant_id: str = "tenant-a", user_id: str = "u1") -> TokenData:
    return TokenData(
        user_id=user_id,
        username=f"user-{user_id}",
        tenant_id=tenant_id,
        org_id=tenant_id,
        role=Role.USER,
        permissions=["update:incidents"],
        group_ids=["g1"],
        is_superuser=False,
        is_mfa_setup=False,
    )


def _request(
    *,
    method: str = "POST",
    path: str = "/api/alertmanager/incidents/inc-1/jira",
    headers: list[tuple[bytes, bytes]] | None = None,
    body: bytes = b"{}",
) -> Request:
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": method,
        "path": path,
        "headers": headers or [],
        "client": ("127.0.0.1", 12345),
        "scheme": "http",
        "query_string": b"",
    }
    req = Request(scope)
    req._body = body
    return req


class _DummyResponse:
    status_code = 200
    content = b'{"ok":true}'
    headers = {"content-type": "application/json"}


AUTHENTICATED_ENDPOINT_CASES = [
    ("incidents.get", "GET", "/internal/v1/api/alertmanager/incidents/inc-1", False),
    ("incidents.patch", "PATCH", "/internal/v1/api/alertmanager/incidents/inc-1", True),
    ("silences.get", "GET", "/internal/v1/api/alertmanager/silences/s-1", False),
    ("silences.put", "PUT", "/internal/v1/api/alertmanager/silences/s-1", True),
    ("rules.list", "GET", "/internal/v1/api/alertmanager/rules", False),
    ("rules.create", "POST", "/internal/v1/api/alertmanager/rules", True),
    ("channels.list", "GET", "/internal/v1/api/alertmanager/channels", False),
    ("channels.update", "PUT", "/internal/v1/api/alertmanager/channels/c-1", True),
    ("jira.config", "GET", "/internal/v1/api/alertmanager/jira/config", False),
    ("jira.create", "POST", "/internal/v1/api/alertmanager/incidents/inc-1/jira", True),
]


@pytest.mark.asyncio
async def test_forward_drops_scope_header_for_authenticated_requests(monkeypatch):
    service = BeNotifiedProxyService()
    captured: dict = {}

    async def _fake_request(*, method, url, params, content, headers):
        captured["headers"] = dict(headers)
        captured["url"] = url
        return _DummyResponse()

    monkeypatch.setattr(service, "_write_audit", lambda **_kwargs: None)
    monkeypatch.setattr(service, "_resolve_actor_api_key_id", lambda _current_user: "api-key-1")
    monkeypatch.setattr(service, "_sign_context_token", lambda **_kwargs: "context-jwt")
    monkeypatch.setattr(
        config,
        "get_secret",
        lambda key: {"BENOTIFIED_SERVICE_TOKEN": "service-token"}.get(key),
    )
    service._client.request = _fake_request

    req = _request(
        headers=[
            (b"x-scope-orgid", b"tenant-b"),
            (b"x-request-id", b"corr-1"),
        ]
    )
    resp = await service.forward(
        request=req,
        upstream_path="/internal/v1/api/alertmanager/incidents/inc-1/jira",
        current_user=_user(tenant_id="tenant-a"),
        require_api_key=True,
        audit_action="alertmanager.proxy",
    )
    assert isinstance(resp, Response)
    lowered = {k.lower(): v for k, v in captured["headers"].items()}
    assert "x-scope-orgid" not in lowered
    assert lowered["authorization"] == "Bearer context-jwt"
    assert lowered["x-service-token"] == "service-token"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("_name", "method", "upstream_path", "require_api_key"),
    AUTHENTICATED_ENDPOINT_CASES,
    ids=[case[0] for case in AUTHENTICATED_ENDPOINT_CASES],
)
async def test_forward_authenticated_matrix_blocks_scope_header_spoofing(
    monkeypatch,
    _name,
    method,
    upstream_path,
    require_api_key,
):
    service = BeNotifiedProxyService()
    captured: dict = {}

    async def _fake_request(*, method, url, params, content, headers):
        captured["method"] = method
        captured["url"] = url
        captured["headers"] = dict(headers)
        return _DummyResponse()

    monkeypatch.setattr(service, "_write_audit", lambda **_kwargs: None)
    monkeypatch.setattr(service, "_resolve_actor_api_key_id", lambda _current_user: "api-key-1")
    monkeypatch.setattr(service, "_sign_context_token", lambda **_kwargs: "context-jwt")
    monkeypatch.setattr(
        config,
        "get_secret",
        lambda key: {"BENOTIFIED_SERVICE_TOKEN": "service-token"}.get(key),
    )
    service._client.request = _fake_request

    req = _request(
        method=method,
        path="/api/alertmanager/tenant-spoof-attempt",
        headers=[
            (b"x-scope-orgid", b"tenant-b"),
            (b"x-request-id", b"corr-1"),
        ],
    )
    resp = await service.forward(
        request=req,
        upstream_path=upstream_path,
        current_user=_user(tenant_id="tenant-a"),
        require_api_key=require_api_key,
        audit_action="alertmanager.proxy",
    )
    assert isinstance(resp, Response)
    lowered = {k.lower(): v for k, v in captured["headers"].items()}
    assert "x-scope-orgid" not in lowered
    assert lowered["authorization"] == "Bearer context-jwt"
    assert lowered["x-service-token"] == "service-token"
    assert captured["method"] == method
    assert captured["url"].endswith(upstream_path)


@pytest.mark.asyncio
async def test_forward_authenticated_concurrent_matrix_keeps_tenant_binding(monkeypatch):
    service = BeNotifiedProxyService()
    captured: list[dict] = []
    repetitions = 6

    async def _fake_request(*, method, url, params, content, headers):
        await asyncio.sleep(0.001)
        captured.append({"method": method, "url": url, "headers": dict(headers)})
        return _DummyResponse()

    monkeypatch.setattr(service, "_write_audit", lambda **_kwargs: None)
    monkeypatch.setattr(service, "_resolve_actor_api_key_id", lambda _current_user: "api-key-1")
    monkeypatch.setattr(service, "_sign_context_token", lambda **_kwargs: "context-jwt")
    monkeypatch.setattr(
        config,
        "get_secret",
        lambda key: {"BENOTIFIED_SERVICE_TOKEN": "service-token"}.get(key),
    )
    service._client.request = _fake_request

    tasks = []
    for _ in range(repetitions):
        for _name, method, upstream_path, require_api_key in AUTHENTICATED_ENDPOINT_CASES:
            req = _request(
                method=method,
                path="/api/alertmanager/tenant-spoof-attempt",
                headers=[(b"x-scope-orgid", b"tenant-b")],
            )
            tasks.append(
                asyncio.create_task(
                    service.forward(
                        request=req,
                        upstream_path=upstream_path,
                        current_user=_user(tenant_id="tenant-a"),
                        require_api_key=require_api_key,
                        audit_action="alertmanager.proxy",
                    )
                )
            )

    responses = await asyncio.gather(*tasks)
    assert all(isinstance(resp, Response) and resp.status_code == 200 for resp in responses)
    assert len(captured) == len(AUTHENTICATED_ENDPOINT_CASES) * repetitions

    for item in captured:
        lowered = {k.lower(): v for k, v in item["headers"].items()}
        assert lowered["x-service-token"] == "service-token"
        assert lowered["authorization"] == "Bearer context-jwt"
        assert "x-scope-orgid" not in lowered


@pytest.mark.asyncio
async def test_forward_preserves_scope_header_for_unauthenticated_webhooks(monkeypatch):
    service = BeNotifiedProxyService()
    captured: dict = {}

    async def _fake_request(*, method, url, params, content, headers):
        captured["headers"] = dict(headers)
        return _DummyResponse()

    monkeypatch.setattr(service, "_write_audit", lambda **_kwargs: None)
    monkeypatch.setattr(
        config,
        "get_secret",
        lambda key: {"BENOTIFIED_SERVICE_TOKEN": "service-token"}.get(key),
    )
    service._client.request = _fake_request

    req = _request(
        path="/alerts/webhook",
        headers=[
            (b"x-scope-orgid", b"tenant-webhook"),
            (b"x-beobservant-webhook-token", b"webhook-token"),
        ],
    )
    await service.forward(
        request=req,
        upstream_path="/internal/v1/alertmanager/alerts/webhook",
        current_user=None,
        require_api_key=False,
        audit_action="alertmanager.webhook",
    )
    lowered = {k.lower(): v for k, v in captured["headers"].items()}
    assert lowered["x-scope-orgid"] == "tenant-webhook"
    assert lowered["x-beobservant-webhook-token"] == "webhook-token"
    assert "authorization" not in lowered


def test_sign_context_token_pins_user_and_tenant_claims(monkeypatch):
    service = BeNotifiedProxyService()
    key = "context-signing-key-123"
    monkeypatch.setattr(config, "BENOTIFIED_CONTEXT_ALGORITHM", "HS256")
    monkeypatch.setattr(config, "BENOTIFIED_CONTEXT_ISSUER", "beobservant-main")
    monkeypatch.setattr(config, "BENOTIFIED_CONTEXT_AUDIENCE", "benotified")
    monkeypatch.setattr(config, "BENOTIFIED_CONTEXT_TTL_SECONDS", 120)
    monkeypatch.setattr(
        config,
        "get_secret",
        lambda name: {"BENOTIFIED_CONTEXT_SIGNING_KEY": key}.get(name),
    )

    token = service._sign_context_token(current_user=_user(tenant_id="tenant-a", user_id="u123"), api_key_id="api-k-1")
    payload = jwt.decode(
        token,
        key,
        algorithms=["HS256"],
        audience="benotified",
        issuer="beobservant-main",
    )
    assert payload["tenant_id"] == "tenant-a"
    assert payload["org_id"] == "tenant-a"
    assert payload["user_id"] == "u123"
    assert payload["api_key_id"] == "api-k-1"
    assert payload.get("jti")
