"""
Gateway Authentication Service - API Router

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

import logging

from fastapi import APIRouter, HTTPException, Request, Response, Security, status
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader
from models.exceptions import DatabaseUnavailableError
from pydantic import BaseModel, Field
from services.gateway_service import GatewayAuthService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/gateway", tags=["gateway"])

service = GatewayAuthService()
otlp_token_header = APIKeyHeader(
    name="x-otlp-token",
    scheme_name="OtlpTokenHeader",
    description="OTLP token used to resolve organization scope in the gateway.",
    auto_error=False,
)


class ValidateTokenResponse(BaseModel):
    org_id: str = Field(..., description="Resolved organization identifier for the OTLP token.")


class GatewayHealthResponse(BaseModel):
    status: str
    service: str


def _validate_otlp_token_request(request: Request, otlp_token: str | None) -> Response:
    service.enforce_ip_allowlist(request)
    service.enforce_rate_limit(request)

    raw_token = otlp_token if isinstance(otlp_token, str) else request.headers.get("x-otlp-token")
    token = service.extract_otlp_token(raw_token)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing x-otlp-token header")

    token_prefix = token[:3] + "..." if len(token) > 3 else token

    try:
        org_id = service.validate_otlp_token(token)
    except DatabaseUnavailableError as exc:
        logger.warning("Auth backend unavailable")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Auth backend unavailable",
        ) from exc

    if not org_id:
        logger.warning("OTLP token validation failed - token_prefix=%s", token_prefix)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or disabled OTLP token")

    response = JSONResponse(status_code=200, content={"org_id": org_id})
    response.headers["X-Scope-OrgID"] = org_id
    return response


@router.post(
    "/validate",
    summary="Validate OTLP Token",
    description="Validates an OTLP token and returns scoped organization metadata.",
    response_description="Validation result with resolved organization scope.",
    response_model=ValidateTokenResponse,
)
async def validate_otlp_token(
    request: Request,
    otlp_token: str | None = Security(otlp_token_header),
) -> Response:
    return _validate_otlp_token_request(request, otlp_token)


@router.post(
    "/validate/{upstream_path:path}",
    include_in_schema=False,
)
async def validate_otlp_token_with_upstream_path(
    request: Request,
    upstream_path: str,
    otlp_token: str | None = Security(otlp_token_header),
) -> Response:
    _ = upstream_path
    return _validate_otlp_token_request(request, otlp_token)


@router.get(
    "/health",
    summary="Gateway Health",
    description="Returns health information for the gateway router surface.",
    response_description="Current gateway router health status.",
)
async def health() -> dict[str, str]:
    return service.health()
