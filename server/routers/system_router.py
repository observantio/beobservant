from fastapi import APIRouter, Depends, HTTPException, status
from typing import Dict, Any
import logging

from services.system_service import SystemService
from models.auth_models import Permission, TokenData
from routers.auth_router import require_permission
from middleware.rate_limit import enforce_rate_limit
from config import config

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/system", tags=["system"])
system_service = SystemService()


@router.get("/metrics", response_model=Dict[str, Any])
async def get_system_metrics(
    current_user: TokenData = Depends(require_permission(Permission.READ_AGENTS))
) -> Dict[str, Any]:
    """
    Get system metrics including CPU, memory, disk, network utilization and stress status.
    Requires READ_AGENTS permission.
    """
    enforce_rate_limit(key=f"user:{current_user.user_id}:system", limit=config.RATE_LIMIT_USER_PER_MINUTE, window_seconds=60)
    try:
        return system_service.get_all_metrics()
    except Exception as e:
        logger.error("Error fetching system metrics: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve system metrics",
        )
