"""Storage service for alert rules and notification channels."""
import json
import logging
import uuid
import tempfile
from pathlib import Path
from typing import List, Optional, Dict, Any

from cryptography.fernet import Fernet, InvalidToken
from models.alertmanager_models import (
    AlertRule, AlertRuleCreate, NotificationChannel, NotificationChannelCreate
)
from config import config

logger = logging.getLogger(__name__)

class StorageService:
    """Service for persisting alert rules and notification channels."""
    
    def __init__(self, data_dir: str = config.STORAGE_DIR):
        """Initialize storage service.
        
        Args:
            data_dir: Directory for storing data files
        """
        self.data_dir = self._find_writable_dir(Path(data_dir))

        self.rules_file = self.data_dir / "alert_rules.json"
        self.channels_file = self.data_dir / "notification_channels.json"

        self._fernet = None
        if config.DATA_ENCRYPTION_KEY:
            try:
                self._fernet = Fernet(config.DATA_ENCRYPTION_KEY)
            except ValueError:
                logger.error("Invalid DATA_ENCRYPTION_KEY; encryption disabled")
        
        try:
            self._ensure_files_exist()
        except PermissionError:
            logger.warning("Configured storage dir %s not writable, attempting fallback", data_dir)
            alternate = self._find_writable_dir(Path(tempfile.gettempdir()) / "beobservant")
            if str(alternate) != str(self.data_dir):
                self.data_dir = alternate
                self.rules_file = self.data_dir / "alert_rules.json"
                self.channels_file = self.data_dir / "notification_channels.json"
                self._ensure_files_exist()
            else:
                raise
    
    def _ensure_files_exist(self):
        """Ensure storage files exist with default data."""
        if not self.rules_file.exists():
            try:
                self.rules_file.write_text(self._serialize([]))
            except PermissionError as e:
                logger.error("Permission denied when creating %s: %s", self.rules_file, e)
                raise

        if not self.channels_file.exists():
            try:
                self.channels_file.write_text(self._serialize([]))
            except PermissionError as e:
                logger.error("Permission denied when creating %s: %s", self.channels_file, e)
                raise

    def _find_writable_dir(self, candidate: Path) -> Path:
        """Return a directory Path that is writable, trying fallbacks.

        Tries the configured `candidate` first, then `/tmp/beobservant`, then
        an application-local `data/` directory next to the server package.
        """
        candidates = [candidate, Path(tempfile.gettempdir()) / "beobservant",
                      Path(__file__).resolve().parent.parent / "data"]

        last_exc = None
        for p in candidates:
            try:
                p.mkdir(parents=True, exist_ok=True)
                test_file = p / ".writetest"
                with test_file.open("w") as f:
                    f.write("ok")
                try:
                    test_file.unlink()
                except Exception:
                    pass
                logger.info("Using storage directory: %s", p)
                return p
            except PermissionError as e:
                last_exc = e
                logger.warning("No write access to %s: %s", p, e)
            except Exception as e:
                last_exc = e
                logger.warning("Unable to prepare storage dir %s: %s", p, e)

        logger.error("No writable storage directory found; last error: %s", last_exc)
        raise PermissionError("No writable storage directory available")

    def _serialize(self, payload: List[Dict[str, Any]]) -> str:
        content = json.dumps(payload, indent=2, default=str)
        if not self._fernet:
            return content
        token = self._fernet.encrypt(content.encode("utf-8")).decode("utf-8")
        return f"ENC::{token}"

    def _deserialize(self, content: str) -> List[Dict[str, Any]]:
        if content.startswith("ENC::"):
            if not self._fernet:
                raise ValueError("Encrypted storage requires DATA_ENCRYPTION_KEY")
            token = content.replace("ENC::", "", 1)
            try:
                decrypted = self._fernet.decrypt(token.encode("utf-8")).decode("utf-8")
            except InvalidToken as exc:
                raise ValueError("Invalid encryption token or key") from exc
            return json.loads(decrypted)
        return json.loads(content)
    
    def get_alert_rules(self, tenant_id: str, user_id: str, group_ids: List[str] = None) -> List[AlertRule]:
        try:
            logger.info(f"Getting alert rules for user {user_id}, tenant {tenant_id}, group_ids={group_ids}")
            data = self._deserialize(self.rules_file.read_text())
            accessible_rules = []
            for rule in data:
                if rule.get("tenant_id") != tenant_id:
                    continue
                
                visibility = rule.get("visibility", "private")
                rule_id = rule.get("id", "unknown")
                shared_group_ids = rule.get("shared_group_ids", [])
                
                logger.debug(f"Rule {rule_id}: visibility={visibility}, shared_group_ids={shared_group_ids}, created_by={rule.get('created_by')}")
                
                if rule.get("created_by") == user_id:
                    logger.debug(f"Rule {rule_id} accessible (owner)")
                    accessible_rules.append(rule)
                
                elif visibility == "tenant":
                    logger.debug(f"Rule {rule_id} accessible (tenant-wide)")
                    accessible_rules.append(rule)
                
                elif visibility == "group" and group_ids:
                    if any(gid in shared_group_ids for gid in group_ids):
                        logger.debug(f"Rule {rule_id} accessible (group match)")
                        accessible_rules.append(rule)
                    else:
                        logger.debug(f"Rule {rule_id} NOT accessible (no group match)")
            
            logger.info(f"Returning {len(accessible_rules)} accessible rules out of {len([r for r in data if r.get('tenant_id') == tenant_id])} total")
            return [AlertRule(**rule) for rule in accessible_rules]
        except Exception as e:
            logger.error(f"Error loading alert rules: {e}")
            return []
    
    def get_alert_rule(self, rule_id: str, tenant_id: str, user_id: str, group_ids: List[str] = None) -> Optional[AlertRule]:
        rules = self.get_alert_rules(tenant_id, user_id, group_ids)
        for rule in rules:
            if rule.id == rule_id:
                return rule
        return None
    
    def create_alert_rule(self, rule_create: AlertRuleCreate, tenant_id: str, user_id: str, group_ids: List[str] = None) -> AlertRule:
        data = self._deserialize(self.rules_file.read_text())
        
        new_rule = AlertRule(
            id=str(uuid.uuid4()),
            **rule_create.model_dump()
        )
        
        rule_dict = new_rule.model_dump()
        rule_dict["tenant_id"] = tenant_id
        rule_dict["created_by"] = user_id
        rule_dict["group_ids"] = group_ids or []  
        
        rule_dict["visibility"] = rule_create.visibility
        rule_dict["shared_group_ids"] = rule_create.shared_group_ids
        
        data.append(rule_dict)
        self.rules_file.write_text(self._serialize(data))
        
        logger.info(f"Created alert rule: {new_rule.name} ({new_rule.id}) for tenant {tenant_id} with visibility={rule_create.visibility}")
        return new_rule
    
    def update_alert_rule(self, rule_id: str, rule_update: AlertRuleCreate, tenant_id: str, user_id: str, group_ids: List[str] = None) -> Optional[AlertRule]:
        data = self._deserialize(self.rules_file.read_text())
        
        for i, rule in enumerate(data):
            if rule["id"] == rule_id and rule.get("tenant_id") == tenant_id:
                
                visibility = rule.get("visibility", "private")
                has_access = False
                
                if rule.get("created_by") == user_id:
                    has_access = True
                elif visibility == "group" and group_ids:
                    shared_groups = rule.get("shared_group_ids", [])
                    if any(gid in shared_groups for gid in group_ids):
                        has_access = True
                elif visibility == "tenant":
                    has_access = True
                
                if not has_access:
                    return None
                
                updated_rule = AlertRule(
                    id=rule_id,
                    **rule_update.model_dump()
                )
                rule_dict = updated_rule.model_dump()
                rule_dict["tenant_id"] = tenant_id
                rule_dict["created_by"] = rule.get("created_by")
                rule_dict["group_ids"] = rule.get("group_ids", [])
                rule_dict["visibility"] = rule_update.visibility
                rule_dict["shared_group_ids"] = rule_update.shared_group_ids
                
                data[i] = rule_dict
                self.rules_file.write_text(self._serialize(data))
                logger.info(f"Updated alert rule: {updated_rule.name} ({rule_id})")
                return updated_rule
        
        return None
    
    def delete_alert_rule(self, rule_id: str, tenant_id: str, user_id: str, group_ids: List[str] = None) -> bool:
        data = self._deserialize(self.rules_file.read_text())
        
        # Find the rule and check access
        rule_to_delete = None
        for rule in data:
            if rule["id"] == rule_id and rule.get("tenant_id") == tenant_id:
                rule_to_delete = rule
                break
        
        if not rule_to_delete:
            return False
        
        # Check if user has permission to delete
        visibility = rule_to_delete.get("visibility", "private")
        has_access = False
        
        # Owner can always delete
        if rule_to_delete.get("created_by") == user_id:
            has_access = True
        # Group members can delete group-visible rules
        elif visibility == "group" and group_ids:
            shared_groups = rule_to_delete.get("shared_group_ids", [])
            if any(gid in shared_groups for gid in group_ids):
                has_access = True
        # Tenant-wide rules can be deleted by any tenant member
        elif visibility == "tenant":
            has_access = True
        
        if not has_access:
            return False
        
        # Remove the rule
        data = [r for r in data if r["id"] != rule_id]
        self.rules_file.write_text(self._serialize(data))
        logger.info(f"Deleted alert rule: {rule_id}")
        return True
    
    def _save_rules(self, rules: List[AlertRule]):
        """Save rules to file.
        
        Args:
            rules: List of rules to save
        """
        data = [rule.model_dump() for rule in rules]
        self.rules_file.write_text(self._serialize(data))
    
    def get_notification_channels(self, tenant_id: str, user_id: str, group_ids: List[str] = None) -> List[NotificationChannel]:
        try:
            logger.info(f"Getting notification channels for user {user_id}, tenant {tenant_id}, group_ids={group_ids}")
            data = self._deserialize(self.channels_file.read_text())
            accessible_channels = []
            for ch in data:
                if ch.get("tenant_id") != tenant_id:
                    continue
                
                visibility = ch.get("visibility", "private")
                channel_id = ch.get("id", "unknown")
                shared_group_ids = ch.get("shared_group_ids", [])
                
                logger.debug(f"Channel {channel_id}: visibility={visibility}, shared_group_ids={shared_group_ids}, created_by={ch.get('created_by')}")
                
                if ch.get("created_by") == user_id:
                    logger.debug(f"Channel {channel_id} accessible (owner)")
                    accessible_channels.append(ch)
                
                elif visibility == "tenant":
                    logger.debug(f"Channel {channel_id} accessible (tenant-wide)")
                    accessible_channels.append(ch)
                
                elif visibility == "group" and group_ids:
                    if any(gid in shared_group_ids for gid in group_ids):
                        logger.debug(f"Channel {channel_id} accessible (group match)")
                        accessible_channels.append(ch)
                    else:
                        logger.debug(f"Channel {channel_id} NOT accessible (no group match)")
            
            logger.info(f"Returning {len(accessible_channels)} accessible channels out of {len([c for c in data if c.get('tenant_id') == tenant_id])} total")
            return [NotificationChannel(**channel) for channel in accessible_channels]
        except Exception as e:
            logger.error(f"Error loading notification channels: {e}")
            return []
    
    def get_notification_channel(self, channel_id: str, tenant_id: str, user_id: str, group_ids: List[str] = None) -> Optional[NotificationChannel]:
        channels = self.get_notification_channels(tenant_id, user_id, group_ids)
        for channel in channels:
            if channel.id == channel_id:
                return channel
        return None
    
    def create_notification_channel(
        self,
        channel_create: NotificationChannelCreate,
        tenant_id: str,
        user_id: str,
        group_ids: List[str] = None
    ) -> NotificationChannel:
        data = self._deserialize(self.channels_file.read_text())
        
        new_channel = NotificationChannel(
            id=str(uuid.uuid4()),
            **channel_create.model_dump()
        )
        
        channel_dict = new_channel.model_dump()
        channel_dict["tenant_id"] = tenant_id
        channel_dict["created_by"] = user_id
        channel_dict["group_ids"] = group_ids or []  
        
        channel_dict["visibility"] = channel_create.visibility
        channel_dict["shared_group_ids"] = channel_create.shared_group_ids
        
        data.append(channel_dict)
        self.channels_file.write_text(self._serialize(data))
        
        logger.info(f"Created notification channel: {new_channel.name} ({new_channel.id}) for tenant {tenant_id} with visibility={channel_create.visibility}")
        return new_channel
    
    def update_notification_channel(
        self,
        channel_id: str,
        channel_update: NotificationChannelCreate,
        tenant_id: str,
        user_id: str,
        group_ids: List[str] = None
    ) -> Optional[NotificationChannel]:
        data = self._deserialize(self.channels_file.read_text())
        
        for i, channel in enumerate(data):
            if channel["id"] == channel_id and channel.get("tenant_id") == tenant_id:
                
                visibility = channel.get("visibility", "private")
                has_access = False
                
                if channel.get("created_by") == user_id:
                    has_access = True
                elif visibility == "group" and group_ids:
                    shared_groups = channel.get("shared_group_ids", [])
                    if any(gid in shared_groups for gid in group_ids):
                        has_access = True
                elif visibility == "tenant":
                    has_access = True
                
                if not has_access:
                    return None
                
                updated_channel = NotificationChannel(
                    id=channel_id,
                    **channel_update.model_dump()
                )
                channel_dict = updated_channel.model_dump()
                channel_dict["tenant_id"] = tenant_id
                channel_dict["created_by"] = channel.get("created_by")
                channel_dict["group_ids"] = channel.get("group_ids", [])
                channel_dict["visibility"] = channel_update.visibility
                channel_dict["shared_group_ids"] = channel_update.shared_group_ids
                
                data[i] = channel_dict
                self.channels_file.write_text(self._serialize(data))
                logger.info(f"Updated notification channel: {updated_channel.name} ({channel_id})")
                return updated_channel
        
        return None
    
    def delete_notification_channel(self, channel_id: str, tenant_id: str, user_id: str, group_ids: List[str] = None) -> bool:
        data = self._deserialize(self.channels_file.read_text())
        
        # Find the channel and check access
        channel_to_delete = None
        for channel in data:
            if channel["id"] == channel_id and channel.get("tenant_id") == tenant_id:
                channel_to_delete = channel
                break
        
        if not channel_to_delete:
            return False
        
        # Check if user has permission to delete
        visibility = channel_to_delete.get("visibility", "private")
        has_access = False
        
        # Owner can always delete
        if channel_to_delete.get("created_by") == user_id:
            has_access = True
        # Group members can delete group-visible channels
        elif visibility == "group" and group_ids:
            shared_groups = channel_to_delete.get("shared_group_ids", [])
            if any(gid in shared_groups for gid in group_ids):
                has_access = True
        # Tenant-wide channels can be deleted by any tenant member
        elif visibility == "tenant":
            has_access = True
        
        if not has_access:
            return False
        
        # Remove the channel
        data = [c for c in data if c["id"] != channel_id]
        self.channels_file.write_text(self._serialize(data))
        logger.info(f"Deleted notification channel: {channel_id}")
        return True
    
    def test_notification_channel(self, channel_id: str, tenant_id: str, user_id: str, group_ids: List[str] = None) -> Dict[str, Any]:
        channel = self.get_notification_channel(channel_id, tenant_id, user_id, group_ids)
        if not channel:
            return {"success": False, "error": "Channel not found"}
        
        logger.info(f"Testing notification channel: {channel.name} ({channel.type})")
        
        return {
            "success": True,
            "message": f"Test notification would be sent to {channel.type} channel: {channel.name}",
            "config": channel.config
        }
