from tests._env import ensure_test_env
ensure_test_env()

import pytest
import pyotp

from database import get_db_session
from config import config
from services.database_auth_service import DatabaseAuthService
from models.access.user_models import UserCreate
from db_models import Tenant


import database

@pytest.mark.skipif(not database.connection_test(), reason="DB not available")
def test_enroll_and_verify_mfa_flow():
    svc = DatabaseAuthService()
    svc._lazy_init()

    with get_db_session() as db:
        tenant = db.query(Tenant).filter_by(name=config.DEFAULT_ADMIN_TENANT).first()
        tenant_id = tenant.id

    # create a user and enroll TOTP
    user = svc.create_user(UserCreate(username='mfa-user', email='mfa-user@example.com', password='pwstrong', full_name='MFA User'), tenant_id)
    payload = svc.enroll_totp(user.id)
    assert 'secret' in payload and payload['secret']

    # verify with a correct code
    secret = payload['secret']
    code = pyotp.TOTP(secret).now()
    recovery_codes = svc.verify_enable_totp(user.id, code)
    assert isinstance(recovery_codes, list) and len(recovery_codes) > 0

    # ensure user now has MFA enabled
    updated = svc.get_user_by_id(user.id)
    assert updated.mfa_enabled is True
