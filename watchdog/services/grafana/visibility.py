"""
Visibility resolution for Grafana services.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the
License. You may obtain a copy of the License at
http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

from typing import List, Optional, Protocol

from sqlalchemy.orm import Session

from db_models import Group


class _GroupVisibilityService(Protocol):
    def validate_group_visibility(
        self,
        db: Session,
        *,
        user_id: str,
        tenant_id: str,
        group_ids: List[str],
        shared_group_ids: Optional[List[str]],
        is_admin: bool,
    ) -> List[Group]: ...


def resolve_visibility_groups(
    service: _GroupVisibilityService,
    db: Session,
    user_id: str,
    tenant_id: str,
    visibility: str,
    group_ids: List[str],
    shared_group_ids: Optional[List[str]],
    is_admin: bool,
) -> List[Group]:
    if visibility != "group":
        return []
    return service.validate_group_visibility(
        db,
        user_id=user_id,
        tenant_id=tenant_id,
        group_ids=group_ids,
        shared_group_ids=shared_group_ids,
        is_admin=is_admin,
    )
