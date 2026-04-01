"""
Gateway Authentication Service - API Router

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

import logging

from fastapi import APIRouter, Request, Response, HTTPException, status
from fastapi.responses import JSONResponse

from models.exceptions import DatabaseUnavailable
from services.gateway_service import GatewayAuthService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/gateway", tags=["gateway"])

service = GatewayAuthService()


def _validate_otlp_token_request(request: Request) -> Response:
    service.enforce_ip_allowlist(request)
    service.enforce_rate_limit(request)

    token = service.extract_otlp_token(request.headers.get("x-otlp-token"))
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing x-otlp-token header")

    token_prefix = token[:3] + "..." if len(token) > 3 else token

    try:
        org_id = service.validate_otlp_token(token)
    except DatabaseUnavailable as exc:
        logger.warning("Auth backend unavailable")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Auth backend unavailable",
        ) from exc

    if not org_id:
        logger.warning("OTLP token validation failed – token_prefix=%s", token_prefix)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or disabled OTLP token")

    response = JSONResponse(status_code=200, content={"org_id": org_id})
    response.headers["X-Scope-OrgID"] = org_id
    return response


@router.api_route("/validate", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def validate_otlp_token(request: Request) -> Response:
    return _validate_otlp_token_request(request)


@router.api_route("/validate/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def validate_otlp_token_with_path(request: Request, path: str) -> Response:
    _ = path
    return _validate_otlp_token_request(request)

@router.get("/health")
async def health() -> dict[str, str]:
    return service.health()
