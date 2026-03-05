"""
Shared router state and helpers for access/auth routes.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter
from fastapi.concurrency import run_in_threadpool

from services.notification_service import NotificationService

logger = logging.getLogger(__name__)

USER_NOT_FOUND = "User not found"
GROUP_NOT_FOUND = "Group not found"

router = APIRouter(prefix="/api/auth", tags=["authentication"])
notification_service = NotificationService()
rtp = run_in_threadpool
