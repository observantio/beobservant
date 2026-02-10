"""AlertManager API router."""
from fastapi import APIRouter, HTTPException, Query, Body, Request, status, Depends
from typing import Optional, List, Dict
import json
import logging
import httpx

from models.alertmanager_models import (
    Alert, AlertGroup, Silence, SilenceCreate, SilenceCreateRequest, Visibility,
    AlertManagerStatus, AlertRule, AlertRuleCreate,
    NotificationChannel, NotificationChannelCreate
)
from services.alertmanager_service import AlertManagerService
from services.storage_db_service import DatabaseStorageService
from services.notification_service import NotificationService
from config import config, constants
from middleware.rate_limit import enforce_ip_rate_limit
from models.alertmanager_models import AlertStatus, AlertState
from datetime import datetime, timezone
from models.auth_models import TokenData, Permission

from routers.auth_router import require_permission

logger = logging.getLogger(__name__)

INVALID_FILTER_LABELS_JSON = "Invalid filter_labels JSON"
SILENCE_META_PREFIX = "[beobservant-meta]"

router = APIRouter(
    prefix="/api/alertmanager",
    tags=["alertmanager"]
)

webhook_router = APIRouter(tags=["alertmanager-webhooks"])

alertmanager_service = AlertManagerService()
notification_service = NotificationService()
storage_service = DatabaseStorageService()
_mimir_client = httpx.AsyncClient(
    timeout=httpx.Timeout(config.DEFAULT_TIMEOUT),
    limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
)

MIMIR_RULES_NAMESPACE = "beobservant"


def _require_inbound_webhook_token(request: Request) -> None:
    """Optional shared-secret auth for inbound webhook endpoints."""
    if not config.INBOUND_WEBHOOK_TOKEN:
        return
    provided = request.headers.get("x-beobservant-webhook-token")
    if provided != config.INBOUND_WEBHOOK_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook token",
        )


def _normalize_visibility(value: Optional[str]) -> str:
    if isinstance(value, Visibility):
        value = value.value
    if not value:
        return Visibility.PRIVATE.value
    normalized = value.lower()
    if normalized == "public":
        normalized = Visibility.TENANT.value
    if normalized not in {Visibility.PRIVATE.value, Visibility.GROUP.value, Visibility.TENANT.value}:
        raise HTTPException(status_code=400, detail="Invalid visibility value")
    return normalized


def _encode_silence_comment(comment: str, visibility: str, shared_group_ids: List[str]) -> str:
    meta = {
        "visibility": visibility,
        "shared_group_ids": shared_group_ids or []
    }
    payload = json.dumps(meta, separators=(",", ":"))
    return f"{SILENCE_META_PREFIX}{payload}\n{comment}"


def _decode_silence_comment(comment: Optional[str]) -> Dict[str, object]:
    if not comment or not comment.startswith(SILENCE_META_PREFIX):
        return {
            "comment": comment or "",
            "visibility": Visibility.TENANT.value,
            "shared_group_ids": []
        }

    raw = comment[len(SILENCE_META_PREFIX):]
    if "\n" in raw:
        meta_str, comment_text = raw.split("\n", 1)
    else:
        meta_str, comment_text = raw, ""

    try:
        meta = json.loads(meta_str)
    except json.JSONDecodeError:
        return {
            "comment": comment,
            "visibility": Visibility.TENANT.value,
            "shared_group_ids": []
        }

    visibility = _normalize_visibility(meta.get("visibility") or Visibility.TENANT.value)
    shared_group_ids = meta.get("shared_group_ids") or []
    if not isinstance(shared_group_ids, list):
        shared_group_ids = []

    return {
        "comment": comment_text,
        "visibility": visibility,
        "shared_group_ids": shared_group_ids
    }


def _resolve_rule_org_id(rule_org_id: Optional[str], current_user: TokenData) -> str:
    user_org_id = getattr(current_user, "org_id", None)
    return rule_org_id or user_org_id or config.DEFAULT_ORG_ID


def _yaml_quote(value: object) -> str:
    text = str(value)
    escaped = text.replace("\\", "\\\\").replace("\"", "\\\"")
    return f"\"{escaped}\""


def _build_ruler_yaml(rules: List[AlertRule]) -> str:
    groups: Dict[str, List[AlertRule]] = {}
    for rule in rules:
        if not rule.enabled:
            continue
        group_name = rule.group or config.DEFAULT_RULE_GROUP
        groups.setdefault(group_name, []).append(rule)

    if not groups:
        return ""

    lines = ["groups:"]
    for group_name in sorted(groups.keys()):
        lines.append(f"- name: {_yaml_quote(group_name)}")
        lines.append("  rules:")
        for rule in sorted(groups[group_name], key=lambda r: r.name.lower()):
            lines.append(f"  - alert: {_yaml_quote(rule.name)}")
            lines.append(f"    expr: {_yaml_quote(rule.expr)}")
            lines.append(f"    for: {_yaml_quote(rule.duration)}")

            labels = dict(rule.labels or {})
            labels["severity"] = rule.severity
            if labels:
                lines.append("    labels:")
                for key in sorted(labels.keys()):
                    lines.append(f"      {key}: {_yaml_quote(labels[key])}")

            annotations = rule.annotations or {}
            if annotations:
                lines.append("    annotations:")
                for key in sorted(annotations.keys()):
                    lines.append(f"      {key}: {_yaml_quote(annotations[key])}")

    return "\n".join(lines) + "\n"


async def _sync_mimir_rules_for_org(tenant_id: str, org_id: str) -> None:
    rules = storage_service.get_alert_rules_for_org(tenant_id, org_id)
    payload = _build_ruler_yaml(rules)
    headers = {"X-Scope-OrgID": org_id}
    base_url = config.MIMIR_URL.rstrip("/")

    try:
        if payload:
            headers["Content-Type"] = "application/yaml"
            resp = await _mimir_client.post(
                f"{base_url}/api/v1/rules/{MIMIR_RULES_NAMESPACE}",
                content=payload,
                headers=headers,
            )
        else:
            resp = await _mimir_client.delete(
                f"{base_url}/api/v1/rules/{MIMIR_RULES_NAMESPACE}",
                headers=headers,
            )
        if resp.status_code not in {200, 201, 202, 204, 404}:
            raise httpx.HTTPStatusError(
                f"Unexpected Mimir response: {resp.status_code}",
                request=resp.request,
                response=resp,
            )
    except httpx.HTTPError as exc:
        logger.error("Failed to sync rules to Mimir for org_id=%s: %s", org_id, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to sync alert rules to Mimir",
        ) from exc


def _apply_silence_metadata(silence: Silence) -> Silence:
    data = _decode_silence_comment(silence.comment)
    silence.comment = data["comment"]
    silence.visibility = data["visibility"]
    silence.shared_group_ids = data["shared_group_ids"]
    return silence


def _silence_accessible(silence: Silence, current_user: TokenData) -> bool:
    visibility = silence.visibility or Visibility.TENANT.value
    if silence.created_by == current_user.username:
        return True
    if visibility == Visibility.TENANT.value:
        return True
    if visibility == Visibility.GROUP.value:
        user_group_ids = getattr(current_user, "group_ids", []) or []
        return any(gid in silence.shared_group_ids for gid in user_group_ids)
    return False


@webhook_router.post(
    "/alerts/webhook",
    summary="Alert webhook",
    description="Receive alert webhook notifications from AlertManager"
)
async def alert_webhook(request: Request) -> dict:
    """Receive alert webhook notifications from AlertManager based on routing configuration."""
    enforce_ip_rate_limit(
        request,
        scope="alertmanager_webhook",
        limit=config.RATE_LIMIT_PUBLIC_PER_MINUTE,
        window_seconds=60,
    )
    _require_inbound_webhook_token(request)
    try:
        payload = await request.json()
        alerts = payload.get("alerts", [])
        logger.info("Received webhook payload with %d alerts", len(alerts))
        
        for alert in alerts:
            alertname = alert.get('labels', {}).get('alertname', 'unknown')
            alert_status = alert.get('status', 'unknown')
            logger.info("Alert: %s - %s", alertname, alert_status)
        
        return {
            "status": constants.STATUS_SUCCESS,
            "count": len(alerts)
        }
    except Exception as e:
        logger.error("Error processing webhook: %s", e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid webhook payload"
        )


@webhook_router.post(
    "/alerts/critical",
    summary="Critical alerts webhook",
    description="Receive critical severity alerts routed by AlertManager"
)
async def alert_critical(request: Request) -> dict:
    """Receive critical severity alerts routed by AlertManager."""
    enforce_ip_rate_limit(
        request,
        scope="alertmanager_critical",
        limit=config.RATE_LIMIT_PUBLIC_PER_MINUTE,
        window_seconds=60,
    )
    _require_inbound_webhook_token(request)
    try:
        payload = await request.json()
        alerts = payload.get("alerts", [])
        logger.warning("Received %d critical alerts", len(alerts))
        
        for alert in alerts:
            alertname = alert.get('labels', {}).get('alertname', 'unknown')
            logger.warning("Critical Alert: %s", alertname)
        
        return {
            "status": constants.STATUS_SUCCESS,
            "severity": "critical",
            "count": len(alerts)
        }
    except Exception as e:
        logger.error("Error processing critical alerts: %s", e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid payload"
        )


@webhook_router.post(
    "/alerts/warning",
    summary="Warning alerts webhook",
    description="Receive warning severity alerts routed by AlertManager"
)
async def alert_warning(request: Request) -> dict:
    """Receive warning severity alerts routed by AlertManager."""
    enforce_ip_rate_limit(
        request,
        scope="alertmanager_warning",
        limit=config.RATE_LIMIT_PUBLIC_PER_MINUTE,
        window_seconds=60,
    )
    _require_inbound_webhook_token(request)
    try:
        payload = await request.json()
        alerts = payload.get("alerts", [])
        logger.info("Received warning alerts payload with %d alerts", len(alerts))
        for alert in alerts:
            logger.info("Warning Alert: %s", alert.get('labels', {}).get('alertname', 'unknown'))
        
        return {"status": "received", "severity": "warning", "count": len(alerts)}
    except Exception as e:
        logger.error("Error processing warning alerts: %s", e)
        raise HTTPException(status_code=400, detail="Invalid payload")


@router.get("/alerts", response_model=List[Alert])
async def get_alerts(
    active: Optional[bool] = Query(None, description="Filter active alerts"),
    silenced: Optional[bool] = Query(None, description="Filter silenced alerts"),
    inhibited: Optional[bool] = Query(None, description="Filter inhibited alerts"),
    filter_labels: Optional[str] = Query(None, description='Label filters as JSON string, e.g. {"severity":"critical"}'),
    current_user: TokenData = Depends(require_permission(Permission.READ_ALERTS))
):
    """Get all alerts with optional filters.
    
    Returns all alerts from AlertManager, optionally filtered by state and labels.
    """
    labels = None
    if filter_labels:
        try:
            labels = json.loads(filter_labels)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail=INVALID_FILTER_LABELS_JSON)
    
    alerts = await alertmanager_service.get_alerts(
        filter_labels=labels,
        active=active,
        silenced=silenced,
        inhibited=inhibited
    )
    return alerts


@router.get("/alerts/groups", response_model=List[AlertGroup])
async def get_alert_groups(
    filter_labels: Optional[str] = Query(None, description='Label filters as JSON string'),
    current_user: TokenData = Depends(require_permission(Permission.READ_ALERTS))
):
    """Get alert groups.
    
    Returns alerts grouped by their grouping labels.
    """
    labels = None
    if filter_labels:
        try:
            labels = json.loads(filter_labels)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail=INVALID_FILTER_LABELS_JSON)
    
    groups = await alertmanager_service.get_alert_groups(filter_labels=labels)
    return groups


@router.post("/alerts")
async def post_alerts(
    alerts: List[Alert] = Body(..., description="List of alerts to post"),
    current_user: TokenData = Depends(require_permission(Permission.WRITE_ALERTS))
):
    """Post new alerts to AlertManager.
    
    Creates or updates alerts in AlertManager. Used for testing or manual alert creation.
    """
    success = await alertmanager_service.post_alerts(alerts)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to post alerts")
    return {"status": "success", "count": len(alerts)}


@router.delete("/alerts")
async def delete_alerts(
    filter_labels: str = Query(..., description='Label filters as JSON string, e.g. {"alertname":"test"}'),
    current_user: TokenData = Depends(require_permission(Permission.DELETE_ALERTS))
):
    """Delete alerts matching the filter.
    
    Creates a short silence to suppress matching alerts (AlertManager doesn't support direct deletion).
    """
    try:
        labels = json.loads(filter_labels)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail=INVALID_FILTER_LABELS_JSON)
    
    if not labels:
        raise HTTPException(status_code=400, detail="filter_labels cannot be empty")
    
    success = await alertmanager_service.delete_alerts(filter_labels=labels)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete alerts")
    return {"status": "success", "message": "Alerts silenced"}


@router.get("/silences", response_model=List[Silence])
async def get_silences(
    filter_labels: Optional[str] = Query(None, description='Label filters as JSON string'),
    current_user: TokenData = Depends(require_permission(Permission.READ_ALERTS))
):
    """Get all silences.
    
    Returns all active and expired silences, optionally filtered by labels.
    """
    labels = None
    if filter_labels:
        try:
            labels = json.loads(filter_labels)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail=INVALID_FILTER_LABELS_JSON)
    
    silences = await alertmanager_service.get_silences(filter_labels=labels)
    visible_silences = []
    for silence in silences:
        silence = _apply_silence_metadata(silence)
        if _silence_accessible(silence, current_user):
            visible_silences.append(silence)
    return visible_silences


@router.get("/silences/{silence_id}", response_model=Silence)
async def get_silence(
    silence_id: str,
    current_user: TokenData = Depends(require_permission(Permission.READ_ALERTS))
):
    """Get a specific silence by ID.
    
    Returns detailed information about a single silence.
    """
    silence = await alertmanager_service.get_silence(silence_id)
    if not silence:
        raise HTTPException(status_code=404, detail=f"Silence {silence_id} not found")
    silence = _apply_silence_metadata(silence)
    if not _silence_accessible(silence, current_user):
        raise HTTPException(status_code=404, detail=f"Silence {silence_id} not found")
    return silence


@router.post("/silences", response_model=Dict[str, str])
async def create_silence(
    silence: SilenceCreateRequest = Body(..., description="Silence configuration"),
    current_user: TokenData = Depends(require_permission(Permission.WRITE_ALERTS))
):
    """Create a new silence.
    
    Creates a silence that will suppress alerts matching the specified matchers.
    """
    visibility = _normalize_visibility(silence.visibility)
    shared_group_ids = silence.shared_group_ids if visibility == Visibility.GROUP.value else []
    comment = _encode_silence_comment(silence.comment, visibility, shared_group_ids)
    created_by = current_user.username or current_user.user_id

    payload = SilenceCreate(
        matchers=silence.matchers,
        starts_at=silence.starts_at,
        ends_at=silence.ends_at,
        created_by=created_by,
        comment=comment
    )

    silence_id = await alertmanager_service.create_silence(payload)
    if not silence_id:
        raise HTTPException(status_code=500, detail="Failed to create silence")
    return {"silenceID": silence_id, "status": "success"}


@router.put("/silences/{silence_id}", response_model=Dict[str, str])
async def update_silence(
    silence_id: str,
    silence: SilenceCreateRequest = Body(..., description="Updated silence configuration"),
    current_user: TokenData = Depends(require_permission(Permission.WRITE_ALERTS))
):
    """Update an existing silence.
    
    Deletes the old silence and creates a new one with the updated configuration.
    """
    existing = await alertmanager_service.get_silence(silence_id)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Silence {silence_id} not found")
    existing = _apply_silence_metadata(existing)
    if not _silence_accessible(existing, current_user):
        raise HTTPException(status_code=404, detail=f"Silence {silence_id} not found")

    visibility = _normalize_visibility(silence.visibility)
    shared_group_ids = silence.shared_group_ids if visibility == Visibility.GROUP.value else []
    comment = _encode_silence_comment(silence.comment, visibility, shared_group_ids)
    created_by = current_user.username or current_user.user_id

    payload = SilenceCreate(
        matchers=silence.matchers,
        starts_at=silence.starts_at,
        ends_at=silence.ends_at,
        created_by=created_by,
        comment=comment
    )

    new_id = await alertmanager_service.update_silence(silence_id, payload)
    if not new_id:
        raise HTTPException(status_code=500, detail="Failed to update silence")
    return {"silenceID": new_id, "status": "success", "message": "Silence updated"}


@router.delete("/silences/{silence_id}")
async def delete_silence(
    silence_id: str,
    current_user: TokenData = Depends(require_permission(Permission.DELETE_ALERTS))
):
    """Delete a silence.
    
    Immediately expires the specified silence.
    """
    existing = await alertmanager_service.get_silence(silence_id)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Silence {silence_id} not found or already deleted")
    existing = _apply_silence_metadata(existing)
    if not _silence_accessible(existing, current_user):
        raise HTTPException(status_code=404, detail=f"Silence {silence_id} not found or already deleted")

    success = await alertmanager_service.delete_silence(silence_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Silence {silence_id} not found or already deleted")
    return {"status": "success", "message": f"Silence {silence_id} deleted"}


@router.get("/status", response_model=AlertManagerStatus)
async def get_status(current_user: TokenData = Depends(require_permission(Permission.READ_ALERTS))):
    """Get AlertManager status.
    
    Returns AlertManager version, configuration, and cluster information.
    """
    status = await alertmanager_service.get_status()
    if not status:
        raise HTTPException(status_code=500, detail="Failed to fetch AlertManager status")
    return status


@router.get("/receivers", response_model=List[str])
async def get_receivers(current_user: TokenData = Depends(require_permission(Permission.READ_ALERTS))):
    """Get list of configured receivers.
    
    Returns names of all alert receivers configured in AlertManager.
    """
    receivers = await alertmanager_service.get_receivers()
    return receivers


@router.get("/rules", response_model=List[AlertRule])
async def get_alert_rules(current_user: TokenData = Depends(require_permission(Permission.READ_ALERTS))):
    """Get all alert rules.
    
    Returns all configured alert rules accessible to the user.
    """
    tenant_id = current_user.tenant_id
    user_id = current_user.user_id
    group_ids = getattr(current_user, 'group_ids', []) or []
    rules = storage_service.get_alert_rules(tenant_id, user_id, group_ids)
    return rules


@router.get("/metrics/names")
async def list_metric_names(
    org_id: Optional[str] = Query(
        None,
        alias="orgId",
        description=(
            "API key value / org_id to scope metrics to. "
            "If omitted, falls back to the current user's org_id."
        ),
    ),
    current_user: TokenData = Depends(require_permission(Permission.WRITE_ALERTS)),
):
    """List metric names from Mimir for assisted rule creation.

    Uses the configured Mimir Prometheus-compatible API and scopes the
    query via ``X-Scope-OrgID`` so that each product / API key only sees
    its own metrics.
    """
    tenant_org_id = org_id or getattr(current_user, "org_id", None)
    if not tenant_org_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No org_id available to query metrics. Set a product / API key first.",
        )

    try:
        resp = await _mimir_client.get(
            f"{config.MIMIR_URL.rstrip('/')}/prometheus/api/v1/label/__name__/values",
            headers={"X-Scope-OrgID": tenant_org_id},
        )
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        logger.error("Error querying Mimir metric names for org_id=%s: %s", tenant_org_id, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to fetch metrics from Mimir",
        ) from exc

    payload = resp.json()
    status_val = payload.get("status")
    if status_val != "success":
        logger.error("Unexpected Mimir response status for org_id=%s: %s", tenant_org_id, status_val)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Mimir returned an error while listing metrics",
        )

    metrics = payload.get("data") or []
    if not isinstance(metrics, list):
        metrics = []

    return {"orgId": tenant_org_id, "metrics": metrics}


@router.get("/rules/{rule_id}", response_model=AlertRule)
async def get_alert_rule(rule_id: str, current_user: TokenData = Depends(require_permission(Permission.READ_ALERTS))):
    """Get a specific alert rule by ID.
    
    Returns detailed information about a single alert rule.
    """
    tenant_id = current_user.tenant_id
    user_id = current_user.user_id
    group_ids = getattr(current_user, 'group_ids', []) or []
    rule = storage_service.get_alert_rule(rule_id, tenant_id, user_id, group_ids)
    if not rule:
        raise HTTPException(status_code=404, detail=f"Alert rule {rule_id} not found")
    return rule


@router.post("/rules", response_model=AlertRule, status_code=status.HTTP_201_CREATED)
async def create_alert_rule(
    rule: AlertRuleCreate = Body(..., description="Alert rule configuration"),
    current_user: TokenData = Depends(require_permission(Permission.WRITE_ALERTS))
):
    """Create a new alert rule.
    
    Creates a new alert rule that will be evaluated by Prometheus.
    Supports visibility settings: private, group, or tenant.
    """
    tenant_id = current_user.tenant_id
    user_id = current_user.user_id
    group_ids = getattr(current_user, 'group_ids', []) or []
    resolved_org_id = _resolve_rule_org_id(rule.org_id, current_user)
    if rule.org_id != resolved_org_id:
        rule = rule.model_copy(update={"org_id": resolved_org_id})
    created_rule = storage_service.create_alert_rule(rule, tenant_id, user_id, group_ids)
    await _sync_mimir_rules_for_org(tenant_id, created_rule.org_id or resolved_org_id)
    return created_rule


@router.put("/rules/{rule_id}", response_model=AlertRule)
async def update_alert_rule(
    rule_id: str,
    rule: AlertRuleCreate = Body(..., description="Updated rule configuration"),
    current_user: TokenData = Depends(require_permission(Permission.WRITE_ALERTS))
):
    """Update an existing alert rule.
    
    Updates the configuration of an existing alert rule.
    Can update visibility settings and shared groups.
    """
    tenant_id = current_user.tenant_id
    user_id = current_user.user_id
    group_ids = getattr(current_user, 'group_ids', []) or []
    existing_rule = storage_service.get_alert_rule(rule_id, tenant_id, user_id, group_ids)
    if not existing_rule:
        raise HTTPException(status_code=404, detail=f"Alert rule {rule_id} not found or access denied")

    resolved_org_id = _resolve_rule_org_id(rule.org_id, current_user)
    if rule.org_id != resolved_org_id:
        rule = rule.model_copy(update={"org_id": resolved_org_id})

    updated_rule = storage_service.update_alert_rule(rule_id, rule, tenant_id, user_id, group_ids)
    if not updated_rule:
        raise HTTPException(status_code=404, detail=f"Alert rule {rule_id} not found or access denied")

    await _sync_mimir_rules_for_org(tenant_id, updated_rule.org_id or resolved_org_id)
    if existing_rule.org_id and existing_rule.org_id != updated_rule.org_id:
        await _sync_mimir_rules_for_org(tenant_id, existing_rule.org_id)

    return updated_rule


@router.post("/rules/{rule_id}/test")
async def test_alert_rule(rule_id: str, current_user: TokenData = Depends(require_permission(Permission.WRITE_ALERTS))):
    """Send a test notification for an alert rule to its configured channels.

    This does not require Prometheus evaluation and is meant for validation.
    """
    tenant_id = current_user.tenant_id
    user_id = current_user.user_id
    group_ids = getattr(current_user, 'group_ids', []) or []
    rule = storage_service.get_alert_rule(rule_id, tenant_id, user_id, group_ids)
    if not rule:
        raise HTTPException(status_code=404, detail=f"Alert rule {rule_id} not found")

    channels = storage_service.get_notification_channels(tenant_id, user_id, group_ids)
    if rule.notification_channels:
        channels = [c for c in channels if c.id in rule.notification_channels]

    if not channels:
        raise HTTPException(status_code=400, detail="No notification channels configured for this rule")

    alert = Alert(
        labels={
            "alertname": rule.name,
            "severity": rule.severity,
            **(rule.labels or {})
        },
        annotations={
            "summary": rule.annotations.get("summary", f"Test alert for {rule.name}"),
            "description": rule.annotations.get("description", rule.expr),
            **(rule.annotations or {})
        },
        startsAt=datetime.now(timezone.utc).isoformat(),
        status=AlertStatus(state=AlertState.ACTIVE, silencedBy=[], inhibitedBy=[]),
        fingerprint=f"test-{rule.id}"
    )

    results = []
    success_count = 0
    for channel in channels:
        try:
            ok = await notification_service.send_notification(channel, alert, "firing")
            results.append({"channel": channel.name, "ok": ok})
            if ok:
                success_count += 1
        except Exception as e:
            results.append({"channel": channel.name, "ok": False, "error": str(e)})

    return {
        "status": "success" if success_count else "failed",
        "message": f"Test alert sent to {success_count}/{len(channels)} channels",
        "results": results
    }


@router.delete("/rules/{rule_id}")
async def delete_alert_rule(rule_id: str, current_user: TokenData = Depends(require_permission(Permission.DELETE_ALERTS))):
    """Delete an alert rule.
    
    Removes an alert rule from the configuration. Only the owner can delete.
    """
    tenant_id = current_user.tenant_id
    user_id = current_user.user_id
    group_ids = getattr(current_user, 'group_ids', []) or []
    existing_rule = storage_service.get_alert_rule(rule_id, tenant_id, user_id, group_ids)
    if not existing_rule:
        raise HTTPException(status_code=404, detail=f"Alert rule {rule_id} not found or access denied")

    success = storage_service.delete_alert_rule(rule_id, tenant_id, user_id, group_ids)
    if not success:
        raise HTTPException(status_code=404, detail=f"Alert rule {rule_id} not found or access denied")

    resolved_org_id = _resolve_rule_org_id(existing_rule.org_id, current_user)
    await _sync_mimir_rules_for_org(tenant_id, resolved_org_id)
    return {"status": "success", "message": f"Alert rule {rule_id} deleted"}


@router.get("/channels", response_model=List[NotificationChannel])
async def get_notification_channels(current_user: TokenData = Depends(require_permission(Permission.READ_CHANNELS))):
    """Get all notification channels.
    
    Returns all configured notification channels accessible to the user.
    """
    tenant_id = current_user.tenant_id
    user_id = current_user.user_id
    group_ids = getattr(current_user, 'group_ids', []) or []
    channels = storage_service.get_notification_channels(tenant_id, user_id, group_ids)
    return channels


@router.get("/channels/{channel_id}", response_model=NotificationChannel)
async def get_notification_channel(channel_id: str, current_user: TokenData = Depends(require_permission(Permission.READ_CHANNELS))):
    """Get a specific notification channel by ID.
    
    Returns detailed information about a single notification channel.
    """
    tenant_id = current_user.tenant_id
    user_id = current_user.user_id
    group_ids = getattr(current_user, 'group_ids', []) or []
    channel = storage_service.get_notification_channel(channel_id, tenant_id, user_id, group_ids)
    if not channel:
        raise HTTPException(status_code=404, detail=f"Notification channel {channel_id} not found")
    return channel


@router.post("/channels", response_model=NotificationChannel, status_code=status.HTTP_201_CREATED)
async def create_notification_channel(
    channel: NotificationChannelCreate = Body(..., description="Notification channel configuration"),
    current_user: TokenData = Depends(require_permission(Permission.WRITE_CHANNELS))
):
    """Create a new notification channel.
    
    Creates a new notification channel for alert delivery.
    Supports visibility settings: private, group, or tenant.
    """
    tenant_id = current_user.tenant_id
    user_id = current_user.user_id
    group_ids = getattr(current_user, 'group_ids', []) or []
    created_channel = storage_service.create_notification_channel(channel, tenant_id, user_id, group_ids)
    return created_channel


@router.put("/channels/{channel_id}", response_model=NotificationChannel)
async def update_notification_channel(
    channel_id: str,
    channel: NotificationChannelCreate = Body(..., description="Updated channel configuration"),
    current_user: TokenData = Depends(require_permission(Permission.WRITE_CHANNELS))
):
    """Update an existing notification channel.
    
    Updates the configuration of an existing notification channel.
    Can update visibility settings and shared groups.
    """
    tenant_id = current_user.tenant_id
    user_id = current_user.user_id
    group_ids = getattr(current_user, 'group_ids', []) or []
    updated_channel = storage_service.update_notification_channel(channel_id, channel, tenant_id, user_id, group_ids)
    if not updated_channel:
        raise HTTPException(status_code=404, detail=f"Notification channel {channel_id} not found or access denied")
    return updated_channel


@router.delete("/channels/{channel_id}")
async def delete_notification_channel(channel_id: str, current_user: TokenData = Depends(require_permission(Permission.DELETE_CHANNELS))):
    """Delete a notification channel.
    
    Removes a notification channel from the configuration. Only the owner can delete.
    """
    tenant_id = current_user.tenant_id
    user_id = current_user.user_id
    group_ids = getattr(current_user, 'group_ids', []) or []
    success = storage_service.delete_notification_channel(channel_id, tenant_id, user_id, group_ids)
    if not success:
        raise HTTPException(status_code=404, detail=f"Notification channel {channel_id} not found or access denied")
    return {"status": "success", "message": f"Notification channel {channel_id} deleted"}


@router.post("/channels/{channel_id}/test")
async def test_notification_channel(channel_id: str, current_user: TokenData = Depends(require_permission(Permission.WRITE_CHANNELS))):
    """Test a notification channel.
    
    Sends a test notification through the specified channel.
    """
    tenant_id = current_user.tenant_id
    user_id = current_user.user_id
    group_ids = getattr(current_user, 'group_ids', []) or []
    channel = storage_service.get_notification_channel(channel_id, tenant_id, user_id, group_ids)
    if not channel:
        raise HTTPException(status_code=404, detail=f"Notification channel {channel_id} not found")
    
    test_alert = Alert(
        labels={"alertname": "InvokableTestAlert", "severity": "INFO"},
        annotations={"summary": "You have invoked a test alert", "description": "This is a test notification from BeObservant, Please ignore this alert, if you didn't expect it."},
        startsAt=datetime.now().astimezone().isoformat(),
        status={"state": "active", "silencedBy": [], "inhibitedBy": []},
        fingerprint="test"
    )

    try:
        success = await notification_service.send_notification(channel, test_alert, "firing")
        if success:
            return {"status": "success", "message": f"Test notification sent to {channel.name}"}
        else:
            raise HTTPException(status_code=500, detail="Failed to send test notification")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error sending test notification: {str(e)}")


__all__ = ["router", "webhook_router"]