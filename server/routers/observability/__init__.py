"""Observability-related API routers."""

from . import agents_router
from . import alertmanager_router
from . import grafana_router
from . import loki_router
from . import tempo_router

__all__ = [
	"agents_router",
	"alertmanager_router",
	"grafana_router",
	"loki_router",
	"tempo_router",
]

