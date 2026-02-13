"""AlertManager service for alert operations."""
import httpx
import logging
import json
from typing import List, Optional, Dict
from datetime import datetime, timezone, timedelta
from urllib.parse import quote

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
        data = self.decode_silence_comment(silence.comment)
        silence.comment = data["comment"]
        silence.visibility = data["visibility"]
        silence.shared_group_ids = data["shared_group_ids"]
        return silence

    def silence_accessible(self, silence: Silence, current_user: TokenData) -> bool:
        visibility = silence.visibility or Visibility.TENANT.value
        if silence.created_by == current_user.username:
            return True
        if visibility == Visibility.TENANT.value:
            return True
        if visibility == Visibility.GROUP.value:
            user_group_ids = getattr(current_user, "group_ids", []) or []
            return any(group_id in silence.shared_group_ids for group_id in user_group_ids)
        return False

    def resolve_rule_org_id(self, rule_org_id: Optional[str], current_user: TokenData) -> str:
        user_org_id = getattr(current_user, "org_id", None)
        return rule_org_id or user_org_id or config.DEFAULT_ORG_ID

    async def notify_for_alerts(self, alerts_list, storage_service, notification_service) -> None:
        for incoming_alert in alerts_list:
            alertname = incoming_alert.get("labels", {}).get("alertname")
            if not alertname:
                logger.debug("Alert without alertname label, skipping")
                continue

            channels = storage_service.get_notification_channels_for_rule_name(alertname)
            if not channels:
                logger.info("No notification channels configured for rule %s", alertname)
                continue

            raw_status = incoming_alert.get("status") or {}
            state_value = None
            silenced = []
            inhibited = []
            if isinstance(raw_status, dict):
                state_value = raw_status.get("state")
                silenced = raw_status.get("silencedBy", []) or []
                inhibited = raw_status.get("inhibitedBy", []) or []
            elif isinstance(raw_status, str):
                state_value = raw_status

            state_enum = AlertState.ACTIVE if (state_value and str(state_value).lower() in {"active", "firing"}) else AlertState.UNPROCESSED
            status_obj = AlertStatus(state=state_enum, silencedBy=silenced, inhibitedBy=inhibited)

            starts_at = incoming_alert.get("startsAt") or incoming_alert.get("starts_at") or datetime.now(timezone.utc).isoformat()
            alert_model = Alert(
                labels=incoming_alert.get("labels", {}),
                annotations=incoming_alert.get("annotations", {}),
                startsAt=starts_at,
                endsAt=incoming_alert.get("endsAt") or incoming_alert.get("ends_at"),
                generatorURL=incoming_alert.get("generatorURL"),
                status=status_obj,
                fingerprint=incoming_alert.get("fingerprint") or incoming_alert.get("fingerPrint"),
            )

            action = "firing" if state_enum == AlertState.ACTIVE else "resolved"
            for channel in channels:
                try:
                    sent = await notification_service.send_notification(channel, alert_model, action)
                    logger.info("Sent notification to channel %s ok=%s", channel.name, sent)
                except Exception as exc:
                    logger.exception(
                        "Failed to send notification for rule %s to channel %s: %s",
                        alertname,
                        getattr(channel, "name", "unknown"),
                        exc,
                    )

    async def list_metric_names(self, org_id: str) -> List[str]:
        response = await self._mimir_client.get(
            f"{config.MIMIR_URL.rstrip('/')}/prometheus/api/v1/label/__name__/values",
            headers={"X-Scope-OrgID": org_id},
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("status") != "success":
            raise httpx.HTTPStatusError(
                "Mimir returned non-success status",
                request=response.request,
                response=response,
            )
        metrics = payload.get("data") or []
        if not isinstance(metrics, list):
            return []
        return metrics

    def _yaml_quote(self, value: object) -> str:
        return yaml_quote(value)

    def _group_enabled_rules(self, rules: List[AlertRule]) -> Dict[str, List[AlertRule]]:
        return group_enabled_rules(rules)

    def _build_ruler_group_yaml(self, group_name: str, rules: List[AlertRule]) -> str:
        return build_ruler_group_yaml(group_name, rules)

    def _extract_mimir_group_names(self, namespace_yaml: str) -> List[str]:
        return extract_mimir_group_names(namespace_yaml)

    async def sync_mimir_rules_for_org(self, org_id: str, rules: List[AlertRule]) -> None:
        desired_groups = self._group_enabled_rules(rules)
        headers = {"X-Scope-OrgID": org_id, "Content-Type": "application/yaml"}
        base_url = config.MIMIR_URL.rstrip("/")

        list_url = f"{base_url}{MIMIR_RULER_CONFIG_BASEPATH}/{MIMIR_RULES_NAMESPACE}"
        upsert_url = f"{base_url}{MIMIR_RULER_CONFIG_BASEPATH}/{MIMIR_RULES_NAMESPACE}"

        existing_group_names: List[str] = []
        try:
            response = await self._mimir_client.get(list_url, headers={"X-Scope-OrgID": org_id})
            if response.status_code == 200:
                existing_group_names = self._extract_mimir_group_names(response.text)
        except httpx.HTTPError:
            existing_group_names = []

        for group_name in existing_group_names:
            if group_name in desired_groups:
                continue
            delete_url = (
                f"{base_url}{MIMIR_RULER_CONFIG_BASEPATH}/"
                f"{MIMIR_RULES_NAMESPACE}/{quote(group_name, safe='')}"
            )
            delete_response = await self._mimir_client.delete(delete_url, headers={"X-Scope-OrgID": org_id})
            if delete_response.status_code not in {200, 202, 204, 404}:
                raise httpx.HTTPStatusError(
                    f"Unexpected Mimir delete response: {delete_response.status_code}",
                    request=delete_response.request,
                    response=delete_response,
                )

        for group_name, group_rules in desired_groups.items():
            payload = self._build_ruler_group_yaml(group_name, group_rules)
            post_response = await self._mimir_client.post(upsert_url, content=payload, headers=headers)
            if post_response.status_code not in {200, 201, 202, 204}:
                raise httpx.HTTPStatusError(
                    f"Unexpected Mimir upsert response: {post_response.status_code}",
                    request=post_response.request,
                    response=post_response,
                )
    
    @with_retry()
    @with_timeout()
    async def get_alerts(
        self,
        filter_labels: Optional[Dict[str, str]] = None,
        active: Optional[bool] = None,
        silenced: Optional[bool] = None,
        inhibited: Optional[bool] = None
    ) -> List[Alert]:
        """Get all alerts with optional filters.
        
        Args:
            filter_labels: Filter by label key-value pairs
            active: Filter active alerts
            silenced: Filter silenced alerts
            inhibited: Filter inhibited alerts
            
        Returns:
            List of Alert objects
        """
        params = {}
        
        filters = []
        if filter_labels:
            for key, value in filter_labels.items():
                filters.append(f'{key}="{value}"')
        
        if active is not None:
            filters.append(f'active={str(active).lower()}')
        if silenced is not None:
            filters.append(f'silenced={str(silenced).lower()}')
        if inhibited is not None:
            filters.append(f'inhibited={str(inhibited).lower()}')
        
        if filters:
            params["filter"] = filters
        
        try:
            response = await self._client.get(
                f"{self.alertmanager_url}/api/v2/alerts",
                params=params,
            )
            response.raise_for_status()
            return [Alert(**alert) for alert in response.json()]
        except httpx.HTTPError as e:
            logger.error("Error fetching alerts: %s", e)
            return []
    
    async def get_alert_groups(
        self,
        filter_labels: Optional[Dict[str, str]] = None
    ) -> List[AlertGroup]:
        """Get alert groups.
        
        Args:
            filter_labels: Filter by label key-value pairs
            
        Returns:
            List of AlertGroup objects
        """
        params = {}
        if filter_labels:
            filters = [f'{k}="{v}"' for k, v in filter_labels.items()]
            params["filter"] = filters
        
        try:
            response = await self._client.get(
                f"{self.alertmanager_url}/api/v2/alerts/groups",
                params=params,
            )
            response.raise_for_status()
            return [AlertGroup(**group) for group in response.json()]
        except httpx.HTTPError as e:
            logger.error("Error fetching alert groups: %s", e)
            return []
    
    async def post_alerts(self, alerts: List[Alert]) -> bool:
        """Post new alerts to AlertManager.
        
        Args:
            alerts: List of Alert objects to post
            
        Returns:
            True if successful, False otherwise
        """
        try:
            alert_data = [alert.model_dump(by_alias=True) for alert in alerts]
            response = await self._client.post(
                f"{self.alertmanager_url}/api/v2/alerts",
                json=alert_data,
            )
            response.raise_for_status()
            return True
        except httpx.HTTPError as e:
            logger.error("Error posting alerts: %s", e)
            return False
    
    async def get_silences(
        self,
        filter_labels: Optional[Dict[str, str]] = None
    ) -> List[Silence]:
        """Get all silences.
        
        Args:
            filter_labels: Filter by label key-value pairs
            
        Returns:
            List of Silence objects
        """
        params = {}
        if filter_labels:
            filters = [f'{k}="{v}"' for k, v in filter_labels.items()]
            params["filter"] = filters
        
        try:
            response = await self._client.get(
                f"{self.alertmanager_url}/api/v2/silences",
                params=params,
            )
            response.raise_for_status()
            return [Silence(**silence) for silence in response.json()]
        except httpx.HTTPError as e:
            logger.error("Error fetching silences: %s", e)
            return []
    
    async def get_silence(self, silence_id: str) -> Optional[Silence]:
        """Get a specific silence by ID.
        
        Args:
            silence_id: Silence identifier
            
        Returns:
            Silence object or None if not found
        """
        try:
            response = await self._client.get(
                f"{self.alertmanager_url}/api/v2/silence/{silence_id}",
            )
            response.raise_for_status()
            return Silence(**response.json())
        except httpx.HTTPError as e:
            logger.error("Error fetching silence %s: %s", silence_id, e)
            return None
    
    async def create_silence(self, silence: SilenceCreate) -> Optional[str]:
        """Create a new silence.
        
        Args:
            silence: SilenceCreate object
            
        Returns:
            Silence ID if successful, None otherwise
        """
        try:
            silence_data = silence.model_dump(by_alias=True, exclude_none=True)
            response = await self._client.post(
                f"{self.alertmanager_url}/api/v2/silences",
                json=silence_data,
            )
            response.raise_for_status()
            return response.json().get("silenceID")
        except httpx.HTTPError as e:
            logger.error("Error creating silence: %s", e)
            return None
    
    async def delete_silence(self, silence_id: str) -> bool:
        """Delete a silence.
        
        Args:
            silence_id: Silence identifier
            
        Returns:
            True if successful, False otherwise
        """
        try:
            response = await self._client.delete(
                f"{self.alertmanager_url}/api/v2/silence/{silence_id}",
            )
            response.raise_for_status()
            return True
        except httpx.HTTPError as e:
            logger.error("Error deleting silence %s: %s", silence_id, e)
            return False
    
    async def get_status(self) -> Optional[AlertManagerStatus]:
        """Get AlertManager status.
        
        Returns:
            AlertManagerStatus object or None if error
        """
        try:
            response = await self._client.get(
                f"{self.alertmanager_url}/api/v2/status",
            )
            response.raise_for_status()
            return AlertManagerStatus(**response.json())
        except httpx.HTTPError as e:
            logger.error("Error fetching status: %s", e)
            return None
    
    async def get_receivers(self) -> List[str]:
        """Get list of configured receivers.
        
        Returns:
            List of receiver names
        """
        status = await self.get_status()
        if status and status.config:
            receivers = status.config.get("receivers", [])
            return [r.get("name") for r in receivers if r.get("name")]
        return []
    
    async def delete_alerts(
        self,
        filter_labels: Optional[Dict[str, str]] = None
    ) -> bool:
        """Delete alerts matching the filter.
        
        Note: AlertManager doesn't have a direct delete endpoint for alerts.
        This creates a silence to suppress matching alerts.
        
        Args:
            filter_labels: Filter by label key-value pairs
            
        Returns:
            True if silence created successfully
        """
        if not filter_labels:
            logger.warning("Cannot delete all alerts without filter")
            return False
        
        matchers = [
            Matcher(name=k, value=v, isRegex=False, isEqual=True)
            for k, v in filter_labels.items()
        ]
        
        now = datetime.now(timezone.utc)
        end = now + timedelta(seconds=60)
        
        starts_at = now.replace(microsecond=0).isoformat().replace("+00:00", "Z")
        ends_at = end.replace(microsecond=0).isoformat().replace("+00:00", "Z")
        
        silence = SilenceCreate(
            matchers=matchers,
            startsAt=starts_at,
            endsAt=ends_at,
            createdBy="beobservant",
            comment="Alert deletion via API"
        )
        
        silence_id = await self.create_silence(silence)
        return silence_id is not None
    
    async def update_silence(self, silence_id: str, silence: SilenceCreate) -> Optional[str]:
        """Update an existing silence.
        
        Note: AlertManager doesn't have update, so we delete and recreate.
        
        Args:
            silence_id: Existing silence ID
            silence: New silence data
            
        Returns:
            New silence ID if successful
        """
        await self.delete_silence(silence_id)
        
        return await self.create_silence(silence)
