"""User-related operations for DatabaseAuthService."""

from datetime import datetime, timezone
from typing import Optional, List

from fastapi import HTTPException, status
from sqlalchemy import and_, func
from sqlalchemy.orm import joinedload

from config import config
from database import get_db_session
from db_models import User, Group, Permission
from models.access.user_models import UserCreate, UserUpdate, User as UserSchema
from models.access.auth_models import Role


def get_user_by_id(service, user_id: str) -> Optional[UserSchema]:
    service._lazy_init()
    with get_db_session() as db:
        user = db.query(User).options(
            joinedload(User.groups),
            joinedload(User.permissions),
            joinedload(User.api_keys)
        ).filter_by(id=user_id).first()
        if not user:
            return None
        return service._to_user_schema(user)


def get_user_by_username(service, username: str) -> Optional[UserSchema]:
    username = (username or '').strip().lower()
    with get_db_session() as db:
        user = db.query(User).options(joinedload(User.api_keys)).filter(func.lower(User.username) == username).first()
        if not user:
            return None
        return service._to_user_schema(user)


def create_user(service, user_create: UserCreate, tenant_id: str, creator_id: str = None) -> UserSchema:
    with get_db_session() as db:
        normalized_username = (user_create.username or '').strip().lower()
        if db.query(User).filter(func.lower(User.username) == normalized_username).first():
            raise ValueError("Username already exists")

        if db.query(User).filter_by(email=user_create.email).first():
            raise ValueError("Email already exists")

        user = User(
            tenant_id=tenant_id,
            username=normalized_username,
            email=user_create.email,
            full_name=user_create.full_name,
            org_id=getattr(user_create, 'org_id', None) or config.DEFAULT_ORG_ID,
            role=user_create.role,
            is_active=user_create.is_active,
            hashed_password=service.hash_password(user_create.password),
            needs_password_change=True
        )

        if user_create.group_ids:
            groups = db.query(Group).filter(
                and_(
                    Group.id.in_(user_create.group_ids),
                    Group.tenant_id == tenant_id
                )
            ).all()
            user.groups.extend(groups)

        db.add(user)
        db.flush()

        service._ensure_default_api_key(db, user)

        if creator_id:
            service._log_audit(db, tenant_id, creator_id, "create_user", "users", user.id, {
                "username": user.username,
                "role": user.role
            })

        db.commit()
        return service._to_user_schema(user)


def list_users(service, tenant_id: str) -> List[UserSchema]:
    with get_db_session() as db:
        users = db.query(User).options(joinedload(User.groups), joinedload(User.api_keys)).filter_by(tenant_id=tenant_id).all()
        return [service._to_user_schema(user) for user in users]


def update_user(service, user_id: str, user_update: UserUpdate, tenant_id: str, updater_id: str = None) -> Optional[UserSchema]:
    with get_db_session() as db:
        user = db.query(User).filter_by(id=user_id, tenant_id=tenant_id).first()

        if not user:
            return None

        update_data = user_update.model_dump(exclude_unset=True)

        if updater_id and user_id == updater_id and 'is_active' in update_data and update_data['is_active'] is False:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You cannot disable your own account"
            )

        updater_user = None
        if updater_id:
            updater_user = db.query(User).filter_by(id=updater_id, tenant_id=tenant_id).first()

        if user.role == Role.ADMIN and updater_user and updater_user.role != Role.ADMIN and not updater_user.is_superuser:
            modifiable_fields = {'group_ids'}
            for field in update_data:
                if field not in modifiable_fields:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Only administrators can modify admin accounts"
                    )

        for field, value in update_data.items():
            if field == 'group_ids' and value is not None:
                groups = db.query(Group).filter(
                    and_(
                        Group.id.in_(value),
                        Group.tenant_id == tenant_id
                    )
                ).all()
                user.groups = groups
            else:
                setattr(user, field, value)

        user.updated_at = datetime.now(timezone.utc)

        if 'org_id' in update_data:
            service._ensure_default_api_key(db, user)

        if updater_id:
            service._log_audit(db, tenant_id, updater_id, "update_user", "users", user_id, update_data)

        db.commit()
        return service._to_user_schema(user)


def set_grafana_user_id(service, user_id: str, grafana_user_id: int, tenant_id: str) -> bool:
    with get_db_session() as db:
        user = db.query(User).filter_by(id=user_id, tenant_id=tenant_id).first()
        if not user:
            return False
        user.grafana_user_id = grafana_user_id
        db.commit()
        return True


def delete_user(service, user_id: str, tenant_id: str, deleter_id: str = None) -> bool:
    with get_db_session() as db:
        user = db.query(User).filter_by(id=user_id, tenant_id=tenant_id).first()

        if not user:
            return False

        if deleter_id:
            service._log_audit(db, tenant_id, deleter_id, "delete_user", "users", user_id, {
                "username": user.username
            })

        db.delete(user)
        db.commit()
        return True


def update_user_permissions(service, user_id: str, permission_names: List[str], tenant_id: str) -> bool:
    with get_db_session() as db:
        user = db.query(User).filter_by(id=user_id, tenant_id=tenant_id).first()
        if not user:
            return False

        permissions = db.query(Permission).filter(Permission.name.in_(permission_names)).all()
        user.permissions = permissions

        db.commit()
        return True
