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
from services.grafana.grafana_bundles import (
    GrafanaUserScope,
    GroupVisibilityShareChange,
    GroupVisibilityValidation,
    VisibilityGroupResolveContext,
)


class _GroupVisibilityService(Protocol):
    def validate_group_visibility(self, db: Session, validation: GroupVisibilityValidation) -> List[Group]: ...


def resolve_visibility_groups_for_scope(
    service: _GroupVisibilityService,
    db: Session,
    ctx: VisibilityGroupResolveContext,
) -> List[Group]:
    return resolve_visibility_groups(
        service,
        db,
        ctx,
    )


def resolve_visibility_groups(
    service: _GroupVisibilityService,
    db: Session,
    ctx: VisibilityGroupResolveContext,
) -> List[Group]:
    if ctx.visibility != "group":
        return []
    return service.validate_group_visibility(
        db,
        GroupVisibilityValidation(
            user_id=ctx.user_id,
            tenant_id=ctx.tenant_id,
            group_ids=ctx.group_ids,
            shared_group_ids=ctx.shared_group_ids,
            is_admin=ctx.is_admin,
        ),
    )


def resolve_group_share_on_visibility_change(
    service: _GroupVisibilityService,
    db: Session,
    spec: GroupVisibilityShareChange,
) -> List[Group]:
    if spec.visibility != "group" or spec.shared_group_ids is None:
        return []
    return service.validate_group_visibility(
        db,
        GroupVisibilityValidation(
            user_id=spec.user_id,
            tenant_id=spec.tenant_id,
            group_ids=spec.group_ids,
            shared_group_ids=spec.shared_group_ids,
            is_admin=spec.is_admin,
        ),
    )


def visibility_group_resolve_context(
    scope: GrafanaUserScope,
    *,
    visibility: str,
    shared_group_ids: Optional[List[str]],
    is_admin: bool,
) -> VisibilityGroupResolveContext:
    return VisibilityGroupResolveContext(
        user_id=scope.user_id,
        tenant_id=scope.tenant_id,
        visibility=visibility,
        group_ids=scope.group_ids,
        shared_group_ids=shared_group_ids,
        is_admin=is_admin,
    )


def group_share_change_for_scope(
    scope: GrafanaUserScope,
    *,
    visibility: str,
    shared_group_ids: Optional[List[str]],
    is_admin: bool,
) -> GroupVisibilityShareChange:
    return GroupVisibilityShareChange(
        visibility=visibility,
        shared_group_ids=shared_group_ids,
        user_id=scope.user_id,
        tenant_id=scope.tenant_id,
        group_ids=scope.group_ids,
        is_admin=is_admin,
    )
