"""Agents router for OTLP heartbeat and agent listing."""
import logging
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List

import httpx
from fastapi import APIRouter, Request, Depends

from models.observability.agent_models import AgentHeartbeat
from services.agent_service import AgentService
from models.access.auth_models import Permission, TokenData
from config import config

from middleware.dependencies import (
    auth_service,
    require_permission_with_scope,
    enforce_public_endpoint_security,
    enforce_header_token,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agents", tags=["agents"])

_otlp_router = APIRouter(tags=["otlp"])

agent_service = AgentService()
_mimir_client = httpx.AsyncClient(
    timeout=httpx.Timeout(config.DEFAULT_TIMEOUT),
    limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
)


def _extract_metrics_count(payload: Dict[str, Any]) -> int:
    result = payload.get("data", {}).get("result", [])
    if not result:
        return 0
    value = result[0].get("value", [0, 0])[1]
    return int(float(value))

@router.get("/")
async def list_agents(current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_AGENTS, "agents"))):
    """List known OTLP agents."""
    return [agent.model_dump() for agent in agent_service.list_agents()]


async def _key_activity(key_value: str) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    start_ns = int((now - timedelta(hours=1)).timestamp() * 1_000_000_000)
    end_ns = int(now.timestamp() * 1_000_000_000)

    metrics_active = False
    metrics_count = 0

    try:
        resp = await _mimir_client.get(
            f"{config.MIMIR_URL.rstrip('/')}/prometheus/api/v1/query",
            params={"query": "count({__name__=~\".+\"})"},
            headers={"X-Scope-OrgID": key_value},
        )
        resp.raise_for_status()
        payload = resp.json()
        metrics_count = _extract_metrics_count(payload)
        metrics_active = metrics_count > 0
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        metrics_active = False

    return {
        "metrics_active": metrics_active,
        "metrics_count": metrics_count,
    }


@router.get("/active")
async def list_active_agents(current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_AGENTS, "agents"))):
    """List activity per API key assigned to the user."""
    api_keys = auth_service.list_api_keys(current_user.user_id)

    tasks: List[asyncio.Task] = []
    for key in api_keys:
        tasks.append(asyncio.create_task(_key_activity(key.key)))

    results = await asyncio.gather(*tasks, return_exceptions=True) if tasks else []

    activity = []
    recent_agents = agent_service.list_agents()
    host_names_by_tenant: Dict[str, set[str]] = {}
    for agent in recent_agents:
        if not agent.host_name:
            continue
        host_names_by_tenant.setdefault(agent.tenant_id, set()).add(agent.host_name)

    for key, result in zip(api_keys, results):
        if isinstance(result, Exception):
            activity.append({
                "name": key.name,
                "is_enabled": key.is_enabled,
                "active": False,
                "success": False,
                "clean": False,
                "host_names": [],
                "metrics_active": False,
                "metrics_count": 0
            })
            continue

        active = bool(result.get("metrics_active"))
        host_names = sorted(host_names_by_tenant.get(key.key, set()))
        activity.append({
            "name": key.name,
            "is_enabled": key.is_enabled,
            "active": active,
            "success": active,
            "clean": active,
            "host_names": host_names,
            **result
        })

    return activity


@router.post("/heartbeat")
async def heartbeat(request: Request, payload: AgentHeartbeat):
    """Receive explicit heartbeat payloads."""
    enforce_public_endpoint_security(
        request,
        scope="agents_heartbeat",
        limit=config.RATE_LIMIT_PUBLIC_PER_MINUTE,
        window_seconds=60,
        allowlist=config.AGENT_INGEST_IP_ALLOWLIST,
    )
    enforce_header_token(
        request,
        header_name="x-agent-heartbeat-token",
        expected_token=config.AGENT_HEARTBEAT_TOKEN,
        unauthorized_detail="Invalid heartbeat token",
    )
    agent_service.update_from_heartbeat(payload)
    return {"status": "ok"}


otlp_router = _otlp_router
