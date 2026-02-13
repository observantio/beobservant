import logging
from datetime import datetime, timezone
from typing import Dict, List

from models.observability.agent_models import AgentHeartbeat, AgentInfo

logger = logging.getLogger(__name__)


class AgentService:
    """In-memory registry of recently active OTLP agents."""
    
    ATTR_HOST_NAME = "host.name"
    ATTR_HOST_HOSTNAME = "host.hostname"

    def __init__(self):
        self._agents: Dict[str, AgentInfo] = {}

    def _make_agent_id(self, name: str, tenant_id: str) -> str:
        return f"{tenant_id}:{name}" if tenant_id else name

    def update_from_heartbeat(self, heartbeat: AgentHeartbeat) -> None:
        ts = heartbeat.timestamp or datetime.now(timezone.utc)
        agent_id = self._make_agent_id(heartbeat.name, heartbeat.tenant_id)
        attributes = heartbeat.attributes or {}
        host_name = attributes.get(self.ATTR_HOST_NAME) or attributes.get(self.ATTR_HOST_HOSTNAME)
        info = self._agents.get(agent_id)
        if not info:
            info = AgentInfo(
                id=agent_id,
                name=heartbeat.name,
                tenant_id=heartbeat.tenant_id,
                host_name=str(host_name) if host_name else None,
                last_seen=ts,
                signals=[heartbeat.signal] if heartbeat.signal else [],
                attributes=attributes
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
