"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");

you may not use this file except in compliance with the License.

You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from typing import List, Optional, Tuple

from models.alerting.rules import AlertRule, AlertRuleCreate
from db_models import AlertRule as AlertRuleDB


class RuleStorageService:
    def __init__(self, backend):
        self._backend = backend

    def get_public_alert_rules(self, tenant_id: str) -> List[AlertRule]:
        return self._backend.get_public_alert_rules(tenant_id)

    def get_alert_rules(
        self,
        tenant_id: str,
        user_id: str,
        group_ids: Optional[List[str]] = None,
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> List[AlertRule]:
        return self._backend.get_alert_rules(tenant_id, user_id, group_ids=group_ids, limit=limit, offset=offset)

    def get_alert_rules_for_org(self, tenant_id: str, org_id: str) -> List[AlertRule]:
        return self._backend.get_alert_rules_for_org(tenant_id, org_id)

    def get_alert_rules_with_owner(
        self,
        tenant_id: str,
        user_id: str,
        group_ids: Optional[List[str]] = None,
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> List[Tuple[AlertRule, str]]:
        return self._backend.get_alert_rules_with_owner(tenant_id, user_id, group_ids=group_ids, limit=limit, offset=offset)

    def get_alert_rule_raw(self, rule_id: str, tenant_id: str) -> Optional[AlertRuleDB]:
        return self._backend.get_alert_rule_raw(rule_id, tenant_id)

    def get_alert_rule(
        self,
        rule_id: str,
        tenant_id: str,
        user_id: str,
        group_ids: Optional[List[str]] = None,
    ) -> Optional[AlertRule]:
        return self._backend.get_alert_rule(rule_id, tenant_id, user_id, group_ids=group_ids)

    def create_alert_rule(
        self,
        rule_create: AlertRuleCreate,
        tenant_id: str,
        user_id: str,
        group_ids: Optional[List[str]] = None,
    ) -> AlertRule:
        return self._backend.create_alert_rule(rule_create, tenant_id, user_id, group_ids=group_ids)

    def update_alert_rule(
        self,
        rule_id: str,
        rule_update: AlertRuleCreate,
        tenant_id: str,
        user_id: str,
        group_ids: Optional[List[str]] = None,
    ) -> Optional[AlertRule]:
        return self._backend.update_alert_rule(rule_id, rule_update, tenant_id, user_id, group_ids=group_ids)

    def delete_alert_rule(
        self,
        rule_id: str,
        tenant_id: str,
        user_id: str,
        group_ids: Optional[List[str]] = None,
    ) -> bool:
        return self._backend.delete_alert_rule(rule_id, tenant_id, user_id, group_ids=group_ids)