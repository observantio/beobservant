"""Notification service for sending alerts through various channels."""
import httpx
import logging
from typing import Optional
from datetime import datetime

from models.alerting.channels import NotificationChannel, ChannelType
from models.alerting.alerts import Alert
from config import config
from services.common.url_utils import is_safe_http_url
from services.common.http_client import create_async_client

logger = logging.getLogger(__name__)
NO_VALUE = "(none)"

class NotificationService:
    """Service for sending notifications through various channels."""
    
    def __init__(self):
        self.timeout = config.DEFAULT_TIMEOUT
        self._client = create_async_client(self.timeout)
    
    async def send_notification(
        self,
        channel: NotificationChannel,
        alert: Alert,
        action: str = "firing"
    ) -> bool:
        """Send notification through the specified channel.
        
        Args:
            channel: Notification channel configuration
            alert: Alert to send
            action: Alert action (firing or resolved)
            
        Returns:
            True if notification was sent successfully
        """
        if not channel.enabled:
            logger.info(f"Channel {channel.name} is disabled, skipping notification")
            return False
        
        try:
            async_senders = {
                ChannelType.SLACK: self._send_slack,
                ChannelType.TEAMS: self._send_teams,
                ChannelType.WEBHOOK: self._send_webhook,
                ChannelType.PAGERDUTY: self._send_pagerduty,
                ChannelType.OPSGENIE: self._send_opsgenie,
            }
            if channel.type == ChannelType.EMAIL:
                return self._send_email(channel, alert, action)
            sender = async_senders.get(channel.type)
            if not sender:
                logger.error(f"Unknown channel type: {channel.type}")
                return False
            return await sender(channel, alert, action)
        except Exception as e:
            logger.exception("Error sending notification via %s: %s", channel.name, e)
            return False
    
    def _send_email(self, channel: NotificationChannel, alert: Alert, action: str) -> bool:
        """Send email notification."""
        channel_config = channel.config
        
        subject = f"[{action.upper()}] {alert.labels.get('alertname', 'Alert')}"
        logger.info(f"Email notification: {channel_config.get('to')} - {subject}")
        logger.info(f"Would send email via SMTP: {channel_config.get('smtp_host')}:{channel_config.get('smtp_port')}")
        
        return True
    
    async def _send_slack(self, channel: NotificationChannel, alert: Alert, action: str) -> bool:
        """Send Slack notification."""
        channel_config = channel.config
        webhook_url = channel_config.get('webhook_url') or channel_config.get('webhookUrl')
        
        if not is_safe_http_url(webhook_url):
            logger.error("Slack webhook URL is missing or invalid")
            return False
        
        color = "danger" if action == "firing" else "good"
        if alert.labels.get('severity') == 'warning':
            color = "warning"
        
        summary = self._get_annotation(alert, "summary")
        description = self._get_annotation(alert, "description")
        payload = {
            "attachments": [{
                "color": color,
                "title": f"[{action.upper()}] {self._get_label(alert, 'alertname', 'Alert')}",
                "text": self._get_alert_text(alert),
                "fields": [
                    {
                        "title": "Severity",
                        "value": self._get_label(alert, 'severity', 'unknown'),
                        "short": True
                    },
                    {
                        "title": "Status",
                        "value": action,
                        "short": True
                    },
                    {
                        "title": "Summary",
                        "value": summary or NO_VALUE,
                        "short": False
                    },
                    {
                        "title": "Description",
                        "value": description or NO_VALUE,
                        "short": False
                    }
                ],
                "footer": f"Started: {alert.starts_at}",
                "ts": int(datetime.now().timestamp())
            }]
        }
        
        response = await self._client.post(webhook_url, json=payload)
        response.raise_for_status()
        logger.info(
            "Slack notification sent to %s",
            channel_config.get('channel', config.DEFAULT_SLACK_CHANNEL),
        )
        return True
    
    async def _send_teams(self, channel: NotificationChannel, alert: Alert, action: str) -> bool:
        """Send Microsoft Teams notification."""
        channel_config = channel.config
        webhook_url = channel_config.get('webhook_url') or channel_config.get('webhookUrl')
        
        if not is_safe_http_url(webhook_url):
            logger.error("Teams webhook URL is missing or invalid")
            return False
        
        theme_color = "FF0000" if action == "firing" else "00FF00"
        if alert.labels.get('severity') == 'warning':
            theme_color = "FFA500"
        
        summary = self._get_annotation(alert, "summary")
        description = self._get_annotation(alert, "description")
        payload = {
            "@type": "MessageCard",
            "@context": "https://schema.org/extensions",
            "themeColor": theme_color,
            "title": f"[{action.upper()}] {self._get_label(alert, 'alertname', 'Alert')}",
            "text": self._get_alert_text(alert),
            "sections": [{
                "facts": [
                    {"name": "Severity", "value": self._get_label(alert, 'severity', 'unknown')},
                    {"name": "Status", "value": action},
                    {"name": "Started", "value": alert.starts_at},
                    {"name": "Summary", "value": summary or NO_VALUE},
                    {"name": "Description", "value": description or NO_VALUE}
                ]
            }]
        }
        
        response = await self._client.post(webhook_url, json=payload)
        response.raise_for_status()
        logger.info("Teams notification sent")
        return True
    
    async def _send_webhook(self, channel: NotificationChannel, alert: Alert, action: str) -> bool:
        """Send webhook notification."""
        channel_config = channel.config
        webhook_url = channel_config.get('url') or channel_config.get('webhook_url') or channel_config.get('webhookUrl')
        
        if not is_safe_http_url(webhook_url):
            logger.error("Webhook URL is missing or invalid")
            return False
        
        payload = {
            "action": action,
            "alert": {
                "labels": alert.labels,
                "annotations": alert.annotations,
                "startsAt": alert.starts_at,
                "endsAt": alert.ends_at,
                "fingerprint": alert.fingerprint
            }
        }
        
        headers = channel_config.get('headers', {})
        
        response = await self._client.post(webhook_url, json=payload, headers=headers)
        response.raise_for_status()
        logger.info("Webhook notification sent to %s", webhook_url)
        return True
    
    async def _send_pagerduty(self, channel: NotificationChannel, alert: Alert, action: str) -> bool:
        """Send PagerDuty notification."""
        channel_config = channel.config
        routing_key = channel_config.get('routing_key') or channel_config.get('integrationKey')
        
        if not routing_key:
            logger.error("PagerDuty routing key not configured")
            return False
        
        event_action = "trigger" if action == "firing" else "resolve"
        
        summary = self._get_annotation(alert, "summary")
        description = self._get_annotation(alert, "description")
        payload = {
            "routing_key": routing_key,
            "event_action": event_action,
            "dedup_key": alert.fingerprint,
            "payload": {
                "summary": summary or description or self._get_label(alert, 'alertname', 'Alert'),
                "severity": self._get_label(alert, 'severity', 'warning'),
                "source": self._get_label(alert, 'instance', 'unknown'),
                "custom_details": {
                    "labels": alert.labels or {},
                    "annotations": alert.annotations or {},
                    "summary": summary,
                    "description": description
                }
            }
        }
        
        response = await self._client.post(
            "https://events.pagerduty.com/v2/enqueue",
            json=payload,
        )
        response.raise_for_status()
        logger.info("PagerDuty notification sent")
        return True
    
    async def _send_opsgenie(self, channel: NotificationChannel, alert: Alert, action: str) -> bool:
        """Send Opsgenie notification."""
        channel_config = channel.config
        api_key = channel_config.get('api_key') or channel_config.get('apiKey')
        
        if not api_key:
            logger.error("Opsgenie API key not configured")
            return False
        
        url = "https://api.opsgenie.com/v2/alerts"
        headers = {"Authorization": f"GenieKey {api_key}"}
        
        summary = self._get_annotation(alert, "summary")
        description = self._get_annotation(alert, "description")

        if action == "firing":
            payload = {
                "message": self._get_label(alert, 'alertname', 'Alert'),
                "alias": alert.fingerprint,
                "description": description or summary or '',
                "priority": self._map_severity_to_priority(self._get_label(alert, 'severity', 'warning')),
                "details": alert.labels or {}
            }
            response = await self._client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            logger.info("Opsgenie alert created")
        else:
            response = await self._client.post(
                f"{url}/{alert.fingerprint}/close",
                params={"identifierType": "alias"},
                headers=headers,
            )
            response.raise_for_status()
            logger.info("Opsgenie alert closed")
        
        return True
    
    def _format_alert_body(self, alert: Alert, action: str) -> str:
        """Format alert body for email/text notifications."""
        summary = self._get_annotation(alert, "summary")
        description = self._get_annotation(alert, "description")
        lines = [
            f"Alert: {self._get_label(alert, 'alertname', 'Unknown')}",
            f"Status: {action}",
            f"Severity: {self._get_label(alert, 'severity', 'unknown')}",
            f"Started: {alert.starts_at}",
            "",
            "Summary:",
            summary or "No summary",
            "",
            "Description:",
            description or "No description",
            "",
            "Labels:"
        ]
        
        for key, value in alert.labels.items():
            lines.append(f"  {key}: {value}")
        
        return "\n".join(lines)

    def _get_label(self, alert: Alert, key: str, default: str = "") -> str:
        labels = alert.labels or {}
        return str(labels.get(key, default))

    def _get_annotation(self, alert: Alert, key: str) -> Optional[str]:
        annotations = alert.annotations or {}
        value = annotations.get(key)
        if value is None:
            return None
        return str(value)

    def _get_alert_text(self, alert: Alert) -> str:
        summary = self._get_annotation(alert, "summary")
        description = self._get_annotation(alert, "description")
        if summary and description and summary != description:
            return f"{summary}\n{description}"
        return summary or description or "No description"
    
    def _map_severity_to_priority(self, severity: str) -> str:
        """Map alert severity to Opsgenie priority."""
        mapping = {
            "critical": "P1",
            "warning": "P3",
            "info": "P5"
        }
        return mapping.get(severity.lower(), "P3")
