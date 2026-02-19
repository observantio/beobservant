from tests._env import ensure_test_env
ensure_test_env()

import pytest
from fastapi import HTTPException

import database
from database import get_db_session
from config import config
from services.database_auth_service import DatabaseAuthService
from models.access.user_models import UserCreate
from models.access.api_key_models import ApiKeyCreate
from db_models import Tenant


@pytest.mark.skipif(not database.connection_test(), reason="DB not available")
def test_list_api_keys_hides_otlp_token_for_shared_user():
    svc = DatabaseAuthService()
    svc._lazy_init()

    with get_db_session() as db:
        tenant = db.query(Tenant).filter_by(name=config.DEFAULT_ADMIN_TENANT).first()
        tenant_id = tenant.id

    owner = svc.create_user(UserCreate(username='owner', email='owner@example.com', password='pw', full_name='Owner'), tenant_id)
    other = svc.create_user(UserCreate(username='other', email='other@example.com', password='pw', full_name='Other'), tenant_id)

    created = svc.create_api_key(owner.id, tenant_id, ApiKeyCreate(name='owner-key', key='org-owner'))
    assert created.otlp_token  # owner can see token

    # share with other user
    svc.replace_api_key_shares(owner.id, tenant_id, created.id, [other.id], group_ids=[])

    keys_for_other = svc.list_api_keys(other.id)
    shared_entry = next((k for k in keys_for_other if k.id == created.id), None)
    assert shared_entry is not None
    assert shared_entry.is_shared is True
    assert shared_entry.otlp_token is None
    assert shared_entry.owner_user_id == owner.id
    assert getattr(shared_entry, 'owner_username', None) == owner.username


@pytest.mark.skipif(not database.connection_test(), reason="DB not available")
def test_delete_api_key_by_non_owner_returns_403():
    svc = DatabaseAuthService()
    svc._lazy_init()

    with get_db_session() as db:
        tenant = db.query(Tenant).filter_by(name=config.DEFAULT_ADMIN_TENANT).first()
        tenant_id = tenant.id

    owner = svc.create_user(UserCreate(username='del-owner', email='del-owner@example.com', password='pw', full_name='Owner'), tenant_id)
    other = svc.create_user(UserCreate(username='del-other', email='del-other@example.com', password='pw', full_name='Other'), tenant_id)

    created = svc.create_api_key(owner.id, tenant_id, ApiKeyCreate(name='del-key', key='org-del'))
    svc.replace_api_key_shares(owner.id, tenant_id, created.id, [other.id], group_ids=[])

    with pytest.raises(HTTPException) as exc:
        svc.delete_api_key(other.id, created.id)
    assert exc.value.status_code == 403


@pytest.mark.skipif(not database.connection_test(), reason="DB not available")
def test_delete_api_key_by_owner_succeeds():
    svc = DatabaseAuthService()
    svc._lazy_init()

    with get_db_session() as db:
        tenant = db.query(Tenant).filter_by(name=config.DEFAULT_ADMIN_TENANT).first()
        tenant_id = tenant.id

    owner = svc.create_user(UserCreate(username='owner2', email='owner2@example.com', password='pw', full_name='Owner'), tenant_id)
    created = svc.create_api_key(owner.id, tenant_id, ApiKeyCreate(name='owner2-key', key='org-owner2'))

    ok = svc.delete_api_key(owner.id, created.id)
    assert ok is True
