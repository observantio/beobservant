"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");

you may not use this file except in compliance with the License.

You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""
from typing import Any, Dict, List, Optional
from models.alerting.channels import NotificationChannel, NotificationChannelCreate

class ChannelStorageService:
    def __init__(self, backend):
        self._backend = backend

    def get_notification_channels(
        self,
        tenant_id: str,
        user_id: str,
        group_ids: Optional[List[str]] = None,
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> List[NotificationChannel]:
        return self._backend.get_notification_channels(tenant_id, user_id, group_ids=group_ids, limit=limit, offset=offset)

    def get_notification_channel(
        self,
        channel_id: str,
        tenant_id: str,
        user_id: str,
        group_ids: Optional[List[str]] = None,
    ) -> Optional[NotificationChannel]:
        return self._backend.get_notification_channel(channel_id, tenant_id, user_id, group_ids=group_ids)

    def create_notification_channel(
        self,
        channel_create: NotificationChannelCreate,
        tenant_id: str,
        user_id: str,
        group_ids: Optional[List[str]] = None,
    ) -> NotificationChannel:
        return self._backend.create_notification_channel(channel_create, tenant_id, user_id, group_ids=group_ids)

    def update_notification_channel(
        self,
        channel_id: str,
        channel_update: NotificationChannelCreate,
        tenant_id: str,
        user_id: str,
        group_ids: Optional[List[str]] = None,
    ) -> Optional[NotificationChannel]:
        return self._backend.update_notification_channel(channel_id, channel_update, tenant_id, user_id, group_ids=group_ids)

    def delete_notification_channel(
        self,
        channel_id: str,
        tenant_id: str,
        user_id: str,
        group_ids: Optional[List[str]] = None,
    ) -> bool:
        return self._backend.delete_notification_channel(channel_id, tenant_id, user_id, group_ids=group_ids)

    def is_notification_channel_owner(self, channel_id: str, tenant_id: str, user_id: str) -> bool:
        return self._backend.is_notification_channel_owner(channel_id, tenant_id, user_id)

    def test_notification_channel(
        self,
        channel_id: str,
        tenant_id: str,
        user_id: str,
        group_ids: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        return self._backend.test_notification_channel(channel_id, tenant_id, user_id, group_ids=group_ids)

    def get_notification_channels_for_rule_name(self, rule_name: str) -> List[NotificationChannel]:
        return self._backend.get_notification_channels_for_rule_name(rule_name)
