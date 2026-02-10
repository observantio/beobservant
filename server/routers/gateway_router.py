"""OTLP Gateway authentication router.

Provides the token validation endpoint consumed by the nginx OTLP gateway
via ``auth_request``.  The gateway sends each inbound OTLP request's
``x-otlp-token`` header here; this endpoint validates it and returns the
mapped ``X-Org-Id`` (org_id / X-Scope-OrgID) so that nginx can set the
correct tenant header before proxying to Loki, Tempo, or Mimir.
"""
import logging

from fastapi import APIRouter, Request, Response, HTTPException, status

from services.database_auth_service import DatabaseAuthService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/gateway", tags=["gateway"])

auth_service = DatabaseAuthService()


@router.get("/validate")
async def validate_otlp_token(request: Request):
    """Validate an OTLP ingest token and return the mapped org_id.

    Called by the nginx ``auth_request`` subrequest.  On success, returns
    HTTP 200 with the ``X-Org-Id`` response header set to the org_id that
    nginx will forward as ``X-Scope-OrgID`` to the backend.
    """
    token = request.headers.get("x-otlp-token", "").strip()

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing x-otlp-token header",
        )

    org_id = auth_service.validate_otlp_token(token)

    if org_id is None:
        logger.warning(
            "OTLP token validation failed – token_prefix=%s",
            token[:12] + "..." if len(token) > 12 else token,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or disabled OTLP token",
        )

    logger.info(
        "OTLP token validated – token_prefix=%s → org_id=%s",
        token[:12] + "..." if len(token) > 12 else token,
        org_id,
    )

    response = Response(status_code=200)
    response.headers["X-Org-Id"] = org_id
    return response
