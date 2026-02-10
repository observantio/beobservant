"""AlertManager related models."""
from typing import Dict, List, Optional, Any, Union
from pydantic import BaseModel, Field
from enum import Enum

from config import config

# Description constants
DESC_CURRENT_STATE_ALERT = "Current state of the alert"
DESC_LIST_SILENCES_SILENCE_ALERT = "List of silences that silence this alert"
DESC_LIST_ALERTS_INHIBIT_ALERT = "List of alerts that inhibit this alert"
DESC_KEY_VALUE_PAIRS_IDENTIFY_ALERT = "Key-value pairs that identify the alert"
DESC_ADDITIONAL_INFO_ALERT = "Additional information about the alert"
DESC_TIME_ALERT_STARTED_FIRING = "Time when the alert started firing"
DESC_TIME_ALERT_STOPPED_FIRING = "Time when the alert stopped firing"
DESC_URL_ALERT_GENERATOR = "URL of the alert generator"
DESC_CURRENT_STATUS_ALERT = "Current status of the alert"
DESC_LIST_RECEIVERS_ALERT = "List of receivers for this alert"
DESC_UNIQUE_IDENTIFIER_ALERT = "Unique identifier for the alert"
DESC_COMMON_LABELS_GROUP = "Common labels for the group"
DESC_RECEIVER_HANDLE_ALERTS = "Receiver that will handle these alerts"
DESC_LIST_ALERTS_GROUP = "List of alerts in this group"
DESC_LABEL_NAME_MATCH = "Label name to match"
DESC_VALUE_MATCH_AGAINST = "Value to match against"
DESC_VALUE_IS_REGEX = "Whether the value is a regular expression"
DESC_MATCH_EQUAL_VALUES = "Whether to match equal values"
DESC_UNIQUE_IDENTIFIER_SILENCE = "Unique identifier for the silence"
DESC_MATCHERS_DEFINE_SILENCE = "Matchers that define which alerts to silence"
DESC_TIME_SILENCE_STARTS = "Time when the silence starts"
DESC_TIME_SILENCE_ENDS = "Time when the silence ends"
DESC_USER_CREATED_SILENCE = "User who created the silence"
DESC_COMMENT_EXPLAINING_SILENCE = "Comment explaining the silence"
DESC_CURRENT_STATUS_SILENCE = "Current status of the silence"
DESC_VISIBILITY_SCOPE = "Visibility scope"
DESC_GROUP_IDS_SILENCE_SHARED_WITH = "Group IDs this silence is shared with"
DESC_GROUP_IDS_SHARE_WITH = "Group IDs to share with"
DESC_UNIQUE_IDENTIFIER = "Unique identifier"
DESC_CHANNEL_NAME = "Channel name"
DESC_CHANNEL_TYPE = "Channel type"
DESC_CHANNEL_ENABLED = "Whether the channel is enabled"
DESC_CHANNEL_SPECIFIC_CONFIG = "Channel-specific configuration"
DESC_GROUP_IDS_CHANNEL_SHARED_WITH = "Group IDs this channel is shared with (when visibility=group)"
DESC_API_KEY_VALUE_PRODUCT_RULE_SCOPED_TO = "API key value (product) this rule is scoped to"
DESC_RULE_NAME = "Rule name"
DESC_PROMQL_EXPRESSION = "PromQL expression"
DESC_DURATION_CONDITION_TRUE = "Duration for which the condition must be true"
DESC_ALERT_SEVERITY = "Alert severity"
DESC_ADDITIONAL_LABELS = "Additional labels"
DESC_ANNOTATIONS_DESC_SUMMARY = "Annotations with description, summary, etc."
DESC_ANNOTATIONS = "Annotations"
DESC_RULE_ENABLED = "Whether the rule is enabled"
DESC_RULE_GROUP_NAME = "Rule group name"
DESC_LIST_NOTIFICATION_CHANNEL_IDS_SEND_ALERTS = "List of notification channel IDs to send alerts to. If empty, sends to all channels."
DESC_LIST_NOTIFICATION_CHANNEL_IDS_EMPTY_ALL = "List of notification channel IDs. Empty means all channels."
DESC_GROUP_IDS_RULE_SHARED_WITH = "Group IDs this rule is shared with (when visibility=group)"
DESC_API_KEY_VALUE_PRODUCT_SCOPE_RULE_TO = "API key value (product) to scope this rule to"
DESC_NAME_RECEIVER = "Name of the receiver"
DESC_EMAIL_NOTIFICATION_CONFIGS = "Email notification configurations"
DESC_SLACK_NOTIFICATION_CONFIGS = "Slack notification configurations"
DESC_WEBHOOK_NOTIFICATION_CONFIGS = "Webhook notification configurations"
DESC_CLUSTER_INFO = "Cluster information"
DESC_VERSION_INFO = "Version information"
DESC_CURRENT_CONFIG = "Current configuration"
DESC_UPTIME_ALERTMANAGER = "Uptime of the AlertManager instance"

class AlertState(str, Enum):
    """Alert state enum."""
    UNPROCESSED = "unprocessed"
    ACTIVE = "active"
    SUPPRESSED = "suppressed"

class ChannelType(str, Enum):
    """Notification channel types."""
    EMAIL = "email"
    SLACK = "slack"
    TEAMS = "teams"
    WEBHOOK = "webhook"
    PAGERDUTY = "pagerduty"
    OPSGENIE = "opsgenie"

class RuleSeverity(str, Enum):
    """Alert rule severity levels."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"

class Visibility(str, Enum):
    """Visibility/sharing scope for resources."""
    PRIVATE = "private"  # Only visible to creator
    GROUP = "group"      # Visible to specified groups
    TENANT = "tenant"    # Visible to all users in tenant

class AlertStatus(BaseModel):
    """Alert status information."""
    state: AlertState = Field(..., description=DESC_CURRENT_STATE_ALERT)
    silenced_by: List[str] = Field(default_factory=list, alias="silencedBy", description=DESC_LIST_SILENCES_SILENCE_ALERT)
    inhibited_by: List[str] = Field(default_factory=list, alias="inhibitedBy", description=DESC_LIST_ALERTS_INHIBIT_ALERT)
    
    class Config:
        populate_by_name = True

class Alert(BaseModel):
    """Alert representation."""
    labels: Dict[str, str] = Field(..., description=DESC_KEY_VALUE_PAIRS_IDENTIFY_ALERT)
    annotations: Dict[str, str] = Field(default_factory=dict, description=DESC_ADDITIONAL_INFO_ALERT)
    starts_at: str = Field(..., alias="startsAt", description=DESC_TIME_ALERT_STARTED_FIRING)
    ends_at: Optional[str] = Field(None, alias="endsAt", description=DESC_TIME_ALERT_STOPPED_FIRING)
    generator_url: Optional[str] = Field(None, alias="generatorURL", description=DESC_URL_ALERT_GENERATOR)
    status: AlertStatus = Field(..., description=DESC_CURRENT_STATUS_ALERT)
    receivers: Optional[List[Union[str, Dict[str, Any]]]] = Field(default_factory=list, description=DESC_LIST_RECEIVERS_ALERT)
    fingerprint: Optional[str] = Field(None, description=DESC_UNIQUE_IDENTIFIER_ALERT)
    
    class Config:
        populate_by_name = True

class AlertGroup(BaseModel):
    """Grouped alerts."""
    labels: Dict[str, str] = Field(..., description=DESC_COMMON_LABELS_GROUP)
    receiver: str = Field(..., description=DESC_RECEIVER_HANDLE_ALERTS)
    alerts: List[Alert] = Field(..., description=DESC_LIST_ALERTS_GROUP)

class Matcher(BaseModel):
    """Alert matcher."""
    name: str = Field(..., description=DESC_LABEL_NAME_MATCH)
    value: str = Field(..., description=DESC_VALUE_MATCH_AGAINST)
    is_regex: bool = Field(False, alias="isRegex", description=DESC_VALUE_IS_REGEX)
    is_equal: bool = Field(True, alias="isEqual", description=DESC_MATCH_EQUAL_VALUES)
    
    class Config:
        populate_by_name = True

class Silence(BaseModel):
    """Silence representation."""
    id: Optional[str] = Field(None, description=DESC_UNIQUE_IDENTIFIER_SILENCE)
    matchers: List[Matcher] = Field(..., description=DESC_MATCHERS_DEFINE_SILENCE)
    starts_at: str = Field(..., alias="startsAt", description=DESC_TIME_SILENCE_STARTS)
    ends_at: str = Field(..., alias="endsAt", description=DESC_TIME_SILENCE_ENDS)
    created_by: str = Field(..., alias="createdBy", description=DESC_USER_CREATED_SILENCE)
    comment: str = Field(..., description=DESC_COMMENT_EXPLAINING_SILENCE)
    status: Optional[Dict[str, str]] = Field(None, description=DESC_CURRENT_STATUS_SILENCE)
    visibility: Optional[Visibility] = Field(None, description=DESC_VISIBILITY_SCOPE)
    shared_group_ids: List[str] = Field(default_factory=list, alias="sharedGroupIds", description=DESC_GROUP_IDS_SILENCE_SHARED_WITH)
    
    class Config:
        populate_by_name = True
        use_enum_values = True

class SilenceCreate(BaseModel):
    """Create a new silence."""
    matchers: List[Matcher] = Field(..., description=DESC_MATCHERS_DEFINE_SILENCE)
    starts_at: str = Field(..., alias="startsAt", description=DESC_TIME_SILENCE_STARTS)
    ends_at: str = Field(..., alias="endsAt", description=DESC_TIME_SILENCE_ENDS)
    created_by: str = Field(..., alias="createdBy", description=DESC_USER_CREATED_SILENCE)
    comment: str = Field(..., description=DESC_COMMENT_EXPLAINING_SILENCE)
    
    class Config:
        populate_by_name = True

class SilenceCreateRequest(BaseModel):
    """Client-facing silence creation payload (created_by is derived from auth)."""
    matchers: List[Matcher] = Field(..., description=DESC_MATCHERS_DEFINE_SILENCE)
    starts_at: str = Field(..., alias="startsAt", description=DESC_TIME_SILENCE_STARTS)
    ends_at: str = Field(..., alias="endsAt", description=DESC_TIME_SILENCE_ENDS)
    comment: str = Field(..., description=DESC_COMMENT_EXPLAINING_SILENCE)
    visibility: Visibility = Field(Visibility.PRIVATE, description=DESC_VISIBILITY_SCOPE)
    shared_group_ids: List[str] = Field(default_factory=list, alias="sharedGroupIds", description=DESC_GROUP_IDS_SHARE_WITH)

    class Config:
        populate_by_name = True
        use_enum_values = True

class NotificationChannel(BaseModel):
    """Notification channel configuration."""
    id: Optional[str] = Field(None, description=DESC_UNIQUE_IDENTIFIER)
    name: str = Field(..., description=DESC_CHANNEL_NAME)
    type: ChannelType = Field(..., description=DESC_CHANNEL_TYPE)
    enabled: bool = Field(True, description=DESC_CHANNEL_ENABLED)
    config: Dict[str, Any] = Field(..., description=DESC_CHANNEL_SPECIFIC_CONFIG)
    visibility: Visibility = Field(Visibility.PRIVATE, description=DESC_VISIBILITY_SCOPE)
    shared_group_ids: List[str] = Field(default_factory=list, alias="sharedGroupIds", description=DESC_GROUP_IDS_CHANNEL_SHARED_WITH)
    
    class Config:
        use_enum_values = True
        populate_by_name = True

class NotificationChannelCreate(BaseModel):
    """Create a notification channel."""
    name: str = Field(..., min_length=1, max_length=100, description=DESC_CHANNEL_NAME)
    type: ChannelType = Field(..., description=DESC_CHANNEL_TYPE)
    enabled: bool = Field(True, description=DESC_CHANNEL_ENABLED)
    config: Dict[str, Any] = Field(..., description=DESC_CHANNEL_SPECIFIC_CONFIG)
    visibility: Visibility = Field(Visibility.PRIVATE, description=DESC_VISIBILITY_SCOPE)
    shared_group_ids: List[str] = Field(default_factory=list, alias="sharedGroupIds", description=DESC_GROUP_IDS_SHARE_WITH)
    
    class Config:
        use_enum_values = True
        populate_by_name = True

class AlertRule(BaseModel):
    """Alert rule definition."""
    id: Optional[str] = Field(None, description=DESC_UNIQUE_IDENTIFIER)
    org_id: Optional[str] = Field(None, alias="orgId", description=DESC_API_KEY_VALUE_PRODUCT_RULE_SCOPED_TO)
    name: str = Field(..., description=DESC_RULE_NAME)
    expr: str = Field(..., description=DESC_PROMQL_EXPRESSION)
    duration: str = Field("1m", description=DESC_DURATION_CONDITION_TRUE)
    severity: RuleSeverity = Field(RuleSeverity.WARNING, description=DESC_ALERT_SEVERITY)
    labels: Dict[str, str] = Field(default_factory=dict, description=DESC_ADDITIONAL_LABELS)
    annotations: Dict[str, str] = Field(default_factory=dict, description=DESC_ANNOTATIONS_DESC_SUMMARY)
    enabled: bool = Field(True, description=DESC_RULE_ENABLED)
    group: str = Field(config.DEFAULT_RULE_GROUP, description=DESC_RULE_GROUP_NAME)
    notification_channels: List[str] = Field(default_factory=list, alias="notificationChannels", description=DESC_LIST_NOTIFICATION_CHANNEL_IDS_SEND_ALERTS)
    visibility: Visibility = Field(Visibility.PRIVATE, description=DESC_VISIBILITY_SCOPE)
    shared_group_ids: List[str] = Field(default_factory=list, alias="sharedGroupIds", description=DESC_GROUP_IDS_RULE_SHARED_WITH)
    
    class Config:
        use_enum_values = True
        populate_by_name = True

class AlertRuleCreate(BaseModel):
    """Create an alert rule."""
    org_id: Optional[str] = Field(None, alias="orgId", description=DESC_API_KEY_VALUE_PRODUCT_SCOPE_RULE_TO)
    name: str = Field(..., min_length=1, max_length=100, description=DESC_RULE_NAME)
    expr: str = Field(..., min_length=1, description=DESC_PROMQL_EXPRESSION)
    duration: str = Field("1m", description=DESC_DURATION_CONDITION_TRUE)
    severity: RuleSeverity = Field(RuleSeverity.WARNING, description=DESC_ALERT_SEVERITY)
    labels: Dict[str, str] = Field(default_factory=dict, description=DESC_ADDITIONAL_LABELS)
    annotations: Dict[str, str] = Field(default_factory=dict, description=DESC_ANNOTATIONS)
    enabled: bool = Field(True, description=DESC_RULE_ENABLED)
    group: str = Field(config.DEFAULT_RULE_GROUP, description=DESC_RULE_GROUP_NAME)
    notification_channels: List[str] = Field(default_factory=list, alias="notificationChannels", description=DESC_LIST_NOTIFICATION_CHANNEL_IDS_EMPTY_ALL)
    visibility: Visibility = Field(Visibility.PRIVATE, description=DESC_VISIBILITY_SCOPE)
    shared_group_ids: List[str] = Field(default_factory=list, alias="sharedGroupIds", description=DESC_GROUP_IDS_SHARE_WITH)
    
    class Config:
        use_enum_values = True
        populate_by_name = True

class Receiver(BaseModel):
    """Alert receiver configuration."""
    name: str = Field(..., description=DESC_NAME_RECEIVER)
    email_configs: Optional[List[Dict]] = Field(None, alias="emailConfigs", description=DESC_EMAIL_NOTIFICATION_CONFIGS)
    slack_configs: Optional[List[Dict]] = Field(None, alias="slackConfigs", description=DESC_SLACK_NOTIFICATION_CONFIGS)
    webhook_configs: Optional[List[Dict]] = Field(None, alias="webhookConfigs", description=DESC_WEBHOOK_NOTIFICATION_CONFIGS)
    
    class Config:
        populate_by_name = True

class AlertManagerStatus(BaseModel):
    """AlertManager status."""
    cluster: Dict[str, Any] = Field(..., description=DESC_CLUSTER_INFO)
    version_info: Dict[str, str] = Field(..., alias="versionInfo", description=DESC_VERSION_INFO)
    config: Dict[str, Any] = Field(..., description=DESC_CURRENT_CONFIG)
    uptime: str = Field(..., description=DESC_UPTIME_ALERTMANAGER)
    
    class Config:
        populate_by_name = True
