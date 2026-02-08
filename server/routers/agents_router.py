"""Agents router for OTLP heartbeat and agent listing."""
import logging
from typing import Dict, Any

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

from models.agent_models import AgentHeartbeat
from services.agent_service import AgentService

from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import ExportLogsServiceRequest
from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import ExportMetricsServiceRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agents", tags=["agents"])

_otlp_router = APIRouter(tags=["otlp"])

agent_service = AgentService()


def _any_value_to_python(value) -> Any:
    if value is None:
        return None
    kind = value.WhichOneof("value")
    if kind == "string_value":
        return value.string_value
    if kind == "bool_value":
        return value.bool_value
    if kind == "int_value":
        return value.int_value
    if kind == "double_value":
        return value.double_value
    if kind == "bytes_value":
        try:
            return value.bytes_value.decode("utf-8", errors="replace")
        except Exception:
            return value.bytes_value
    if kind == "array_value":
        return [_any_value_to_python(v) for v in value.array_value.values]
    if kind == "kvlist_value":
        return {kv.key: _any_value_to_python(kv.value) for kv in value.kvlist_value.values}
    return None


def _attributes_to_dict(attributes) -> Dict[str, Any]:
    return {kv.key: _any_value_to_python(kv.value) for kv in attributes}


def _update_agents_from_resources(resources, signal: str) -> int:
    count = 0
    for res in resources:
        attrs = _attributes_to_dict(res.resource.attributes)
        if attrs:
            agent_service.update_from_resource(attrs, signal)
            count += 1
    return count


@router.get("/")
async def list_agents():
    """List known OTLP agents."""
    return [agent.model_dump() for agent in agent_service.list_agents()]


@router.post("/heartbeat")
async def heartbeat(payload: AgentHeartbeat):
    """Receive explicit heartbeat payloads."""
    agent_service.update_from_heartbeat(payload)
    return {"status": "ok"}


@_otlp_router.post("/v1/traces")
async def otlp_traces(request: Request):
    """Receive OTLP trace exports and update agent registry."""
    body = await request.body()
    try:
        msg = ExportTraceServiceRequest()
        msg.ParseFromString(body)
        count = _update_agents_from_resources(msg.resource_spans, "traces")
        return {"status": "ok", "agents_updated": count}
    except Exception as exc:
        logger.warning("Failed to parse OTLP traces payload: %s", exc)
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": "Invalid OTLP traces payload"},
        )


@_otlp_router.post("/v1/logs")
async def otlp_logs(request: Request):
    """Receive OTLP log exports and update agent registry."""
    body = await request.body()
    try:
        msg = ExportLogsServiceRequest()
        msg.ParseFromString(body)
        count = _update_agents_from_resources(msg.resource_logs, "logs")
        return {"status": "ok", "agents_updated": count}
    except Exception as exc:
        logger.warning("Failed to parse OTLP logs payload: %s", exc)
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": "Invalid OTLP logs payload"},
        )


@_otlp_router.post("/v1/metrics")
async def otlp_metrics(request: Request):
    """Receive OTLP metric exports, update agent registry, and drop metric data."""
    body = await request.body()
    try:
        msg = ExportMetricsServiceRequest()
        msg.ParseFromString(body)
        count = _update_agents_from_resources(msg.resource_metrics, "metrics")
        return {"status": "ok", "agents_updated": count}
    except Exception as exc:
        logger.warning("Failed to parse OTLP metrics payload: %s", exc)
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": "Invalid OTLP metrics payload"},
        )


otlp_router = _otlp_router
