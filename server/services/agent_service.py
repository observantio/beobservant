import logging
from datetime import datetime, timezone
from typing import Dict, Any, List

from models.agent_models import AgentHeartbeat, AgentInfo

logger = logging.getLogger(__name__)


class AgentService:
    """In-memory registry of recently active OTLP agents."""

    def __init__(self):
        self._agents: Dict[str, AgentInfo] = {}

    def _make_agent_id(self, name: str, tenant_id: str) -> str:
        return f"{tenant_id}:{name}" if tenant_id else name

    def update_from_resource(self, attributes: Dict[str, Any], signal: str) -> None:
        name = (
            attributes.get("service.name")
            or attributes.get("host.name")
            or attributes.get("service.instance.id")
            or "otel-agent"
        )
        host_name = attributes.get("host.name") or attributes.get("host.hostname")
        tenant_id = attributes.get("tenant_id") or attributes.get("tenant.id") or "default"
        agent_id = self._make_agent_id(str(name), str(tenant_id))

        info = self._agents.get(agent_id)
        if not info:
            info = AgentInfo(
                id=agent_id,
                name=str(name),
                tenant_id=str(tenant_id),
                host_name=str(host_name) if host_name else None,
                last_seen=datetime.now(timezone.utc),
                signals=[signal] if signal else [],
                attributes={k: str(v) for k, v in attributes.items() if v is not None}
            )
        else:
            info.last_seen = datetime.now(timezone.utc)
            if host_name:
                info.host_name = str(host_name)
            if signal and signal not in info.signals:
                info.signals.append(signal)
        self._agents[agent_id] = info

    def update_from_heartbeat(self, heartbeat: AgentHeartbeat) -> None:
        ts = heartbeat.timestamp or datetime.now(timezone.utc)
        agent_id = self._make_agent_id(heartbeat.name, heartbeat.tenant_id)
        host_name = (heartbeat.attributes or {}).get("host.name") or (heartbeat.attributes or {}).get("host.hostname")
        info = self._agents.get(agent_id)
        if not info:
            info = AgentInfo(
                id=agent_id,
                name=heartbeat.name,
                tenant_id=heartbeat.tenant_id,
                host_name=str(host_name) if host_name else None,
                last_seen=ts,
                signals=[heartbeat.signal] if heartbeat.signal else [],
                attributes=heartbeat.attributes or {}
            )
        else:
            info.last_seen = ts
            if host_name:
                info.host_name = str(host_name)
            if heartbeat.signal and heartbeat.signal not in info.signals:
                info.signals.append(heartbeat.signal)
        self._agents[agent_id] = info

    def list_agents(self) -> List[AgentInfo]:
        return sorted(self._agents.values(), key=lambda a: a.last_seen, reverse=True)
