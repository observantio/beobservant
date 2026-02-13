"""AlertManager service for alert operations."""
import httpx
import logging
import json
from typing import List, Optional, Dict

from models.alerting.alerts import Alert, AlertGroup, AlertStatus, AlertState
from models.alerting.silences import Silence, SilenceCreate, Matcher, Visibility
from models.alerting.rules import AlertRule
from models.alerting.receivers import AlertManagerStatus
from models.access.auth_models import TokenData
from config import config
from middleware.resilience import with_retry, with_timeout
from services.common.http_client import create_async_client
from services.alerting.silence_metadata import (
    SILENCE_META_PREFIX,
    normalize_visibility,
    encode_silence_comment,
    decode_silence_comment,
)
from services.alerting.ruler_yaml import (
    yaml_quote,
    group_enabled_rules,
    build_ruler_group_yaml,
    extract_mimir_group_names,
)
from services.alerting.alerts_ops import (
    list_metric_names,
    get_alerts,
    get_alert_groups,
    post_alerts,
    delete_alerts,
)
from services.alerting.silences_ops import (
    apply_silence_metadata,
    silence_accessible,
    get_silences,
    get_silence,
    create_silence,
    delete_silence,
    update_silence,
)
from services.alerting.channels_ops import notify_for_alerts, get_status, get_receivers
from services.alerting.rules_ops import resolve_rule_org_id, sync_mimir_rules_for_org

logger = logging.getLogger(__name__)
LABELS_JSON_ERROR = "Invalid filter_labels JSON"
MIMIR_RULES_NAMESPACE = "beobservant"
MIMIR_RULER_CONFIG_BASEPATH = "/prometheus/config/v1/rules"


class AlertManagerService:
    """Service for interacting with AlertManager."""
    
    def __init__(self, alertmanager_url: str = config.ALERTMANAGER_URL):
        """Initialize AlertManager service.
        
        Args:
            alertmanager_url: Base URL for AlertManager instance
        """
        self.alertmanager_url = alertmanager_url.rstrip('/')
        self.timeout = config.DEFAULT_TIMEOUT
        self._client = create_async_client(self.timeout)
        self._mimir_client = create_async_client(self.timeout)
        self.logger = logger
        self.config = config
        self.status_model = AlertManagerStatus
        self.MIMIR_RULES_NAMESPACE = MIMIR_RULES_NAMESPACE
        self.MIMIR_RULER_CONFIG_BASEPATH = MIMIR_RULER_CONFIG_BASEPATH

    def parse_filter_labels(self, filter_labels: Optional[str]) -> Optional[Dict[str, str]]:
        if not filter_labels:
            return None
        try:
            parsed = json.loads(filter_labels)
        except json.JSONDecodeError as exc:
            raise ValueError(LABELS_JSON_ERROR) from exc
        if not isinstance(parsed, dict):
            raise ValueError(LABELS_JSON_ERROR)
        return {str(key): str(value) for key, value in parsed.items()}

    def normalize_visibility(self, value: Optional[str]) -> str:
        return normalize_visibility(value)

    def encode_silence_comment(self, comment: str, visibility: str, shared_group_ids: List[str]) -> str:
        return encode_silence_comment(comment, visibility, shared_group_ids)

    def decode_silence_comment(self, comment: Optional[str]) -> Dict[str, object]:
        return decode_silence_comment(comment)

    def apply_silence_metadata(self, silence: Silence) -> Silence:
        return apply_silence_metadata(self, silence)

    def silence_accessible(self, silence: Silence, current_user: TokenData) -> bool:
        return silence_accessible(self, silence, current_user)

    def resolve_rule_org_id(self, rule_org_id: Optional[str], current_user: TokenData) -> str:
        return resolve_rule_org_id(self, rule_org_id, current_user)

    async def notify_for_alerts(self, alerts_list, storage_service, notification_service) -> None:
        return await notify_for_alerts(self, alerts_list, storage_service, notification_service)

    async def list_metric_names(self, org_id: str) -> List[str]:
        return await list_metric_names(self, org_id)

    def _yaml_quote(self, value: object) -> str:
        return yaml_quote(value)

    def _group_enabled_rules(self, rules: List[AlertRule]) -> Dict[str, List[AlertRule]]:
        return group_enabled_rules(rules)

    def _build_ruler_group_yaml(self, group_name: str, rules: List[AlertRule]) -> str:
        return build_ruler_group_yaml(group_name, rules)

    def _extract_mimir_group_names(self, namespace_yaml: str) -> List[str]:
        return extract_mimir_group_names(namespace_yaml)

    async def sync_mimir_rules_for_org(self, org_id: str, rules: List[AlertRule]) -> None:
        return await sync_mimir_rules_for_org(self, org_id, rules)
    
    @with_retry()
    @with_timeout()
    async def get_alerts(
        self,
        filter_labels: Optional[Dict[str, str]] = None,
        active: Optional[bool] = None,
        silenced: Optional[bool] = None,
        inhibited: Optional[bool] = None
    ) -> List[Alert]:
        return await get_alerts(self, filter_labels, active, silenced, inhibited)
    
    async def get_alert_groups(
        self,
        filter_labels: Optional[Dict[str, str]] = None
    ) -> List[AlertGroup]:
        return await get_alert_groups(self, filter_labels)
    
    async def post_alerts(self, alerts: List[Alert]) -> bool:
        return await post_alerts(self, alerts)
    
    async def get_silences(
        self,
        filter_labels: Optional[Dict[str, str]] = None
    ) -> List[Silence]:
        return await get_silences(self, filter_labels)
    
    async def get_silence(self, silence_id: str) -> Optional[Silence]:
        return await get_silence(self, silence_id)
    
    async def create_silence(self, silence: SilenceCreate) -> Optional[str]:
        return await create_silence(self, silence)
    
    async def delete_silence(self, silence_id: str) -> bool:
        return await delete_silence(self, silence_id)
    
    async def get_status(self) -> Optional[AlertManagerStatus]:
        return await get_status(self)
    
    async def get_receivers(self) -> List[str]:
        return await get_receivers(self)
    
    async def delete_alerts(
        self,
        filter_labels: Optional[Dict[str, str]] = None
    ) -> bool:
        return await delete_alerts(self, filter_labels)
    
    async def update_silence(self, silence_id: str, silence: SilenceCreate) -> Optional[str]:
        return await update_silence(self, silence_id, silence)
