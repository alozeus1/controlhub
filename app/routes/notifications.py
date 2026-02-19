"""
Notification Routes

Endpoints for managing notification channels, alert rules, and viewing alert history.
Feature-flagged: FEATURE_NOTIFICATIONS
"""
from flask import Blueprint, jsonify, request, current_app

from app.utils.rbac import require_role
from app.services.notifications import (
    NotificationChannelService,
    AlertRuleService,
    AlertEventService,
    SUPPORTED_EVENT_TYPES,
    SEVERITY_LEVELS,
    CHANNEL_TYPES,
)

notifications_bp = Blueprint("notifications", __name__)


def check_feature_enabled():
    """Check if notifications feature is enabled."""
    if not current_app.config.get("FEATURE_NOTIFICATIONS", False):
        return jsonify({
            "error": "Notifications feature is not enabled",
            "code": "FEATURE_DISABLED"
        }), 403
    return None


# =============================================================================
# NOTIFICATION CHANNEL ENDPOINTS
# =============================================================================

@notifications_bp.get("/notification-channels")
@require_role("admin")
def list_channels():
    """List all notification channels."""
    error = check_feature_enabled()
    if error:
        return error

    page = request.args.get("page", 1, type=int)
    page_size = min(request.args.get("page_size", 20, type=int), 100)
    channel_type = request.args.get("type")
    is_enabled = request.args.get("is_enabled")

    is_enabled_bool = None
    if is_enabled is not None:
        is_enabled_bool = is_enabled.lower() == "true"

    result = NotificationChannelService.list_channels(
        page=page,
        page_size=page_size,
        channel_type=channel_type,
        is_enabled=is_enabled_bool,
    )
    return jsonify(result)


@notifications_bp.get("/notification-channels/<int:channel_id>")
@require_role("admin")
def get_channel(channel_id):
    """Get a single notification channel."""
    error = check_feature_enabled()
    if error:
        return error

    channel = NotificationChannelService.get_channel(channel_id)
    if not channel:
        return jsonify({"error": "Channel not found"}), 404

    return jsonify(channel.to_dict())


@notifications_bp.post("/notification-channels")
@require_role("admin")
def create_channel():
    """Create a new notification channel."""
    error = check_feature_enabled()
    if error:
        return error

    actor = request.current_user
    data = request.get_json()

    channel_type = data.get("type", "").strip()
    name = data.get("name", "").strip()
    config = data.get("config", {})

    if not channel_type:
        return jsonify({"error": "Channel type is required"}), 400
    if not name:
        return jsonify({"error": "Channel name is required"}), 400
    if not config:
        return jsonify({"error": "Channel config is required"}), 400

    try:
        channel = NotificationChannelService.create_channel(
            channel_type=channel_type,
            name=name,
            config=config,
            actor=actor,
        )
        return jsonify({
            "message": "Notification channel created",
            "channel": channel.to_dict(),
        }), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@notifications_bp.patch("/notification-channels/<int:channel_id>")
@require_role("admin")
def update_channel(channel_id):
    """Update a notification channel."""
    error = check_feature_enabled()
    if error:
        return error

    channel = NotificationChannelService.get_channel(channel_id)
    if not channel:
        return jsonify({"error": "Channel not found"}), 404

    actor = request.current_user
    data = request.get_json()

    try:
        channel = NotificationChannelService.update_channel(
            channel=channel,
            actor=actor,
            name=data.get("name"),
            config=data.get("config"),
            is_enabled=data.get("is_enabled"),
        )
        return jsonify({
            "message": "Channel updated",
            "channel": channel.to_dict(),
        })
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@notifications_bp.delete("/notification-channels/<int:channel_id>")
@require_role("admin")
def delete_channel(channel_id):
    """Delete a notification channel."""
    error = check_feature_enabled()
    if error:
        return error

    channel = NotificationChannelService.get_channel(channel_id)
    if not channel:
        return jsonify({"error": "Channel not found"}), 404

    actor = request.current_user
    NotificationChannelService.delete_channel(channel, actor)

    return jsonify({"message": "Channel deleted"})


@notifications_bp.post("/notification-channels/<int:channel_id>/test")
@require_role("admin")
def test_channel(channel_id):
    """Send a test notification to verify channel configuration."""
    error = check_feature_enabled()
    if error:
        return error

    channel = NotificationChannelService.get_channel(channel_id)
    if not channel:
        return jsonify({"error": "Channel not found"}), 404

    result = NotificationChannelService.test_channel(channel)
    
    if result.get("success"):
        return jsonify({"message": "Test notification sent", "details": result})
    else:
        return jsonify({"error": "Test failed", "details": result}), 400


# =============================================================================
# ALERT RULE ENDPOINTS
# =============================================================================

@notifications_bp.get("/alert-rules")
@require_role("admin")
def list_rules():
    """List all alert rules."""
    error = check_feature_enabled()
    if error:
        return error

    page = request.args.get("page", 1, type=int)
    page_size = min(request.args.get("page_size", 20, type=int), 100)
    event_type = request.args.get("event_type")
    is_enabled = request.args.get("is_enabled")

    is_enabled_bool = None
    if is_enabled is not None:
        is_enabled_bool = is_enabled.lower() == "true"

    result = AlertRuleService.list_rules(
        page=page,
        page_size=page_size,
        event_type=event_type,
        is_enabled=is_enabled_bool,
    )
    return jsonify(result)


@notifications_bp.get("/alert-rules/<int:rule_id>")
@require_role("admin")
def get_rule(rule_id):
    """Get a single alert rule."""
    error = check_feature_enabled()
    if error:
        return error

    rule = AlertRuleService.get_rule(rule_id)
    if not rule:
        return jsonify({"error": "Rule not found"}), 404

    return jsonify(rule.to_dict())


@notifications_bp.post("/alert-rules")
@require_role("admin")
def create_rule():
    """Create a new alert rule."""
    error = check_feature_enabled()
    if error:
        return error

    actor = request.current_user
    data = request.get_json()

    name = data.get("name", "").strip()
    event_type = data.get("event_type", "").strip()
    channel_ids = data.get("channel_ids", [])

    if not name:
        return jsonify({"error": "Rule name is required"}), 400
    if not event_type:
        return jsonify({"error": "Event type is required"}), 400
    if not channel_ids:
        return jsonify({"error": "At least one channel is required"}), 400

    try:
        rule = AlertRuleService.create_rule(
            name=name,
            event_type=event_type,
            channel_ids=channel_ids,
            actor=actor,
            description=data.get("description"),
            severity=data.get("severity", "medium"),
            conditions=data.get("conditions"),
        )
        return jsonify({
            "message": "Alert rule created",
            "rule": rule.to_dict(),
        }), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@notifications_bp.patch("/alert-rules/<int:rule_id>")
@require_role("admin")
def update_rule(rule_id):
    """Update an alert rule."""
    error = check_feature_enabled()
    if error:
        return error

    rule = AlertRuleService.get_rule(rule_id)
    if not rule:
        return jsonify({"error": "Rule not found"}), 404

    actor = request.current_user
    data = request.get_json()

    try:
        rule = AlertRuleService.update_rule(
            rule=rule,
            actor=actor,
            name=data.get("name"),
            description=data.get("description"),
            severity=data.get("severity"),
            conditions=data.get("conditions"),
            channel_ids=data.get("channel_ids"),
            is_enabled=data.get("is_enabled"),
        )
        return jsonify({
            "message": "Rule updated",
            "rule": rule.to_dict(),
        })
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@notifications_bp.delete("/alert-rules/<int:rule_id>")
@require_role("admin")
def delete_rule(rule_id):
    """Delete an alert rule."""
    error = check_feature_enabled()
    if error:
        return error

    rule = AlertRuleService.get_rule(rule_id)
    if not rule:
        return jsonify({"error": "Rule not found"}), 404

    actor = request.current_user
    AlertRuleService.delete_rule(rule, actor)

    return jsonify({"message": "Rule deleted"})


# =============================================================================
# ALERT EVENT ENDPOINTS
# =============================================================================

@notifications_bp.get("/alerts")
@require_role("admin")
def list_alerts():
    """List alert history."""
    error = check_feature_enabled()
    if error:
        return error

    page = request.args.get("page", 1, type=int)
    page_size = min(request.args.get("page_size", 50, type=int), 100)
    event_type = request.args.get("event_type")
    severity = request.args.get("severity")
    delivery_status = request.args.get("delivery_status")

    result = AlertEventService.list_events(
        page=page,
        page_size=page_size,
        event_type=event_type,
        severity=severity,
        delivery_status=delivery_status,
    )
    return jsonify(result)


@notifications_bp.get("/alerts/<int:event_id>")
@require_role("admin")
def get_alert(event_id):
    """Get a single alert event."""
    error = check_feature_enabled()
    if error:
        return error

    event = AlertEventService.get_event(event_id)
    if not event:
        return jsonify({"error": "Alert event not found"}), 404

    return jsonify(event.to_dict())


# =============================================================================
# METADATA ENDPOINTS
# =============================================================================

@notifications_bp.get("/notifications/metadata")
@require_role("admin")
def get_metadata():
    """Get notification system metadata (event types, severities, channel types)."""
    error = check_feature_enabled()
    if error:
        return error

    return jsonify({
        "event_types": SUPPORTED_EVENT_TYPES,
        "severity_levels": SEVERITY_LEVELS,
        "channel_types": CHANNEL_TYPES,
    })


@notifications_bp.get("/notifications/status")
@require_role("admin")
def get_status():
    """Get notification system status."""
    error = check_feature_enabled()
    if error:
        return error

    from app.models import NotificationChannel, AlertRule, AlertEvent

    total_channels = NotificationChannel.query.count()
    enabled_channels = NotificationChannel.query.filter_by(is_enabled=True).count()
    total_rules = AlertRule.query.count()
    enabled_rules = AlertRule.query.filter_by(is_enabled=True).count()
    total_alerts = AlertEvent.query.count()
    failed_alerts = AlertEvent.query.filter_by(delivery_status="failed").count()

    return jsonify({
        "channels": {"total": total_channels, "enabled": enabled_channels},
        "rules": {"total": total_rules, "enabled": enabled_rules},
        "alerts": {"total": total_alerts, "failed": failed_alerts},
    })
