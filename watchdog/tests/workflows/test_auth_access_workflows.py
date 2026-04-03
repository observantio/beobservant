"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from routers import internal_router
from routers.access.auth_router import authentication as auth_routes

from .helpers import WorkflowState, patch_auth_service


def test_registration_login_password_and_mfa_workflow(client, monkeypatch: pytest.MonkeyPatch) -> None:
    state = WorkflowState()
    patch_auth_service(monkeypatch, state)

    class FakeQuery:
        def filter_by(self, **_kwargs):
            return self

        def first(self):
            return SimpleNamespace(id=state.tenant_id)

    class FakeDB:
        def query(self, *_args):
            return FakeQuery()

    class FakeCtx:
        def __enter__(self):
            return FakeDB()

        def __exit__(self, exc_type, exc, tb):
            return False

    async def _send_welcome(**kwargs):
        del kwargs
        return True

    monkeypatch.setattr(auth_routes, "get_db_session", lambda: FakeCtx())
    monkeypatch.setattr(auth_routes.notification_service, "send_user_welcome_email", _send_welcome)

    mode_response = client.get("/api/auth/mode")
    assert mode_response.status_code == 200
    assert mode_response.json()["registration_enabled"] is True

    oidc_authorize_disabled = client.post(
        "/api/auth/oidc/authorize-url",
        json={"redirect_uri": "https://app.example.com/callback", "state": "state-1"},
    )
    assert oidc_authorize_disabled.status_code == 400

    oidc_exchange_disabled = client.post(
        "/api/auth/oidc/exchange",
        json={"code": "code-1", "redirect_uri": "https://app.example.com/callback"},
    )
    assert oidc_exchange_disabled.status_code == 400

    register_response = client.post(
        "/api/auth/register",
        json={
            "username": "alice",
            "email": "alice@example.com",
            "password": "password123",
            "full_name": "Alice Example",
        },
    )
    assert register_response.status_code == 200
    alice_id = register_response.json()["id"]

    login_response = client.post(
        "/api/auth/login",
        json={"username": "alice", "password": "password123"},
    )
    assert login_response.status_code == 200
    alice_token = login_response.json()["access_token"]

    me_response = client.get("/api/auth/me", headers=state.auth_header(alice_token))
    assert me_response.status_code == 200
    assert me_response.json()["username"] == "alice"

    update_me_response = client.put(
        "/api/auth/me",
        headers=state.auth_header(alice_token),
        json={"full_name": "Alice Updated", "email": "alice.updated@example.com"},
    )
    assert update_me_response.status_code == 200
    assert update_me_response.json()["full_name"] == "Alice Updated"

    change_password_response = client.put(
        f"/api/auth/users/{alice_id}/password",
        headers=state.auth_header(alice_token),
        json={"current_password": "password123", "new_password": "new-password-123"},
    )
    assert change_password_response.status_code == 200

    old_login_response = client.post(
        "/api/auth/login",
        json={"username": "alice", "password": "password123"},
    )
    assert old_login_response.status_code == 401

    new_login_response = client.post(
        "/api/auth/login",
        json={"username": "alice", "password": "new-password-123"},
    )
    assert new_login_response.status_code == 200
    refreshed_token = new_login_response.json()["access_token"]

    enroll_response = client.post(
        "/api/auth/mfa/enroll",
        headers=state.auth_header(refreshed_token),
    )
    assert enroll_response.status_code == 200

    verify_response = client.post(
        "/api/auth/mfa/verify",
        headers=state.auth_header(refreshed_token),
        json={"code": "123456"},
    )
    assert verify_response.status_code == 200

    login_requires_mfa = client.post(
        "/api/auth/login",
        json={"username": "alice", "password": "new-password-123"},
    )
    assert login_requires_mfa.status_code == 401
    assert login_requires_mfa.json()["detail"] == "MFA required"

    login_with_mfa = client.post(
        "/api/auth/login",
        json={"username": "alice", "password": "new-password-123", "mfa_code": "123456"},
    )
    assert login_with_mfa.status_code == 200
    mfa_token = login_with_mfa.json()["access_token"]

    disable_mfa_response = client.post(
        "/api/auth/mfa/disable",
        headers=state.auth_header(mfa_token),
        json={"current_password": "new-password-123", "code": "123456"},
    )
    assert disable_mfa_response.status_code == 200

    logout_response = client.post("/api/auth/logout", headers=state.auth_header(mfa_token))
    assert logout_response.status_code == 200


def test_user_group_role_and_permission_workflow(client, monkeypatch: pytest.MonkeyPatch) -> None:
    state = WorkflowState()
    patch_auth_service(monkeypatch, state)
    admin_headers = state.auth_header("token-u-admin")

    viewer_response = client.post(
        "/api/auth/users",
        headers=admin_headers,
        json={"username": "viewer1", "email": "viewer1@example.com", "password": "password123", "role": "viewer"},
    )
    assert viewer_response.status_code == 200
    viewer_id = viewer_response.json()["id"]

    worker_response = client.post(
        "/api/auth/users",
        headers=admin_headers,
        json={"username": "worker1", "email": "worker1@example.com", "password": "password123", "role": "user"},
    )
    assert worker_response.status_code == 200
    worker_id = worker_response.json()["id"]

    list_users_response = client.get("/api/auth/users", headers=admin_headers)
    assert list_users_response.status_code == 200
    assert {item["username"] for item in list_users_response.json()} >= {"admin", "viewer1", "worker1"}

    permissions_response = client.get("/api/auth/permissions", headers=admin_headers)
    assert permissions_response.status_code == 200
    assert any(item["name"] == "create:groups" for item in permissions_response.json())

    role_defaults_response = client.get("/api/auth/role-defaults", headers=admin_headers)
    assert role_defaults_response.status_code == 200
    assert "admin" in role_defaults_response.json()

    update_permissions_response = client.put(
        f"/api/auth/users/{worker_id}/permissions",
        headers=admin_headers,
        json=[
            "create:groups",
            "manage:groups",
            "update:group_members",
            "read:groups",
            "read:users",
            "read:logs",
            "read:traces",
        ],
    )
    assert update_permissions_response.status_code == 200

    update_role_response = client.put(
        f"/api/auth/users/{viewer_id}",
        headers=admin_headers,
        json={"username": "viewer2", "role": "user"},
    )
    assert update_role_response.status_code == 200
    assert update_role_response.json()["username"] == "viewer2"

    worker_group_response = client.post(
        "/api/auth/groups",
        headers=state.auth_header(f"token-{worker_id}"),
        json={"name": "ops-group", "description": "Ops team"},
    )
    assert worker_group_response.status_code == 200
    group_id = worker_group_response.json()["id"]

    get_group_response = client.get(
        f"/api/auth/groups/{group_id}",
        headers=state.auth_header(f"token-{worker_id}"),
    )
    assert get_group_response.status_code == 200

    update_group_response = client.put(
        f"/api/auth/groups/{group_id}",
        headers=state.auth_header(f"token-{worker_id}"),
        json={"description": "Ops team updated"},
    )
    assert update_group_response.status_code == 200

    update_group_permissions_response = client.put(
        f"/api/auth/groups/{group_id}/permissions",
        headers=state.auth_header(f"token-{worker_id}"),
        json=["read:logs", "read:traces"],
    )
    assert update_group_permissions_response.status_code == 200

    update_group_members_response = client.put(
        f"/api/auth/groups/{group_id}/members",
        headers=state.auth_header(f"token-{worker_id}"),
        json={"user_ids": [viewer_id]},
    )
    assert update_group_members_response.status_code == 200

    list_groups_response = client.get("/api/auth/groups", headers=state.auth_header(f"token-{worker_id}"))
    assert list_groups_response.status_code == 200
    assert list_groups_response.json()[0]["id"] == group_id

    temp_password_response = client.post(
        f"/api/auth/users/{viewer_id}/password/reset-temp",
        headers=admin_headers,
    )
    assert temp_password_response.status_code == 200
    assert temp_password_response.json()["temporary_password"] == "Temp-Password-123"

    reset_mfa_response = client.post(
        f"/api/auth/users/{viewer_id}/mfa/reset",
        headers=admin_headers,
    )
    assert reset_mfa_response.status_code == 200

    delete_group_response = client.delete(
        f"/api/auth/groups/{group_id}",
        headers=state.auth_header(f"token-{worker_id}"),
    )
    assert delete_group_response.status_code == 204

    delete_user_response = client.delete(f"/api/auth/users/{viewer_id}", headers=admin_headers)
    assert delete_user_response.status_code == 200


def test_auth_routes_reject_malformed_path_ids(client, monkeypatch: pytest.MonkeyPatch) -> None:
    state = WorkflowState()
    patch_auth_service(monkeypatch, state)
    admin_headers = state.auth_header("token-u-admin")

    invalid_user_id = "bad.user"
    invalid_key_id = "bad.key"
    invalid_shared_user_id = "bad:share"

    delete_user_response = client.delete(f"/api/auth/users/{invalid_user_id}", headers=admin_headers)
    assert delete_user_response.status_code == 422

    reset_mfa_response = client.post(
        f"/api/auth/users/{invalid_user_id}/mfa/reset",
        headers=admin_headers,
    )
    assert reset_mfa_response.status_code == 422

    temp_password_response = client.post(
        f"/api/auth/users/{invalid_user_id}/password/reset-temp",
        headers=admin_headers,
    )
    assert temp_password_response.status_code == 422

    update_key_response = client.patch(
        f"/api/auth/api-keys/{invalid_key_id}",
        headers=admin_headers,
        json={"name": "ignored"},
    )
    assert update_key_response.status_code == 422

    remove_share_response = client.delete(
        f"/api/auth/api-keys/{invalid_key_id}/shares/{invalid_shared_user_id}",
        headers=admin_headers,
    )
    assert remove_share_response.status_code == 422


def test_user_management_permission_boundaries_workflow(client, monkeypatch: pytest.MonkeyPatch) -> None:
    state = WorkflowState()
    patch_auth_service(monkeypatch, state)
    admin_headers = state.auth_header("token-u-admin")

    second_admin_response = client.post(
        "/api/auth/users",
        headers=admin_headers,
        json={
            "username": "admin2",
            "email": "admin2@example.com",
            "password": "password123",
            "role": "admin",
        },
    )
    assert second_admin_response.status_code == 200
    second_admin_id = second_admin_response.json()["id"]

    delete_admin_response = client.delete(
        f"/api/auth/users/{second_admin_id}",
        headers=admin_headers,
    )
    assert delete_admin_response.status_code == 403
    assert "cannot be deleted" in delete_admin_response.json()["detail"].lower()

    operator_response = client.post(
        "/api/auth/users",
        headers=admin_headers,
        json={
            "username": "operator-a",
            "email": "operator-a@example.com",
            "password": "password123",
            "role": "user",
        },
    )
    assert operator_response.status_code == 200
    operator_id = operator_response.json()["id"]

    grant_operator_permissions_response = client.put(
        f"/api/auth/users/{operator_id}/permissions",
        headers=admin_headers,
        json=["create:users", "update:users", "read:users"],
    )
    assert grant_operator_permissions_response.status_code == 200
    operator_headers = state.auth_header(f"token-{operator_id}")

    non_admin_creates_admin_response = client.post(
        "/api/auth/users",
        headers=operator_headers,
        json={
            "username": "blocked-admin",
            "email": "blocked-admin@example.com",
            "password": "password123",
            "role": "admin",
        },
    )
    assert non_admin_creates_admin_response.status_code == 403
    assert "higher than your own" in non_admin_creates_admin_response.json()["detail"].lower()

    non_admin_assigns_scope_response = client.post(
        "/api/auth/users",
        headers=operator_headers,
        json={
            "username": "blocked-scope",
            "email": "blocked-scope@example.com",
            "password": "password123",
            "role": "viewer",
            "org_id": "another-org",
        },
    )
    assert non_admin_assigns_scope_response.status_code == 403
    assert "tenant scope" in non_admin_assigns_scope_response.json()["detail"].lower()

    target_response = client.post(
        "/api/auth/users",
        headers=admin_headers,
        json={
            "username": "target-user",
            "email": "target-user@example.com",
            "password": "password123",
            "role": "viewer",
        },
    )
    assert target_response.status_code == 200
    target_id = target_response.json()["id"]

    non_admin_role_escalation_response = client.put(
        f"/api/auth/users/{target_id}",
        headers=operator_headers,
        json={"role": "admin"},
    )
    assert non_admin_role_escalation_response.status_code == 403
    assert "only administrators can modify role" in non_admin_role_escalation_response.json()["detail"].lower()


def test_manage_tenants_user_can_only_toggle_activation_workflow(client, monkeypatch: pytest.MonkeyPatch) -> None:
    state = WorkflowState()
    patch_auth_service(monkeypatch, state)
    admin_headers = state.auth_header("token-u-admin")

    tenant_manager_response = client.post(
        "/api/auth/users",
        headers=admin_headers,
        json={
            "username": "tenant-manager",
            "email": "tenant-manager@example.com",
            "password": "password123",
            "role": "user",
        },
    )
    assert tenant_manager_response.status_code == 200
    tenant_manager_id = tenant_manager_response.json()["id"]

    tenant_manager_permissions_response = client.put(
        f"/api/auth/users/{tenant_manager_id}/permissions",
        headers=admin_headers,
        json=["manage:tenants"],
    )
    assert tenant_manager_permissions_response.status_code == 200
    tenant_manager_headers = state.auth_header(f"token-{tenant_manager_id}")

    target_response = client.post(
        "/api/auth/users",
        headers=admin_headers,
        json={
            "username": "tenant-target",
            "email": "tenant-target@example.com",
            "password": "password123",
            "role": "viewer",
        },
    )
    assert target_response.status_code == 200
    target_id = target_response.json()["id"]

    activate_toggle_response = client.put(
        f"/api/auth/users/{target_id}",
        headers=tenant_manager_headers,
        json={"is_active": False},
    )
    assert activate_toggle_response.status_code == 200
    assert activate_toggle_response.json()["is_active"] is False

    forbidden_profile_update_response = client.put(
        f"/api/auth/users/{target_id}",
        headers=tenant_manager_headers,
        json={"full_name": "Updated By Tenant Manager"},
    )
    assert forbidden_profile_update_response.status_code == 403
    assert "only activate/deactivate" in forbidden_profile_update_response.json()["detail"].lower()


def test_non_admin_cannot_grant_group_permissions_above_own_scope_workflow(
    client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = WorkflowState()
    patch_auth_service(monkeypatch, state)
    admin_headers = state.auth_header("token-u-admin")

    delegate_response = client.post(
        "/api/auth/users",
        headers=admin_headers,
        json={
            "username": "group-delegate",
            "email": "group-delegate@example.com",
            "password": "password123",
            "role": "user",
        },
    )
    assert delegate_response.status_code == 200
    delegate_id = delegate_response.json()["id"]

    grant_delegate_permissions_response = client.put(
        f"/api/auth/users/{delegate_id}/permissions",
        headers=admin_headers,
        json=[
            "create:groups",
            "read:groups",
            "update:groups",
            "update:group_permissions",
            "update:group_members",
            "read:logs",
        ],
    )
    assert grant_delegate_permissions_response.status_code == 200
    delegate_headers = state.auth_header(f"token-{delegate_id}")

    create_group_response = client.post(
        "/api/auth/groups",
        headers=delegate_headers,
        json={"name": "delegate-scope-group", "description": "Delegation scope checks"},
    )
    assert create_group_response.status_code == 200
    group_id = create_group_response.json()["id"]

    out_of_scope_permissions_response = client.put(
        f"/api/auth/groups/{group_id}/permissions",
        headers=delegate_headers,
        json=["manage:users"],
    )
    assert out_of_scope_permissions_response.status_code == 403
    assert "higher than your own" in out_of_scope_permissions_response.json()["detail"].lower()

    in_scope_permissions_response = client.put(
        f"/api/auth/groups/{group_id}/permissions",
        headers=delegate_headers,
        json=["read:logs"],
    )
    assert in_scope_permissions_response.status_code == 200


def test_api_key_sharing_and_visibility_workflow(client, monkeypatch: pytest.MonkeyPatch) -> None:
    state = WorkflowState()
    patch_auth_service(monkeypatch, state)
    admin_headers = state.auth_header("token-u-admin")

    group_response = client.post(
        "/api/auth/groups",
        headers=admin_headers,
        json={"name": "share-group", "description": "Shared API keys"},
    )
    assert group_response.status_code == 200
    group_id = group_response.json()["id"]

    recipient_response = client.post(
        "/api/auth/users",
        headers=admin_headers,
        json={"username": "recipient", "email": "recipient@example.com", "password": "password123"},
    )
    recipient_id = recipient_response.json()["id"]

    member_response = client.post(
        "/api/auth/users",
        headers=admin_headers,
        json={"username": "member", "email": "member@example.com", "password": "password123"},
    )
    member_id = member_response.json()["id"]

    client.put(
        f"/api/auth/groups/{group_id}/members",
        headers=admin_headers,
        json={"user_ids": [member_id]},
    )

    created_key_response = client.post(
        "/api/auth/api-keys",
        headers=admin_headers,
        json={"name": "primary-scope", "key": "scope-primary"},
    )
    assert created_key_response.status_code == 200
    key_id = created_key_response.json()["id"]

    list_keys_response = client.get("/api/auth/api-keys", headers=admin_headers)
    assert list_keys_response.status_code == 200
    assert list_keys_response.json()[0]["id"] == key_id

    update_key_response = client.patch(
        f"/api/auth/api-keys/{key_id}",
        headers=admin_headers,
        json={"name": "primary-renamed", "is_enabled": True},
    )
    assert update_key_response.status_code == 200
    assert update_key_response.json()["name"] == "primary-renamed"

    regenerate_response = client.post(
        f"/api/auth/api-keys/{key_id}/otlp-token/regenerate",
        headers=admin_headers,
    )
    assert regenerate_response.status_code == 200
    assert regenerate_response.json()["otlp_token"] == f"regen-{key_id}"

    share_response = client.put(
        f"/api/auth/api-keys/{key_id}/shares",
        headers=admin_headers,
        json={"user_ids": [recipient_id], "group_ids": [group_id]},
    )
    assert share_response.status_code == 200
    assert {item["user_id"] for item in share_response.json()} == {recipient_id}

    recipient_keys_response = client.get(
        "/api/auth/api-keys",
        headers=state.auth_header(f"token-{recipient_id}"),
    )
    assert recipient_keys_response.status_code == 200
    assert recipient_keys_response.json()[0]["is_shared"] is True

    member_keys_response = client.get(
        "/api/auth/api-keys",
        headers=state.auth_header(f"token-{member_id}"),
    )
    assert member_keys_response.status_code == 200
    assert member_keys_response.json()[0]["is_shared"] is True

    hide_shared_response = client.post(
        f"/api/auth/api-keys/{key_id}/hide",
        headers=state.auth_header(f"token-{recipient_id}"),
        json={"hidden": True},
    )
    assert hide_shared_response.status_code == 200

    hidden_default_response = client.get(
        "/api/auth/api-keys",
        headers=state.auth_header(f"token-{recipient_id}"),
    )
    assert hidden_default_response.status_code == 200
    assert hidden_default_response.json() == []

    hidden_explicit_response = client.get(
        "/api/auth/api-keys?show_hidden=true",
        headers=state.auth_header(f"token-{recipient_id}"),
    )
    assert hidden_explicit_response.status_code == 200
    assert hidden_explicit_response.json()[0]["is_hidden"] is True

    shares_list_response = client.get(f"/api/auth/api-keys/{key_id}/shares", headers=admin_headers)
    assert shares_list_response.status_code == 200
    assert shares_list_response.json()[0]["user_id"] == recipient_id

    remove_share_response = client.delete(
        f"/api/auth/api-keys/{key_id}/shares/{recipient_id}",
        headers=admin_headers,
    )
    assert remove_share_response.status_code == 200

    recipient_keys_after_removal = client.get(
        "/api/auth/api-keys",
        headers=state.auth_header(f"token-{recipient_id}"),
    )
    assert recipient_keys_after_removal.status_code == 200
    assert recipient_keys_after_removal.json() == []

    delete_key_response = client.delete(f"/api/auth/api-keys/{key_id}", headers=admin_headers)
    assert delete_key_response.status_code == 200


def test_api_key_group_share_membership_revocation_workflow(client, monkeypatch: pytest.MonkeyPatch) -> None:
    state = WorkflowState()
    patch_auth_service(monkeypatch, state)
    admin_headers = state.auth_header("token-u-admin")

    group_response = client.post(
        "/api/auth/groups",
        headers=admin_headers,
        json={"name": "share-membership", "description": "Membership-scoped shares"},
    )
    assert group_response.status_code == 200
    group_id = group_response.json()["id"]

    recipient_response = client.post(
        "/api/auth/users",
        headers=admin_headers,
        json={"username": "recipient2", "email": "recipient2@example.com", "password": "password123"},
    )
    assert recipient_response.status_code == 200
    recipient_id = recipient_response.json()["id"]
    recipient_headers = state.auth_header(f"token-{recipient_id}")

    add_member_response = client.put(
        f"/api/auth/groups/{group_id}/members",
        headers=admin_headers,
        json={"user_ids": [recipient_id]},
    )
    assert add_member_response.status_code == 200

    created_key_response = client.post(
        "/api/auth/api-keys",
        headers=admin_headers,
        json={"name": "membership-shared", "key": "scope-membership"},
    )
    assert created_key_response.status_code == 200
    key_id = created_key_response.json()["id"]

    share_to_group_response = client.put(
        f"/api/auth/api-keys/{key_id}/shares",
        headers=admin_headers,
        json={"user_ids": [], "group_ids": [group_id]},
    )
    assert share_to_group_response.status_code == 200

    visible_before_removal = client.get("/api/auth/api-keys", headers=recipient_headers)
    assert visible_before_removal.status_code == 200
    assert {item["id"] for item in visible_before_removal.json()} == {key_id}

    remove_member_response = client.put(
        f"/api/auth/groups/{group_id}/members",
        headers=admin_headers,
        json={"user_ids": []},
    )
    assert remove_member_response.status_code == 200

    hidden_after_removal = client.get("/api/auth/api-keys", headers=recipient_headers)
    assert hidden_after_removal.status_code == 200
    assert hidden_after_removal.json() == []

    restore_member_response = client.put(
        f"/api/auth/groups/{group_id}/members",
        headers=admin_headers,
        json={"user_ids": [recipient_id]},
    )
    assert restore_member_response.status_code == 200

    visible_after_restore = client.get("/api/auth/api-keys", headers=recipient_headers)
    assert visible_after_restore.status_code == 200
    assert {item["id"] for item in visible_after_restore.json()} == {key_id}


def test_api_key_hide_unhide_restores_shared_visibility_workflow(client, monkeypatch: pytest.MonkeyPatch) -> None:
    state = WorkflowState()
    patch_auth_service(monkeypatch, state)
    admin_headers = state.auth_header("token-u-admin")

    recipient_response = client.post(
        "/api/auth/users",
        headers=admin_headers,
        json={"username": "recipient3", "email": "recipient3@example.com", "password": "password123"},
    )
    assert recipient_response.status_code == 200
    recipient_id = recipient_response.json()["id"]
    recipient_headers = state.auth_header(f"token-{recipient_id}")

    key_response = client.post(
        "/api/auth/api-keys",
        headers=admin_headers,
        json={"name": "hide-toggle", "key": "scope-hide-toggle"},
    )
    assert key_response.status_code == 200
    key_id = key_response.json()["id"]

    share_response = client.put(
        f"/api/auth/api-keys/{key_id}/shares",
        headers=admin_headers,
        json={"user_ids": [recipient_id], "group_ids": []},
    )
    assert share_response.status_code == 200

    hide_response = client.post(
        f"/api/auth/api-keys/{key_id}/hide",
        headers=recipient_headers,
        json={"hidden": True},
    )
    assert hide_response.status_code == 200
    assert hide_response.json() == {"status": "success", "hidden": True}

    list_default_hidden = client.get("/api/auth/api-keys", headers=recipient_headers)
    assert list_default_hidden.status_code == 200
    assert list_default_hidden.json() == []

    unhide_response = client.post(
        f"/api/auth/api-keys/{key_id}/hide",
        headers=recipient_headers,
        json={"hidden": False},
    )
    assert unhide_response.status_code == 200
    assert unhide_response.json() == {"status": "success", "hidden": False}

    list_after_unhide = client.get("/api/auth/api-keys", headers=recipient_headers)
    assert list_after_unhide.status_code == 200
    assert {item["id"] for item in list_after_unhide.json()} == {key_id}


def test_api_key_otlp_rotation_and_enablement_workflow(client, monkeypatch: pytest.MonkeyPatch) -> None:
    state = WorkflowState()
    patch_auth_service(monkeypatch, state)

    monkeypatch.setattr(internal_router.internal_service, "_get_internal_token", lambda: "internal-token")
    monkeypatch.setattr(internal_router.internal_service._auth_service, "validate_otlp_token", state.validate_otlp_token)

    admin_headers = state.auth_header("token-u-admin")
    key_response = client.post(
        "/api/auth/api-keys",
        headers=admin_headers,
        json={"name": "rotation-key", "key": "scope-rotation"},
    )
    assert key_response.status_code == 200
    key = key_response.json()
    key_id = key["id"]
    old_token = key["otlp_token"]

    initial_validate = client.post(
        "/api/internal/otlp/validate",
        headers={"X-Internal-Token": "internal-token"},
        json={"token": old_token},
    )
    assert initial_validate.status_code == 200
    assert initial_validate.json() == {"org_id": "scope-rotation"}

    rotate_response = client.post(
        f"/api/auth/api-keys/{key_id}/otlp-token/regenerate",
        headers=admin_headers,
    )
    assert rotate_response.status_code == 200
    new_token = rotate_response.json()["otlp_token"]
    assert new_token != old_token

    old_token_rejected = client.post(
        "/api/internal/otlp/validate",
        headers={"X-Internal-Token": "internal-token"},
        json={"token": old_token},
    )
    assert old_token_rejected.status_code == 404

    disable_key = client.patch(
        f"/api/auth/api-keys/{key_id}",
        headers=admin_headers,
        json={"is_enabled": False},
    )
    assert disable_key.status_code == 200

    disabled_token_rejected = client.post(
        "/api/internal/otlp/validate",
        headers={"X-Internal-Token": "internal-token"},
        json={"token": new_token},
    )
    assert disabled_token_rejected.status_code == 404

    reenable_key = client.patch(
        f"/api/auth/api-keys/{key_id}",
        headers=admin_headers,
        json={"is_enabled": True},
    )
    assert reenable_key.status_code == 200

    reenabled_token_valid = client.post(
        "/api/internal/otlp/validate",
        headers={"X-Internal-Token": "internal-token"},
        json={"token": new_token},
    )
    assert reenabled_token_valid.status_code == 200
    assert reenabled_token_valid.json() == {"org_id": "scope-rotation"}


def test_api_key_share_replacement_user_to_group_workflow(client, monkeypatch: pytest.MonkeyPatch) -> None:
    state = WorkflowState()
    patch_auth_service(monkeypatch, state)
    admin_headers = state.auth_header("token-u-admin")

    group_response = client.post(
        "/api/auth/groups",
        headers=admin_headers,
        json={"name": "share-switch-group", "description": "Share replacement checks"},
    )
    assert group_response.status_code == 200
    group_id = group_response.json()["id"]

    user_one_response = client.post(
        "/api/auth/users",
        headers=admin_headers,
        json={"username": "switch-user-1", "email": "switch-user-1@example.com", "password": "password123"},
    )
    user_two_response = client.post(
        "/api/auth/users",
        headers=admin_headers,
        json={"username": "switch-user-2", "email": "switch-user-2@example.com", "password": "password123"},
    )
    assert user_one_response.status_code == 200
    assert user_two_response.status_code == 200
    user_one_id = user_one_response.json()["id"]
    user_two_id = user_two_response.json()["id"]
    user_one_headers = state.auth_header(f"token-{user_one_id}")
    user_two_headers = state.auth_header(f"token-{user_two_id}")

    add_group_member = client.put(
        f"/api/auth/groups/{group_id}/members",
        headers=admin_headers,
        json={"user_ids": [user_two_id]},
    )
    assert add_group_member.status_code == 200

    key_response = client.post(
        "/api/auth/api-keys",
        headers=admin_headers,
        json={"name": "share-switch", "key": "scope-share-switch"},
    )
    assert key_response.status_code == 200
    key_id = key_response.json()["id"]

    share_to_user = client.put(
        f"/api/auth/api-keys/{key_id}/shares",
        headers=admin_headers,
        json={"user_ids": [user_one_id], "group_ids": []},
    )
    assert share_to_user.status_code == 200

    user_one_visible = client.get("/api/auth/api-keys", headers=user_one_headers)
    user_two_hidden = client.get("/api/auth/api-keys", headers=user_two_headers)
    assert user_one_visible.status_code == 200
    assert user_two_hidden.status_code == 200
    assert {item["id"] for item in user_one_visible.json()} == {key_id}
    assert user_two_hidden.json() == []

    share_to_group = client.put(
        f"/api/auth/api-keys/{key_id}/shares",
        headers=admin_headers,
        json={"user_ids": [], "group_ids": [group_id]},
    )
    assert share_to_group.status_code == 200

    user_one_now_hidden = client.get("/api/auth/api-keys", headers=user_one_headers)
    user_two_now_visible = client.get("/api/auth/api-keys", headers=user_two_headers)
    assert user_one_now_hidden.status_code == 200
    assert user_two_now_visible.status_code == 200
    assert user_one_now_hidden.json() == []
    assert {item["id"] for item in user_two_now_visible.json()} == {key_id}


def test_api_key_non_owner_share_and_delete_restrictions_workflow(client, monkeypatch: pytest.MonkeyPatch) -> None:
    state = WorkflowState()
    patch_auth_service(monkeypatch, state)
    admin_headers = state.auth_header("token-u-admin")

    outsider_response = client.post(
        "/api/auth/users",
        headers=admin_headers,
        json={"username": "outsider-key", "email": "outsider-key@example.com", "password": "password123"},
    )
    assert outsider_response.status_code == 200
    outsider_id = outsider_response.json()["id"]
    outsider_headers = state.auth_header(f"token-{outsider_id}")

    key_response = client.post(
        "/api/auth/api-keys",
        headers=admin_headers,
        json={"name": "owner-only", "key": "scope-owner-only"},
    )
    assert key_response.status_code == 200
    key_id = key_response.json()["id"]

    outsider_share_update = client.put(
        f"/api/auth/api-keys/{key_id}/shares",
        headers=outsider_headers,
        json={"user_ids": [outsider_id], "group_ids": []},
    )
    assert outsider_share_update.status_code in {400, 404}

    outsider_share_delete = client.delete(
        f"/api/auth/api-keys/{key_id}/shares/{outsider_id}",
        headers=outsider_headers,
    )
    assert outsider_share_delete.status_code in {400, 404}

    outsider_delete_key = client.delete(
        f"/api/auth/api-keys/{key_id}",
        headers=outsider_headers,
    )
    assert outsider_delete_key.status_code == 404


def test_api_key_delete_after_hidden_shared_state_cleanup_workflow(client, monkeypatch: pytest.MonkeyPatch) -> None:
    state = WorkflowState()
    patch_auth_service(monkeypatch, state)
    admin_headers = state.auth_header("token-u-admin")

    recipient_response = client.post(
        "/api/auth/users",
        headers=admin_headers,
        json={"username": "cleanup-recipient", "email": "cleanup-recipient@example.com", "password": "password123"},
    )
    assert recipient_response.status_code == 200
    recipient_id = recipient_response.json()["id"]
    recipient_headers = state.auth_header(f"token-{recipient_id}")

    key_response = client.post(
        "/api/auth/api-keys",
        headers=admin_headers,
        json={"name": "cleanup-key", "key": "scope-cleanup"},
    )
    assert key_response.status_code == 200
    key_id = key_response.json()["id"]

    share_response = client.put(
        f"/api/auth/api-keys/{key_id}/shares",
        headers=admin_headers,
        json={"user_ids": [recipient_id], "group_ids": []},
    )
    assert share_response.status_code == 200

    hide_response = client.post(
        f"/api/auth/api-keys/{key_id}/hide",
        headers=recipient_headers,
        json={"hidden": True},
    )
    assert hide_response.status_code == 200

    delete_response = client.delete(
        f"/api/auth/api-keys/{key_id}",
        headers=admin_headers,
    )
    assert delete_response.status_code == 200

    list_after_delete = client.get("/api/auth/api-keys?show_hidden=true", headers=recipient_headers)
    assert list_after_delete.status_code == 200
    assert list_after_delete.json() == []