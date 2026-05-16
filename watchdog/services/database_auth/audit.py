"""
Database for log and audit utilities for the database authentication service, providing functions to log audit events
related to authentication operations such as user creation, group management, and MFA changes. This module defines a
common interface for logging audit events in the database, allowing for consistent tracking of important actions and
changes within the authentication service while ensuring that relevant information is captured for auditing purposes.
Copyright (c) 2026 Stefan Kumarasinghe.

Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the
License. You may obtain a copy of the License at
http://www.apache.org/licenses/LICENSE-2.0
"""

import json
from dataclasses import dataclass

from sqlalchemy.orm import Session

from custom_types.json import JSONDict
from db_models import AuditLog
from services.audit_context import get_request_audit_context


@dataclass(frozen=True, slots=True)
class AuditLogRecord:
    tenant_id: str
    user_id: str
    action: str
    resource_type: str
    resource_id: str
    details: JSONDict
    ip_address: str | None = None
    user_agent: str | None = None


def log_audit(db: Session, record: AuditLogRecord) -> None:
    json.dumps(record.details)
    ctx_ip: str | None = None
    ctx_user_agent: str | None = None
    if record.ip_address is None or record.user_agent is None:
        ctx_ip, ctx_user_agent = get_request_audit_context()

    db.add(
        AuditLog(
            tenant_id=record.tenant_id,
            user_id=record.user_id,
            action=record.action,
            resource_type=record.resource_type,
            resource_id=record.resource_id,
            details=record.details,
            ip_address=record.ip_address if record.ip_address is not None else ctx_ip,
            user_agent=record.user_agent if record.user_agent is not None else ctx_user_agent,
        )
    )
