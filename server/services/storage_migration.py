"""One-time migration of alert rules and notification channels from legacy
JSON files into the database.

Reads data produced by the old file-based ``StorageService`` and inserts
any records not yet present in PostgreSQL (matched by ``id`` +
``tenant_id``).  After a successful pass the JSON files are renamed to
``*.json.migrated`` so the migration does not repeat.

Safe to call on every startup – it silently does nothing when no legacy
files are found or all records have already been imported.
"""
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.orm import Session

from config import config as app_config
from database import get_db_session
from db_models import (
    AlertRule as AlertRuleDB,
    NotificationChannel as NotificationChannelDB,
    Group,
)

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _deserialize(content: str, fernet: Optional[Fernet] = None) -> List[Dict[str, Any]]:
    """Deserialize file content, handling optional Fernet encryption."""
    if content.startswith("ENC::"):
        if not fernet:
            raise ValueError("Encrypted storage file requires DATA_ENCRYPTION_KEY")
        token = content[len("ENC::"):]
        try:
            decrypted = fernet.decrypt(token.encode()).decode()
        except InvalidToken as exc:
            raise ValueError("Cannot decrypt legacy storage – wrong key?") from exc
        return json.loads(decrypted)
    return json.loads(content)


def _resolve_groups(db: Session, group_ids: List[str]) -> List[Group]:
    if not group_ids:
        return []
    return db.query(Group).filter(Group.id.in_(group_ids)).all()


def _encrypt_config(cfg: Dict[str, Any], fernet: Optional[Fernet] = None) -> Dict[str, Any]:
    """Encrypt channel config for DB storage if a Fernet key is provided."""
    if not fernet:
        return cfg
    try:
        plaintext = json.dumps(cfg, default=str)
        token = fernet.encrypt(plaintext.encode()).decode()
        return {"__encrypted__": token}
    except Exception:
        logger.exception("Failed to encrypt channel config during migration")
        return cfg


# ------------------------------------------------------------------
# Public entry point
# ------------------------------------------------------------------

def migrate_file_storage_to_db() -> None:
    """Import legacy JSON storage into PostgreSQL (idempotent)."""
    storage_dir = Path(app_config.STORAGE_DIR)
    rules_file = storage_dir / "alert_rules.json"
    channels_file = storage_dir / "notification_channels.json"

    if not rules_file.exists() and not channels_file.exists():
        return  # Nothing to migrate

    fernet: Optional[Fernet] = None
    if app_config.DATA_ENCRYPTION_KEY:
        try:
            fernet = Fernet(app_config.DATA_ENCRYPTION_KEY)
        except ValueError:
            logger.error("Invalid DATA_ENCRYPTION_KEY – migration may fail for encrypted files")

    migrated_rules = 0
    migrated_channels = 0

    with get_db_session() as db:
        # --- Alert rules ---
        if rules_file.exists():
            try:
                rules_data = _deserialize(rules_file.read_text(), fernet)
                for rd in rules_data:
                    rule_id, tenant_id = rd.get("id"), rd.get("tenant_id")
                    if not rule_id or not tenant_id:
                        continue
                    if db.query(AlertRuleDB).filter_by(id=rule_id, tenant_id=tenant_id).first():
                        continue

                    rule = AlertRuleDB(
                        id=rule_id,
                        tenant_id=tenant_id,
                        created_by=rd.get("created_by"),
                        name=rd.get("name", ""),
                        group=rd.get("group", app_config.DEFAULT_RULE_GROUP),
                        expr=rd.get("expr", ""),
                        duration=rd.get("duration", "5m"),
                        severity=rd.get("severity", "warning"),
                        labels=rd.get("labels", {}),
                        annotations=rd.get("annotations", {}),
                        enabled=rd.get("enabled", True),
                        notification_channels=rd.get("notification_channels", []),
                        visibility=rd.get("visibility", "private"),
                    )
                    shared = rd.get("shared_group_ids", [])
                    if shared:
                        rule.shared_groups = _resolve_groups(db, shared)
                    db.add(rule)
                    migrated_rules += 1
                logger.info("Migrated %d alert rules from JSON → DB", migrated_rules)
            except Exception:
                logger.exception("Error migrating alert rules")

        # --- Notification channels ---
        if channels_file.exists():
            try:
                channels_data = _deserialize(channels_file.read_text(), fernet)
                for cd in channels_data:
                    ch_id, tenant_id = cd.get("id"), cd.get("tenant_id")
                    if not ch_id or not tenant_id:
                        continue
                    if db.query(NotificationChannelDB).filter_by(id=ch_id, tenant_id=tenant_id).first():
                        continue

                    ch = NotificationChannelDB(
                        id=ch_id,
                        tenant_id=tenant_id,
                        created_by=cd.get("created_by"),
                        name=cd.get("name", ""),
                        type=cd.get("type", "webhook"),
                        config=_encrypt_config(cd.get("config", {}), fernet),
                        enabled=cd.get("enabled", True),
                        visibility=cd.get("visibility", "private"),
                    )
                    shared = cd.get("shared_group_ids", [])
                    if shared:
                        ch.shared_groups = _resolve_groups(db, shared)
                    db.add(ch)
                    migrated_channels += 1
                logger.info("Migrated %d channels from JSON → DB", migrated_channels)
            except Exception:
                logger.exception("Error migrating notification channels")

    # Archive files so migration does not run again – even if zero new
    # records were imported (all already existed).
    for f in (rules_file, channels_file):
        if f.exists():
            dest = f.with_suffix(".json.migrated")
            try:
                f.rename(dest)
                logger.info("Archived %s → %s", f.name, dest.name)
            except OSError as exc:
                logger.warning("Could not archive %s: %s", f, exc)

    if migrated_rules or migrated_channels:
        logger.info("Legacy migration complete: %d rules, %d channels imported",
                     migrated_rules, migrated_channels)
