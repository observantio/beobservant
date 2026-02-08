"""Router modules."""
from . import tempo_router
from . import loki_router
from . import alertmanager_router
from . import grafana_router
from . import auth_router

__all__ = [
    "tempo_router",
    "loki_router",
    "alertmanager_router",
    "grafana_router",
    "auth_router",
]
