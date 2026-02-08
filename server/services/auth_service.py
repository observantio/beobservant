import json
import logging
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any
from passlib.context import CryptContext
from jose import JWTError, jwt

from models.auth_models import (
    User, UserInDB, UserCreate, UserUpdate, UserPasswordUpdate,
    Group, GroupCreate, GroupUpdate, Token, TokenData, Role, Permission, ROLE_PERMISSIONS
)
from config import config

logger = logging.getLogger(__name__)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class AuthService:
    def __init__(self, storage_dir: str = config.STORAGE_DIR):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.users_file = self.storage_dir / config.USERS_FILE
        self.groups_file = self.storage_dir / config.GROUPS_FILE
        self._ensure_files()
        self._ensure_default_admin()

    def _ensure_files(self):
        if not self.users_file.exists():
            self.users_file.write_text(json.dumps([], indent=2))
        if not self.groups_file.exists():
            self.groups_file.write_text(json.dumps([], indent=2))

    def _ensure_default_admin(self):
        users = self._load_users()
        if not any(u.get("role") == Role.ADMIN for u in users):
            admin_username = config.DEFAULT_ADMIN_USERNAME
            admin_password = config.DEFAULT_ADMIN_PASSWORD
            admin_email = config.DEFAULT_ADMIN_EMAIL
            admin_tenant = config.DEFAULT_ADMIN_TENANT

            admin_user = {
                "id": str(uuid.uuid4()),
                "tenant_id": admin_tenant,
                "username": admin_username,
                "email": admin_email,
                "full_name": "System Administrator",
                "role": Role.ADMIN,
                "group_ids": [],
                "is_active": True,
                "hashed_password": self.hash_password(admin_password),
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "last_login": None
            }
            users.append(admin_user)
            self._save_users(users)
            logger.info("Created default admin user (username: admin, password: admin123)")

    def _load_users(self) -> List[Dict[str, Any]]:
        try:
            return json.loads(self.users_file.read_text())
        except Exception as e:
            logger.error(f"Error loading users: {e}")
            return []

    def _save_users(self, users: List[Dict[str, Any]]):
        self.users_file.write_text(json.dumps(users, indent=2, default=str))

    def _load_groups(self) -> List[Dict[str, Any]]:
        try:
            return json.loads(self.groups_file.read_text())
        except Exception as e:
            logger.error(f"Error loading groups: {e}")
            return []

    def _save_groups(self, groups: List[Dict[str, Any]]):
        self.groups_file.write_text(json.dumps(groups, indent=2, default=str))

    def hash_password(self, password: str) -> str:
        return pwd_context.hash(password)

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        return pwd_context.verify(plain_password, hashed_password)

    def create_access_token(self, user: UserInDB) -> Token:
        expires_delta = timedelta(minutes=config.JWT_EXPIRATION_MINUTES)
        expire = datetime.now(timezone.utc) + expires_delta
        
        permissions = ROLE_PERMISSIONS.get(user.role, [])
        
        to_encode = {
            "sub": user.id,
            "username": user.username,
            "tenant_id": user.tenant_id,
            "role": user.role,
            "permissions": [p.value for p in permissions],
            "exp": expire
        }
        
        encoded_jwt = jwt.encode(to_encode, config.JWT_SECRET_KEY, algorithm=config.JWT_ALGORITHM)
        
        return Token(
            access_token=encoded_jwt,
            token_type="bearer",
            expires_in=config.JWT_EXPIRATION_MINUTES * 60
        )

    def decode_token(self, token: str) -> Optional[TokenData]:
        try:
            payload = jwt.decode(token, config.JWT_SECRET_KEY, algorithms=[config.JWT_ALGORITHM])
            user_id: str = payload.get("sub")
            username: str = payload.get("username")
            tenant_id: str = payload.get("tenant_id")
            role: str = payload.get("role")
            permissions: List[str] = payload.get("permissions", [])
            group_ids: List[str] = payload.get("group_ids", [])
            
            if user_id is None or username is None:
                return None
            
            return TokenData(
                user_id=user_id,
                username=username,
                tenant_id=tenant_id,
                role=Role(role),
                permissions=[Permission(p) for p in permissions],
                group_ids=group_ids
            )
        except JWTError as e:
            logger.error(f"JWT decode error: {e}")
            return None

    def authenticate_user(self, username: str, password: str) -> Optional[UserInDB]:
        users = self._load_users()
        user_dict = next((u for u in users if u["username"] == username), None)
        
        if not user_dict:
            return None
        
        if not self.verify_password(password, user_dict["hashed_password"]):
            return None
        
        if not user_dict.get("is_active", True):
            return None
        
        user_dict["last_login"] = datetime.now(timezone.utc).isoformat()
        self._save_users(users)
        
        return UserInDB(**user_dict)

    def get_user_by_id(self, user_id: str) -> Optional[UserInDB]:
        users = self._load_users()
        user_dict = next((u for u in users if u["id"] == user_id), None)
        return UserInDB(**user_dict) if user_dict else None

    def get_user_by_username(self, username: str) -> Optional[UserInDB]:
        users = self._load_users()
        user_dict = next((u for u in users if u["username"] == username), None)
        return UserInDB(**user_dict) if user_dict else None

    def create_user(self, user_create: UserCreate, tenant_id: str) -> User:
        users = self._load_users()
        
        if any(u["username"] == user_create.username for u in users):
            raise ValueError("Username already exists")
        
        if any(u["email"] == user_create.email for u in users):
            raise ValueError("Email already exists")
        
        now = datetime.now(timezone.utc)
        user_dict = {
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "username": user_create.username,
            "email": user_create.email,
            "full_name": user_create.full_name,
            "role": user_create.role,
            "group_ids": user_create.group_ids,
            "is_active": user_create.is_active,
            "hashed_password": self.hash_password(user_create.password),
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "last_login": None
        }
        
        users.append(user_dict)
        self._save_users(users)
        
        return User(**{k: v for k, v in user_dict.items() if k != "hashed_password"})

    def list_users(self, tenant_id: str) -> List[User]:
        users = self._load_users()
        tenant_users = [u for u in users if u["tenant_id"] == tenant_id]
        return [User(**{k: v for k, v in u.items() if k != "hashed_password"}) for u in tenant_users]

    def update_user(self, user_id: str, user_update: UserUpdate, tenant_id: str) -> Optional[User]:
        users = self._load_users()
        user_dict = next((u for u in users if u["id"] == user_id and u["tenant_id"] == tenant_id), None)
        
        if not user_dict:
            return None
        
        update_data = user_update.model_dump(exclude_unset=True)
        user_dict.update(update_data)
        user_dict["updated_at"] = datetime.now(timezone.utc).isoformat()
        
        self._save_users(users)
        return User(**{k: v for k, v in user_dict.items() if k != "hashed_password"})

    def update_password(self, user_id: str, password_update: UserPasswordUpdate, tenant_id: str) -> bool:
        users = self._load_users()
        user_dict = next((u for u in users if u["id"] == user_id and u["tenant_id"] == tenant_id), None)
        
        if not user_dict:
            return False
        
        if not self.verify_password(password_update.current_password, user_dict["hashed_password"]):
            return False
        
        user_dict["hashed_password"] = self.hash_password(password_update.new_password)
        user_dict["updated_at"] = datetime.now(timezone.utc).isoformat()
        
        self._save_users(users)
        return True

    def delete_user(self, user_id: str, tenant_id: str) -> bool:
        users = self._load_users()
        original_count = len(users)
        users = [u for u in users if not (u["id"] == user_id and u["tenant_id"] == tenant_id)]
        
        if len(users) < original_count:
            self._save_users(users)
            return True
        return False

    def create_group(self, group_create: GroupCreate, tenant_id: str) -> Group:
        groups = self._load_groups()
        
        now = datetime.now(timezone.utc)
        group_dict = {
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "name": group_create.name,
            "description": group_create.description,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat()
        }
        
        groups.append(group_dict)
        self._save_groups(groups)
        
        return Group(**group_dict)

    def list_groups(self, tenant_id: str) -> List[Group]:
        groups = self._load_groups()
        tenant_groups = [g for g in groups if g["tenant_id"] == tenant_id]
        return [Group(**g) for g in tenant_groups]

    def get_group(self, group_id: str, tenant_id: str) -> Optional[Group]:
        groups = self._load_groups()
        group_dict = next((g for g in groups if g["id"] == group_id and g["tenant_id"] == tenant_id), None)
        return Group(**group_dict) if group_dict else None

    def delete_group(self, group_id: str, tenant_id: str) -> bool:
        groups = self._load_groups()
        original_count = len(groups)
        groups = [g for g in groups if not (g["id"] == group_id and g["tenant_id"] == tenant_id)]
        
        if len(groups) < original_count:
            self._save_groups(groups)
            
            users = self._load_users()
            for user in users:
                if group_id in user.get("group_ids", []):
                    user["group_ids"].remove(group_id)
                    user["updated_at"] = datetime.now(timezone.utc).isoformat()
            self._save_users(users)
            
            return True
        return False

    def update_group(self, group_id: str, group_update: GroupUpdate, tenant_id: str) -> Optional[Group]:
        groups = self._load_groups()
        group_dict = next((g for g in groups if g["id"] == group_id and g["tenant_id"] == tenant_id), None)

        if not group_dict:
            return None

        update_data = group_update.model_dump(exclude_unset=True)
        group_dict.update(update_data)
        group_dict["updated_at"] = datetime.now(timezone.utc).isoformat()

        self._save_groups(groups)
        return Group(**group_dict)
