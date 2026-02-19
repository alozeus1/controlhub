"""
Notification Service Layer

Business logic for notification channels, alert rules, and event delivery.
"""
import json
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any
from urllib.parse import urlparse

import requests

from app.extensions import db
from app.models import NotificationChannel, AlertRule, AlertEvent, User
from app.utils.audit import log_action

logger = logging.getLogger(__name__)

# Supported event types that can trigger alerts
SUPPORTED_EVENT_TYPES = [
    "job.failed",
    "job.completed",
    "user.created",
    "user.disabled",
    "user.role_changed",
    "upload.created",
    "upload.deleted",
    "approval.requested",
    "approval.approved",
    "approval.rejected",
    "service_account.created",
    "api_key.created",
    "api_key.revoked",
    "policy.violated",
]

SEVERITY_LEVELS = ["low", "medium", "high", "critical"]
CHANNEL_TYPES = ["email", "slack", "webhook"]


class NotificationChannelService:
    """Service for managing notification channels."""

    @staticmethod
    def list_channels(
        page: int = 1,
        page_size: int = 20,
        channel_type: Optional[str] = None,
        is_enabled: Optional[bool] = None,
    ) -> dict:
        """List notification channels with pagination and filters."""
        query = NotificationChannel.query

        if channel_type:
            query = query.filter(NotificationChannel.type == channel_type)

        if is_enabled is not None:
            query = query.filter(NotificationChannel.is_enabled == is_enabled)

        query = query.order_by(NotificationChannel.created_at.desc())
        pagination = query.paginate(page=page, per_page=page_size, error_out=False)

        return {
            "items": [ch.to_dict() for ch in pagination.items],
            "total": pagination.total,
            "page": pagination.page,
            "page_size": pagination.per_page,
            "pages": pagination.pages,
        }

    @staticmethod
    def get_channel(channel_id: int) -> Optional[NotificationChannel]:
        """Get a notification channel by ID."""
        return NotificationChannel.query.get(channel_id)

    @staticmethod
    def create_channel(
        channel_type: str,
        name: str,
        config: Dict[str, Any],
        actor: User,
    ) -> NotificationChannel:
        """Create a new notification channel."""
        if channel_type not in CHANNEL_TYPES:
            raise ValueError(f"Unsupported channel type: {channel_type}")

        # Validate config based on type
        NotificationChannelService._validate_config(channel_type, config)

        channel = NotificationChannel(
            type=channel_type,
            name=name,
            config=config,
            is_enabled=True,
            created_by_id=actor.id,
        )
        db.session.add(channel)
        db.session.commit()

        log_action(
            action="notification_channel.created",
            actor=actor,
            target_type="notification_channel",
            target_id=channel.id,
            target_label=channel.name,
            details={"type": channel_type},
        )

        return channel

    @staticmethod
    def update_channel(
        channel: NotificationChannel,
        actor: User,
        name: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
        is_enabled: Optional[bool] = None,
    ) -> NotificationChannel:
        """Update a notification channel."""
        changes = {}

        if name is not None and name != channel.name:
            changes["name"] = {"from": channel.name, "to": name}
            channel.name = name

        if config is not None:
            NotificationChannelService._validate_config(channel.type, config)
            changes["config"] = "updated"
            channel.config = config

        if is_enabled is not None and is_enabled != channel.is_enabled:
            changes["is_enabled"] = {"from": channel.is_enabled, "to": is_enabled}
            channel.is_enabled = is_enabled

        if changes:
            db.session.commit()
            log_action(
                action="notification_channel.updated",
                actor=actor,
                target_type="notification_channel",
                target_id=channel.id,
                target_label=channel.name,
                details=changes,
            )

        return channel

    @staticmethod
    def delete_channel(channel: NotificationChannel, actor: User) -> None:
        """Delete a notification channel."""
        channel_name = channel.name
        channel_id = channel.id

        db.session.delete(channel)
        db.session.commit()

        log_action(
            action="notification_channel.deleted",
            actor=actor,
            target_type="notification_channel",
            target_id=channel_id,
            target_label=channel_name,
        )

    @staticmethod
    def test_channel(channel: NotificationChannel) -> Dict[str, Any]:
        """Send a test notification to verify channel configuration."""
        test_payload = {
            "title": "Test Notification",
            "message": "This is a test notification from ControlHub.",
            "severity": "low",
            "timestamp": datetime.utcnow().isoformat(),
        }

        try:
            result = NotificationDeliveryService.deliver_to_channel(channel, test_payload)
            return {"success": result.get("success", False), "details": result}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @staticmethod
    def _validate_config(channel_type: str, config: Dict[str, Any]) -> None:
        """Validate channel configuration based on type."""
        if channel_type == "email":
            if not config.get("recipients"):
                raise ValueError("Email channel requires 'recipients' list")
            recipients = config["recipients"]
            if not isinstance(recipients, list) or len(recipients) == 0:
                raise ValueError("Email channel requires at least one recipient")

        elif channel_type == "slack":
            if not config.get("webhook_url"):
                raise ValueError("Slack channel requires 'webhook_url'")
            url = config["webhook_url"]
            parsed = urlparse(url)
            if not parsed.scheme or not parsed.netloc:
                raise ValueError("Invalid webhook URL")

        elif channel_type == "webhook":
            if not config.get("url"):
                raise ValueError("Webhook channel requires 'url'")
            url = config["url"]
            parsed = urlparse(url)
            if not parsed.scheme or not parsed.netloc:
                raise ValueError("Invalid webhook URL")


class AlertRuleService:
    """Service for managing alert rules."""

    @staticmethod
    def list_rules(
        page: int = 1,
        page_size: int = 20,
        event_type: Optional[str] = None,
        is_enabled: Optional[bool] = None,
    ) -> dict:
        """List alert rules with pagination and filters."""
        query = AlertRule.query

        if event_type:
            query = query.filter(AlertRule.event_type == event_type)

        if is_enabled is not None:
            query = query.filter(AlertRule.is_enabled == is_enabled)

        query = query.order_by(AlertRule.created_at.desc())
        pagination = query.paginate(page=page, per_page=page_size, error_out=False)

        return {
            "items": [rule.to_dict() for rule in pagination.items],
            "total": pagination.total,
            "page": pagination.page,
            "page_size": pagination.per_page,
            "pages": pagination.pages,
        }

    @staticmethod
    def get_rule(rule_id: int) -> Optional[AlertRule]:
        """Get an alert rule by ID."""
        return AlertRule.query.get(rule_id)

    @staticmethod
    def create_rule(
        name: str,
        event_type: str,
        channel_ids: List[int],
        actor: User,
        description: Optional[str] = None,
        severity: str = "medium",
        conditions: Optional[Dict[str, Any]] = None,
    ) -> AlertRule:
        """Create a new alert rule."""
        if event_type not in SUPPORTED_EVENT_TYPES:
            raise ValueError(f"Unsupported event type: {event_type}")

        if severity not in SEVERITY_LEVELS:
            raise ValueError(f"Invalid severity: {severity}")

        # Validate channel IDs exist
        for cid in channel_ids:
            channel = NotificationChannel.query.get(cid)
            if not channel:
                raise ValueError(f"Channel {cid} not found")

        rule = AlertRule(
            name=name,
            description=description,
            event_type=event_type,
            severity=severity,
            conditions=conditions,
            channel_ids=channel_ids,
            is_enabled=True,
            created_by_id=actor.id,
        )
        db.session.add(rule)
        db.session.commit()

        log_action(
            action="alert_rule.created",
            actor=actor,
            target_type="alert_rule",
            target_id=rule.id,
            target_label=rule.name,
            details={"event_type": event_type, "severity": severity},
        )

        return rule

    @staticmethod
    def update_rule(
        rule: AlertRule,
        actor: User,
        name: Optional[str] = None,
        description: Optional[str] = None,
        severity: Optional[str] = None,
        conditions: Optional[Dict[str, Any]] = None,
        channel_ids: Optional[List[int]] = None,
        is_enabled: Optional[bool] = None,
    ) -> AlertRule:
        """Update an alert rule."""
        changes = {}

        if name is not None and name != rule.name:
            changes["name"] = {"from": rule.name, "to": name}
            rule.name = name

        if description is not None:
            rule.description = description

        if severity is not None and severity != rule.severity:
            if severity not in SEVERITY_LEVELS:
                raise ValueError(f"Invalid severity: {severity}")
            changes["severity"] = {"from": rule.severity, "to": severity}
            rule.severity = severity

        if conditions is not None:
            rule.conditions = conditions

        if channel_ids is not None:
            for cid in channel_ids:
                if not NotificationChannel.query.get(cid):
                    raise ValueError(f"Channel {cid} not found")
            changes["channel_ids"] = "updated"
            rule.channel_ids = channel_ids

        if is_enabled is not None and is_enabled != rule.is_enabled:
            changes["is_enabled"] = {"from": rule.is_enabled, "to": is_enabled}
            rule.is_enabled = is_enabled

        if changes:
            db.session.commit()
            log_action(
                action="alert_rule.updated",
                actor=actor,
                target_type="alert_rule",
                target_id=rule.id,
                target_label=rule.name,
                details=changes,
            )

        return rule

    @staticmethod
    def delete_rule(rule: AlertRule, actor: User) -> None:
        """Delete an alert rule."""
        rule_name = rule.name
        rule_id = rule.id

        db.session.delete(rule)
        db.session.commit()

        log_action(
            action="alert_rule.deleted",
            actor=actor,
            target_type="alert_rule",
            target_id=rule_id,
            target_label=rule_name,
        )


class AlertEventService:
    """Service for alert event history."""

    @staticmethod
    def list_events(
        page: int = 1,
        page_size: int = 50,
        event_type: Optional[str] = None,
        severity: Optional[str] = None,
        delivery_status: Optional[str] = None,
    ) -> dict:
        """List alert events with pagination and filters."""
        query = AlertEvent.query

        if event_type:
            query = query.filter(AlertEvent.event_type == event_type)

        if severity:
            query = query.filter(AlertEvent.severity == severity)

        if delivery_status:
            query = query.filter(AlertEvent.delivery_status == delivery_status)

        query = query.order_by(AlertEvent.created_at.desc())
        pagination = query.paginate(page=page, per_page=page_size, error_out=False)

        return {
            "items": [evt.to_dict() for evt in pagination.items],
            "total": pagination.total,
            "page": pagination.page,
            "page_size": pagination.per_page,
            "pages": pagination.pages,
        }

    @staticmethod
    def get_event(event_id: int) -> Optional[AlertEvent]:
        """Get an alert event by ID."""
        return AlertEvent.query.get(event_id)


class NotificationDeliveryService:
    """Service for delivering notifications to channels."""

    @staticmethod
    def deliver_to_channel(channel: NotificationChannel, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Deliver a notification to a specific channel."""
        if channel.type == "email":
            return NotificationDeliveryService._deliver_email(channel, payload)
        elif channel.type == "slack":
            return NotificationDeliveryService._deliver_slack(channel, payload)
        elif channel.type == "webhook":
            return NotificationDeliveryService._deliver_webhook(channel, payload)
        else:
            return {"success": False, "error": f"Unsupported channel type: {channel.type}"}

    @staticmethod
    def _deliver_email(channel: NotificationChannel, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Deliver notification via email (placeholder - would integrate with email service)."""
        recipients = channel.config.get("recipients", [])
        logger.info(f"[EMAIL] Would send to {recipients}: {payload.get('title')}")
        # In production, integrate with SendGrid, SES, etc.
        return {"success": True, "recipients": recipients, "simulated": True}

    @staticmethod
    def _is_mattermost_webhook(webhook_url: str, channel_config: Dict[str, Any]) -> bool:
        """
        Detect if webhook is Mattermost-style.
        Mattermost URLs typically contain '/hooks/' in the path.
        Also check if provider is explicitly set to 'mattermost'.
        """
        if channel_config.get("provider") == "mattermost":
            return True
        if "/hooks/" in webhook_url:
            return True
        return False

    @staticmethod
    def _deliver_slack(channel: NotificationChannel, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Deliver notification via Slack or Mattermost webhook."""
        webhook_url = channel.config.get("webhook_url")
        if not webhook_url:
            return {"success": False, "error": "No webhook URL configured"}

        # Detect Mattermost vs Slack
        is_mattermost = NotificationDeliveryService._is_mattermost_webhook(webhook_url, channel.config)

        if is_mattermost:
            # Mattermost uses simple {"text": "..."} format
            title = payload.get("title", "Alert")
            message = payload.get("message", "")
            severity = payload.get("severity", "medium")
            event_type = payload.get("event_type", "unknown")
            
            text = f"**{title}**\n{message}\n_Severity: {severity} | Event: {event_type}_"
            message_payload = {"text": text}
        else:
            # Slack uses attachments format
            severity_colors = {
                "low": "#36a64f",
                "medium": "#ffcc00",
                "high": "#ff9900",
                "critical": "#ff0000",
            }

            message_payload = {
                "attachments": [{
                    "color": severity_colors.get(payload.get("severity", "medium"), "#36a64f"),
                    "title": payload.get("title", "Alert"),
                    "text": payload.get("message", ""),
                    "fields": [
                        {"title": "Severity", "value": payload.get("severity", "medium"), "short": True},
                        {"title": "Event Type", "value": payload.get("event_type", "unknown"), "short": True},
                    ],
                    "ts": int(datetime.utcnow().timestamp()),
                }]
            }

        try:
            response = requests.post(
                webhook_url,
                json=message_payload,
                headers={"Content-Type": "application/json"},
                timeout=10
            )
            response.raise_for_status()
            
            # Log response body (truncated) for debugging
            response_text = response.text[:500] if response.text else ""
            return {
                "success": True,
                "status_code": response.status_code,
                "response_body": response_text,
                "provider": "mattermost" if is_mattermost else "slack",
            }
        except requests.RequestException as e:
            logger.error(f"Slack/Mattermost delivery failed: {e}")
            # Include response body in error if available
            error_body = ""
            if hasattr(e, "response") and e.response is not None:
                error_body = e.response.text[:500] if e.response.text else ""
            return {
                "success": False,
                "error": str(e),
                "response_body": error_body,
                "provider": "mattermost" if is_mattermost else "slack",
            }

    @staticmethod
    def _deliver_webhook(channel: NotificationChannel, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Deliver notification via generic webhook."""
        url = channel.config.get("url")
        if not url:
            return {"success": False, "error": "No webhook URL configured"}

        headers = channel.config.get("headers", {})
        headers.setdefault("Content-Type", "application/json")

        # Add auth header if configured
        if channel.config.get("auth_header"):
            auth_header = channel.config["auth_header"]
            headers[auth_header.get("name", "Authorization")] = auth_header.get("value", "")

        try:
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            response.raise_for_status()
            return {"success": True, "status_code": response.status_code}
        except requests.RequestException as e:
            logger.error(f"Webhook delivery failed: {e}")
            return {"success": False, "error": str(e)}


class AlertTriggerService:
    """Service for triggering alerts based on events."""

    @staticmethod
    def trigger_alert(
        event_type: str,
        title: str,
        payload: Optional[Dict[str, Any]] = None,
        severity_override: Optional[str] = None,
    ) -> Optional[AlertEvent]:
        """
        Trigger alerts for an event type.
        Finds matching enabled rules and delivers to their channels.
        """
        # Find enabled rules matching this event type
        rules = AlertRule.query.filter(
            AlertRule.event_type == event_type,
            AlertRule.is_enabled == True
        ).all()

        if not rules:
            logger.debug(f"No alert rules for event type: {event_type}")
            return None

        # Process each matching rule
        for rule in rules:
            # Check conditions if any
            if rule.conditions and not AlertTriggerService._check_conditions(rule.conditions, payload):
                continue

            severity = severity_override or rule.severity
            
            # Create alert event
            alert_event = AlertEvent(
                rule_id=rule.id,
                event_type=event_type,
                severity=severity,
                title=title,
                payload=payload,
                channels_notified=[],
                delivery_status="pending",
                delivery_details={},
            )
            db.session.add(alert_event)
            db.session.flush()

            # Deliver to each channel
            delivery_details = {}
            successful_channels = []
            failed_channels = []

            for channel_id in rule.channel_ids:
                channel = NotificationChannel.query.get(channel_id)
                if not channel or not channel.is_enabled:
                    delivery_details[str(channel_id)] = {"success": False, "error": "Channel not found or disabled"}
                    failed_channels.append(channel_id)
                    continue

                notification_payload = {
                    "title": title,
                    "message": payload.get("message", "") if payload else "",
                    "severity": severity,
                    "event_type": event_type,
                    "timestamp": datetime.utcnow().isoformat(),
                    "details": payload,
                }

                result = NotificationDeliveryService.deliver_to_channel(channel, notification_payload)
                delivery_details[str(channel_id)] = result

                if result.get("success"):
                    successful_channels.append(channel_id)
                else:
                    failed_channels.append(channel_id)

            # Update alert event with delivery status
            alert_event.channels_notified = successful_channels
            alert_event.delivery_details = delivery_details

            if len(successful_channels) == len(rule.channel_ids):
                alert_event.delivery_status = "delivered"
            elif len(successful_channels) > 0:
                alert_event.delivery_status = "partial"
            else:
                alert_event.delivery_status = "failed"

            db.session.commit()

            logger.info(f"Alert triggered: {title} (rule: {rule.name}, status: {alert_event.delivery_status})")

        return alert_event

    @staticmethod
    def _check_conditions(conditions: Dict[str, Any], payload: Optional[Dict[str, Any]]) -> bool:
        """Check if payload matches rule conditions."""
        if not payload:
            return True  # No payload means no conditions to check against

        for key, expected in conditions.items():
            actual = payload.get(key)
            if isinstance(expected, list):
                if actual not in expected:
                    return False
            elif actual != expected:
                return False

        return True
