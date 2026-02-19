"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");

you may not use this file except in compliance with the License.

You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from services.storage_db_service import DatabaseStorageService as LegacyDatabaseStorageService
from services.storage.incidents import IncidentStorageService
from services.storage.rules import RuleStorageService
from services.storage.channels import ChannelStorageService


class DatabaseStorageService:
    """Facade split by domain modules (incidents/rules/channels).

    Keeps backward-compatible method names while delegating to domain services.
    """

    def __init__(self) -> None:
        self._backend = LegacyDatabaseStorageService()
        self.incidents = IncidentStorageService(self._backend)
        self.rules = RuleStorageService(self._backend)
        self.channels = ChannelStorageService(self._backend)

    def __getattr__(self, item):
        return getattr(self._backend, item)

    def sync_incidents_from_alerts(self, tenant_id, alerts, resolve_missing=True):
        return self.incidents.sync_incidents_from_alerts(tenant_id, alerts, resolve_missing)

    def list_incidents(self, tenant_id, user_id, group_ids=None, status=None, visibility=None, group_id=None, limit=None, offset=0):
        return self.incidents.list_incidents(
            tenant_id,
            user_id,
            group_ids=group_ids,
            status=status,
            visibility=visibility,
            group_id=group_id,
            limit=limit,
            offset=offset,
        )

    def get_incident_for_user(self, incident_id, tenant_id, user_id=None, group_ids=None, require_write=False):
        return self.incidents.get_incident_for_user(
            incident_id,
            tenant_id,
            user_id=user_id,
            group_ids=group_ids,
            require_write=require_write,
        )

    def update_incident(self, incident_id, tenant_id, user_id, payload):
        return self.incidents.update_incident(incident_id, tenant_id, user_id, payload)

    def filter_alerts_for_user(self, tenant_id, user_id, group_ids, alerts):
        return self.incidents.filter_alerts_for_user(tenant_id, user_id, group_ids, alerts)

    # Rules domain
    def get_public_alert_rules(self, tenant_id):
        return self.rules.get_public_alert_rules(tenant_id)

    def get_alert_rules(self, tenant_id, user_id, group_ids=None, limit=None, offset=0):
        return self.rules.get_alert_rules(tenant_id, user_id, group_ids=group_ids, limit=limit, offset=offset)

    def get_alert_rules_for_org(self, tenant_id, org_id):
        return self.rules.get_alert_rules_for_org(tenant_id, org_id)

    def get_alert_rules_with_owner(self, tenant_id, user_id, group_ids=None, limit=None, offset=0):
        return self.rules.get_alert_rules_with_owner(tenant_id, user_id, group_ids=group_ids, limit=limit, offset=offset)

    def get_alert_rule_raw(self, rule_id, tenant_id):
        return self.rules.get_alert_rule_raw(rule_id, tenant_id)

    def get_alert_rule(self, rule_id, tenant_id, user_id, group_ids=None):
        return self.rules.get_alert_rule(rule_id, tenant_id, user_id, group_ids=group_ids)

    def create_alert_rule(self, rule_create, tenant_id, user_id, group_ids=None):
        return self.rules.create_alert_rule(rule_create, tenant_id, user_id, group_ids=group_ids)

    def update_alert_rule(self, rule_id, rule_update, tenant_id, user_id, group_ids=None):
        return self.rules.update_alert_rule(rule_id, rule_update, tenant_id, user_id, group_ids=group_ids)

    def delete_alert_rule(self, rule_id, tenant_id, user_id, group_ids=None):
        return self.rules.delete_alert_rule(rule_id, tenant_id, user_id, group_ids=group_ids)

    # Channels domain
    def get_notification_channels(self, tenant_id, user_id, group_ids=None, limit=None, offset=0):
        return self.channels.get_notification_channels(tenant_id, user_id, group_ids=group_ids, limit=limit, offset=offset)

    def get_notification_channel(self, channel_id, tenant_id, user_id, group_ids=None):
        return self.channels.get_notification_channel(channel_id, tenant_id, user_id, group_ids=group_ids)

    def create_notification_channel(self, channel_create, tenant_id, user_id, group_ids=None):
        return self.channels.create_notification_channel(channel_create, tenant_id, user_id, group_ids=group_ids)

    def update_notification_channel(self, channel_id, channel_update, tenant_id, user_id, group_ids=None):
        return self.channels.update_notification_channel(channel_id, channel_update, tenant_id, user_id, group_ids=group_ids)

    def delete_notification_channel(self, channel_id, tenant_id, user_id, group_ids=None):
        return self.channels.delete_notification_channel(channel_id, tenant_id, user_id, group_ids=group_ids)

    def is_notification_channel_owner(self, channel_id, tenant_id, user_id):
        return self.channels.is_notification_channel_owner(channel_id, tenant_id, user_id)

    def test_notification_channel(self, channel_id, tenant_id, user_id, group_ids=None):
        return self.channels.test_notification_channel(channel_id, tenant_id, user_id, group_ids=group_ids)

    def get_notification_channels_for_rule_name(self, rule_name):
        return self.channels.get_notification_channels_for_rule_name(rule_name)
