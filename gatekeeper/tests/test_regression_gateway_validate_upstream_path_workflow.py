"""
Regression tests for gateway validate route variants with upstream paths.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from fastapi.responses import JSONResponse
from routers import gateway_router
from services.gateway_service import DatabaseUnavailableError, GatewayAuthService
from starlette.requests import Request


def _request(headers: list[tuple[bytes, bytes]] | None = None) -> Request:
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "POST",
        "path": "/api/gateway/validate/tempo/v1/traces",
        "headers": headers or [],
        "client": ("127.0.0.1", 1234),
        "scheme": "http",
        "query_string": b"",
    }
    return Request(scope)


@pytest.mark.asyncio
async def test_validate_otlp_token_with_upstream_path_uses_shared_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def _validate(request: Request, otlp_token: str | None):
        captured["path"] = request.url.path
        captured["otlp_token"] = otlp_token
        return JSONResponse(status_code=200, content={"org_id": "tenant-1"})

    monkeypatch.setattr(gateway_router, "_validate_otlp_token_request", _validate)

    result = await gateway_router.validate_otlp_token_with_upstream_path(_request(), "tempo/v1/traces", "tok-123")

    assert result.status_code == 200
    assert captured["path"] == "/api/gateway/validate/tempo/v1/traces"
    assert captured["otlp_token"] == "tok-123"


@pytest.mark.asyncio
async def test_validate_otlp_token_with_upstream_path_rejects_missing_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(GatewayAuthService, "enforce_ip_allowlist", lambda self, request: None)
    monkeypatch.setattr(GatewayAuthService, "enforce_rate_limit", lambda self, request: None)

    with pytest.raises(HTTPException) as exc:
        await gateway_router.validate_otlp_token_with_upstream_path(_request(), "tempo/v1/traces", None)

    assert exc.value.status_code == 401
    assert exc.value.detail == "Missing x-otlp-token header"


@pytest.mark.asyncio
async def test_validate_otlp_token_invalid_token_logs_expected_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    warnings: list[tuple[str, tuple[object, ...]]] = []

    monkeypatch.setattr(GatewayAuthService, "enforce_ip_allowlist", lambda self, request: None)
    monkeypatch.setattr(GatewayAuthService, "enforce_rate_limit", lambda self, request: None)
    monkeypatch.setattr(GatewayAuthService, "validate_otlp_token", lambda self, token: None)
    monkeypatch.setattr(gateway_router.logger, "warning", lambda msg, *args: warnings.append((msg, args)))

    with pytest.raises(HTTPException) as exc:
        await gateway_router.validate_otlp_token_with_upstream_path(_request([(b"x-otlp-token", b"abcdef")]), "x", None)

    assert exc.value.status_code == 401
    assert exc.value.detail == "Invalid or disabled OTLP token"
    assert warnings and warnings[0][0] == "OTLP token validation failed - token_prefix=%s"
    assert warnings[0][1] == ("abc...",)


@pytest.mark.asyncio
async def test_validate_otlp_token_short_token_does_not_ellipsis_log_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    warnings: list[tuple[str, tuple[object, ...]]] = []

    monkeypatch.setattr(GatewayAuthService, "enforce_ip_allowlist", lambda self, request: None)
    monkeypatch.setattr(GatewayAuthService, "enforce_rate_limit", lambda self, request: None)
    monkeypatch.setattr(GatewayAuthService, "validate_otlp_token", lambda self, token: None)
    monkeypatch.setattr(gateway_router.logger, "warning", lambda msg, *args: warnings.append((msg, args)))

    with pytest.raises(HTTPException):
        await gateway_router.validate_otlp_token_with_upstream_path(_request([(b"x-otlp-token", b"abc")]), "x", None)

    assert warnings and warnings[0][1] == ("abc",)


@pytest.mark.asyncio
async def test_validate_otlp_token_four_char_prefix_and_forwarded_validation_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    warnings: list[tuple[str, tuple[object, ...]]] = []
    captured: dict[str, object] = {}

    monkeypatch.setattr(GatewayAuthService, "enforce_ip_allowlist", lambda self, request: None)
    monkeypatch.setattr(GatewayAuthService, "enforce_rate_limit", lambda self, request: None)

    def _validate(self, token):
        captured["token"] = token
        return None

    monkeypatch.setattr(GatewayAuthService, "validate_otlp_token", _validate)
    monkeypatch.setattr(gateway_router.logger, "warning", lambda msg, *args: warnings.append((msg, args)))

    with pytest.raises(HTTPException):
        await gateway_router.validate_otlp_token_with_upstream_path(_request([(b"x-otlp-token", b"abcd")]), "x", None)

    assert captured["token"] == "abcd"
    assert warnings and warnings[0][1] == ("abc...",)


@pytest.mark.asyncio
async def test_validate_otlp_token_database_unavailable_maps_to_503(monkeypatch: pytest.MonkeyPatch) -> None:
    warnings: list[str] = []

    monkeypatch.setattr(GatewayAuthService, "enforce_ip_allowlist", lambda self, request: None)
    monkeypatch.setattr(GatewayAuthService, "enforce_rate_limit", lambda self, request: None)

    def _raise_db_unavailable(self, token):
        raise DatabaseUnavailableError("db down")

    monkeypatch.setattr(GatewayAuthService, "validate_otlp_token", _raise_db_unavailable)
    monkeypatch.setattr(
        gateway_router.logger, "warning", lambda msg, *args: warnings.append(msg % args if args else msg)
    )

    with pytest.raises(HTTPException) as exc:
        await gateway_router.validate_otlp_token_with_upstream_path(_request([(b"x-otlp-token", b"abc")]), "x", None)

    assert exc.value.status_code == 503
    assert exc.value.detail == "Auth backend unavailable"
    assert warnings and warnings[0] == "Auth backend unavailable"


@pytest.mark.asyncio
async def test_validate_otlp_token_success_payload_and_scope_header(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(GatewayAuthService, "enforce_ip_allowlist", lambda self, request: None)
    monkeypatch.setattr(GatewayAuthService, "enforce_rate_limit", lambda self, request: None)
    monkeypatch.setattr(GatewayAuthService, "validate_otlp_token", lambda self, token: "tenant-42")

    result = await gateway_router.validate_otlp_token_with_upstream_path(_request(), "tempo/v1/traces", "tok-42")

    assert result.status_code == 200
    assert result.body == b'{"org_id":"tenant-42"}'
    assert result.headers["X-Scope-OrgID"] == "tenant-42"
