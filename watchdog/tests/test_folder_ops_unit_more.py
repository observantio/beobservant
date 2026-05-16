"""
Copyright (c) 2026 Stefan Kumarasinghe.

Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the
License. You may obtain a copy of the License at
http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from tests._env import ensure_test_env

ensure_test_env()

from db_models import Base, GrafanaFolder, Group, Tenant, User
from models.grafana.grafana_folder_models import Folder
from services.grafana import folder_ops
from services.grafana.grafana_bundles import (
    FolderAccessCriteria,
    FolderCreateOptions,
    FolderCreateRequest,
    FolderDeleteOptions,
    FolderDeleteRequest,
    FolderGetParams,
    FolderGetRequest,
    FolderListParams,
    FolderUpdateOptions,
    FolderUpdateRequest,
    GrafanaUserScope,
    HiddenToggleParams,
)
from services.grafana.grafana_service import GrafanaAPIError


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _seed(db):
    tenant = Tenant(id="t1", name="tenant-1", display_name="Tenant 1", is_active=True)
    owner = User(
        id="u1",
        tenant_id="t1",
        username="owner",
        email="owner@example.com",
        hashed_password="x",
        org_id="org-1",
        is_active=True,
    )
    viewer = User(
        id="u2",
        tenant_id="t1",
        username="viewer",
        email="viewer@example.com",
        hashed_password="x",
        org_id="org-2",
        is_active=True,
    )
    outsider = User(
        id="u3",
        tenant_id="t1",
        username="outsider",
        email="outsider@example.com",
        hashed_password="x",
        org_id="org-3",
        is_active=True,
    )
    group = Group(id="g1", tenant_id="t1", name="Ops", is_active=True)

    private_folder = GrafanaFolder(
        id="db-private",
        tenant_id="t1",
        created_by="u1",
        grafana_uid="f-private",
        grafana_id=10,
        title="Private",
        visibility="private",
        hidden_by=[],
    )
    tenant_folder = GrafanaFolder(
        id="db-tenant",
        tenant_id="t1",
        created_by="u1",
        grafana_uid="f-tenant",
        grafana_id=11,
        title="Tenant",
        visibility="tenant",
        hidden_by=[],
    )
    group_folder = GrafanaFolder(
        id="db-group",
        tenant_id="t1",
        created_by="u1",
        grafana_uid="f-group",
        grafana_id=12,
        title="Group",
        visibility="group",
        hidden_by=[],
        allow_dashboard_writes=True,
    )
    hidden_folder = GrafanaFolder(
        id="db-hidden",
        tenant_id="t1",
        created_by="u1",
        grafana_uid="f-hidden",
        grafana_id=13,
        title="Hidden",
        visibility="tenant",
        hidden_by=["u2"],
    )
    group_folder.shared_groups.append(group)

    db.add_all([tenant, owner, viewer, outsider, group, private_folder, tenant_folder, group_folder, hidden_folder])
    db.commit()
    return owner, viewer, outsider, group, private_folder, tenant_folder, group_folder, hidden_folder


class GrafanaServiceStub:
    def __init__(self):
        self.folders = []
        self.folder_by_uid = {}
        self.created = None
        self.updated = None
        self.deleted = True
        self.create_error = None
        self.update_error = None
        self.delete_error = None
        self.calls = []

    async def get_folders(self):
        return list(self.folders)

    async def get_folder(self, uid):
        self.calls.append(("get", uid))
        return self.folder_by_uid.get(uid)

    async def create_folder(self, title):
        self.calls.append(("create", title))
        if self.create_error is not None:
            raise self.create_error
        return self.created

    async def update_folder(self, uid, title):
        self.calls.append(("update", uid, title))
        if self.update_error is not None:
            raise self.update_error
        return self.updated

    async def delete_folder(self, uid):
        self.calls.append(("delete", uid))
        if self.delete_error is not None:
            raise self.delete_error
        return self.deleted


class ProxyStub:
    def __init__(self, grafana_service):
        self.grafana_service = grafana_service
        self.visibility_calls = []
        self.raised_errors = []

        def raise_http_from_grafana_error(exc: Exception) -> None:
            self.raised_errors.append(exc)
            status = getattr(exc, "status", 502)
            raise HTTPException(status_code=status, detail=str(exc)) from exc

        self.raise_http_from_grafana_error = raise_http_from_grafana_error

    def validate_group_visibility(self, db, validation):
        self.visibility_calls.append(list(validation.shared_group_ids or []))
        return db.query(Group).filter(Group.id.in_(validation.shared_group_ids or [])).all()


def test_folder_helpers_cover_access_and_payload_branches():
    db = _session()
    owner, viewer, _outsider, group, private_folder, tenant_folder, group_folder, hidden_folder = _seed(db)

    assert folder_ops._db_folder_by_uid(db, "t1", "f-private").id == private_folder.id
    v_scope = GrafanaUserScope(viewer.id, "t1", [])
    v_group_scope = GrafanaUserScope(viewer.id, "t1", [group.id])
    assert folder_ops.check_folder_access(db, "missing", v_scope, FolderAccessCriteria()) is None
    assert folder_ops.check_folder_access(db, hidden_folder.grafana_uid, v_scope, FolderAccessCriteria()) is None
    assert (
        folder_ops.check_folder_access(
            db,
            hidden_folder.grafana_uid,
            v_scope,
            FolderAccessCriteria(include_hidden=True),
        ).id
        == hidden_folder.id
    )
    assert (
        folder_ops.check_folder_access(
            db,
            private_folder.grafana_uid,
            v_scope,
            FolderAccessCriteria(require_write=True),
        )
        is None
    )
    assert (
        folder_ops.check_folder_access(db, tenant_folder.grafana_uid, v_scope, FolderAccessCriteria()).id
        == tenant_folder.id
    )
    assert (
        folder_ops.check_folder_access(db, group_folder.grafana_uid, v_group_scope, FolderAccessCriteria()).id
        == group_folder.id
    )
    assert folder_ops.check_folder_access(db, group_folder.grafana_uid, v_scope, FolderAccessCriteria()) is None

    assert folder_ops.is_folder_accessible(db, None, v_scope, FolderAccessCriteria()) is True
    assert folder_ops.is_folder_accessible(db, "missing", v_scope, FolderAccessCriteria()) is False

    model_payload = folder_ops._folder_payload(
        Folder(id=99, uid="model", title="Model Folder"),
        db_folder=group_folder,
        user_id=viewer.id,
    )
    assert model_payload["sharedGroupIds"] == [group.id]
    assert model_payload["allowDashboardWrites"] is True

    dict_payload = folder_ops._folder_payload(
        {"uid": "dict", "title": "Dict Folder"}, db_folder=None, user_id=viewer.id
    )
    assert dict_payload["visibility"] == "tenant"
    assert dict_payload["is_owned"] is False

    obj_payload = folder_ops._folder_payload(
        SimpleNamespace(uid="obj", title="Object Folder"), db_folder=tenant_folder, user_id=owner.id
    )
    assert obj_payload["created_by"] == owner.id
    assert obj_payload["is_owned"] is True


@pytest.mark.asyncio
async def test_get_folder_and_get_folders_cover_missing_branches():
    db = _session()
    _owner, viewer, _outsider, _group, _private_folder, _tenant_folder, _group_folder, _hidden_folder = _seed(db)
    stub = GrafanaServiceStub()
    stub.folders = [
        SimpleNamespace(id=11, uid="f-tenant", title="Tenant"),
        SimpleNamespace(id=77, uid="f-no-db", title="Orphan"),
    ]
    stub.folder_by_uid = {
        "f-tenant": None,
        "f-private": SimpleNamespace(id=10, uid="f-private", title="Private"),
    }
    service = ProxyStub(stub)

    folders = await folder_ops.get_folders(service, db, GrafanaUserScope(viewer.id, "t1", []), FolderListParams())
    assert [folder.uid for folder in folders] == ["f-tenant"]

    gfs = FolderGetParams()
    assert (
        await folder_ops.get_folder(
            service,
            db,
            FolderGetRequest(uid="missing", scope=GrafanaUserScope(viewer.id, "t1", []), params=gfs),
        )
        is None
    )
    assert (
        await folder_ops.get_folder(
            service,
            db,
            FolderGetRequest(uid="f-private", scope=GrafanaUserScope(viewer.id, "t1", []), params=gfs),
        )
        is None
    )
    assert (
        await folder_ops.get_folder(
            service,
            db,
            FolderGetRequest(uid="f-tenant", scope=GrafanaUserScope(viewer.id, "t1", []), params=gfs),
        )
        is None
    )


@pytest.mark.asyncio
async def test_create_folder_covers_group_and_no_uid_paths():
    db = _session()
    _owner, viewer, _outsider, group, _private_folder, _tenant_folder, _group_folder, _hidden_folder = _seed(db)
    stub = GrafanaServiceStub()
    service = ProxyStub(stub)

    stub.created = SimpleNamespace(id=20, uid="f-created", title="Created Group")
    created = await folder_ops.create_folder(
        service,
        db,
        FolderCreateRequest(
            title="Created Group",
            scope=GrafanaUserScope(viewer.id, "t1", [group.id]),
            options=FolderCreateOptions(
                visibility="group",
                shared_group_ids=[group.id],
                allow_dashboard_writes=True,
                is_admin=False,
            ),
        ),
    )
    assert created is not None
    assert created.shared_group_ids == [group.id]
    db_row = db.query(GrafanaFolder).filter_by(grafana_uid="f-created").first()
    assert db_row is not None
    assert db_row.allow_dashboard_writes is True
    assert [g.id for g in db_row.shared_groups] == [group.id]
    assert service.visibility_calls[-1] == [group.id]

    stub.created = {"id": 21, "uid": "", "title": "Loose Folder"}
    loose = await folder_ops.create_folder(
        service,
        db,
        FolderCreateRequest(
            title="Loose Folder",
            scope=GrafanaUserScope(viewer.id, "t1", []),
            options=FolderCreateOptions(),
        ),
    )
    assert loose is not None
    assert loose.title == "Loose Folder"
    assert db.query(GrafanaFolder).filter_by(title="Loose Folder").first() is None

    stub.created = None
    assert (
        await folder_ops.create_folder(
            service,
            db,
            FolderCreateRequest(
                title="Nothing",
                scope=GrafanaUserScope(viewer.id, "t1", []),
                options=FolderCreateOptions(),
            ),
        )
        is None
    )


@pytest.mark.asyncio
async def test_update_folder_covers_none_error_and_group_visibility_paths():
    db = _session()
    owner, viewer, _outsider, group, _private_folder, _tenant_folder, group_folder, _hidden_folder = _seed(db)
    stub = GrafanaServiceStub()
    service = ProxyStub(stub)

    o_scope = GrafanaUserScope(owner.id, "t1", [])
    o_g_scope = GrafanaUserScope(owner.id, "t1", [group.id])
    v_g_scope = GrafanaUserScope(viewer.id, "t1", [group.id])
    assert (
        await folder_ops.update_folder(
            service,
            db,
            FolderUpdateRequest(uid="missing", scope=o_scope, options=FolderUpdateOptions()),
        )
        is None
    )
    assert (
        await folder_ops.update_folder(
            service,
            db,
            FolderUpdateRequest(uid=group_folder.grafana_uid, scope=v_g_scope, options=FolderUpdateOptions()),
        )
        is None
    )

    stub.updated = None
    assert (
        await folder_ops.update_folder(
            service,
            db,
            FolderUpdateRequest(uid=group_folder.grafana_uid, scope=o_g_scope, options=FolderUpdateOptions()),
        )
        is None
    )

    stub.update_error = GrafanaAPIError(500, {"message": "boom"})
    with pytest.raises(HTTPException) as exc:
        await folder_ops.update_folder(
            service,
            db,
            FolderUpdateRequest(uid=group_folder.grafana_uid, scope=o_g_scope, options=FolderUpdateOptions()),
        )
    assert exc.value.status_code == 500
    stub.update_error = None

    stub.updated = SimpleNamespace(id=12, uid=group_folder.grafana_uid, title="Grouped Updated")
    updated = await folder_ops.update_folder(
        service,
        db,
        FolderUpdateRequest(
            uid=group_folder.grafana_uid,
            scope=o_g_scope,
            options=FolderUpdateOptions(
                title="Grouped Updated",
                visibility="group",
                shared_group_ids=[group.id],
                allow_dashboard_writes=False,
                is_admin=False,
            ),
        ),
    )
    assert updated is not None
    refreshed = db.query(GrafanaFolder).filter_by(grafana_uid=group_folder.grafana_uid).first()
    assert refreshed.title == "Grouped Updated"
    assert refreshed.allow_dashboard_writes is False
    assert [g.id for g in refreshed.shared_groups] == [group.id]

    stub.updated = SimpleNamespace(id=12, uid=group_folder.grafana_uid, title="Tenant Again")
    updated = await folder_ops.update_folder(
        service,
        db,
        FolderUpdateRequest(
            uid=group_folder.grafana_uid,
            scope=o_g_scope,
            options=FolderUpdateOptions(visibility="tenant"),
        ),
    )
    assert updated is not None
    refreshed = db.query(GrafanaFolder).filter_by(grafana_uid=group_folder.grafana_uid).first()
    assert refreshed.visibility == "tenant"
    assert refreshed.shared_groups == []


@pytest.mark.asyncio
async def test_delete_and_toggle_folder_cover_remaining_paths():
    db = _session()
    owner, viewer, _outsider, _group, _private_folder, tenant_folder, group_folder, _hidden_folder = _seed(db)
    stub = GrafanaServiceStub()
    service = ProxyStub(stub)
    o_scope = GrafanaUserScope(owner.id, "t1", [])

    assert (
        await folder_ops.delete_folder(
            service,
            db,
            FolderDeleteRequest(uid="missing", scope=o_scope, options=FolderDeleteOptions(is_admin=False)),
        )
        is False
    )
    assert (
        await folder_ops.delete_folder(
            service,
            db,
            FolderDeleteRequest(
                uid=tenant_folder.grafana_uid,
                scope=GrafanaUserScope(viewer.id, "t1", []),
                options=FolderDeleteOptions(is_admin=False),
            ),
        )
        is False
    )

    stub.delete_error = httpx.ConnectError("down")
    with pytest.raises(HTTPException) as exc:
        await folder_ops.delete_folder(
            service,
            db,
            FolderDeleteRequest(
                uid=tenant_folder.grafana_uid,
                scope=o_scope,
                options=FolderDeleteOptions(is_admin=False),
            ),
        )
    assert exc.value.status_code == 502
    stub.delete_error = None

    stub.deleted = False
    assert (
        await folder_ops.delete_folder(
            service,
            db,
            FolderDeleteRequest(
                uid=tenant_folder.grafana_uid,
                scope=o_scope,
                options=FolderDeleteOptions(is_admin=False),
            ),
        )
        is False
    )

    stub.deleted = True
    assert (
        await folder_ops.delete_folder(
            service,
            db,
            FolderDeleteRequest(
                uid=tenant_folder.grafana_uid,
                scope=o_scope,
                options=FolderDeleteOptions(is_admin=False),
            ),
        )
        is True
    )
    assert db.query(GrafanaFolder).filter_by(grafana_uid=tenant_folder.grafana_uid).first() is None

    viewer_scope = GrafanaUserScope(viewer.id, "t1", [])
    assert folder_ops.toggle_folder_hidden(db, "missing", viewer_scope, HiddenToggleParams(hidden=True)) is False
    assert (
        folder_ops.toggle_folder_hidden(
            db,
            group_folder.grafana_uid,
            viewer_scope,
            HiddenToggleParams(hidden=True),
        )
        is True
    )
    assert viewer.id in db.query(GrafanaFolder).filter_by(grafana_uid=group_folder.grafana_uid).first().hidden_by
    assert (
        folder_ops.toggle_folder_hidden(
            db,
            group_folder.grafana_uid,
            viewer_scope,
            HiddenToggleParams(hidden=False),
        )
        is True
    )
    assert viewer.id not in db.query(GrafanaFolder).filter_by(grafana_uid=group_folder.grafana_uid).first().hidden_by
