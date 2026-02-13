"""Router modules."""
from .observability import tempo_router
from .observability import loki_router
from .observability import alertmanager_router
from .observability import grafana_router
from .access import auth_router
from .observability import agents_router
from .platform import system_router
from .platform import gateway_router

__all__ = [
    "tempo_router",
    "loki_router",
    "alertmanager_router",
    "grafana_router",
    "auth_router",
    "agents_router",
    "system_router",
    "gateway_router",
]
