"""
Per-user in-app notification inbox helpers.

Distinct from app/services/notifications.py, which is the ops-facing
NotificationChannel/AlertRule/AlertEvent system (admin-configured Slack/
webhook/email channels for system events). This module creates personal
inbox items for the specific user(s) an action pertains to — e.g. "your
biweekly review was graded", "a decision requires your approval".

Best-effort: a failure to create a notification must never break the
calling workflow.
"""
import logging

from app.extensions import db
from app.models import Notification, User, ROLE_LEVELS

logger = logging.getLogger(__name__)


def notify_user(user_id, notif_type, title, body=None, link=None, target_type=None, target_id=None):
    """Create an inbox notification for a single user, honoring their
    notifications_enabled preference. Returns the created Notification, or
    None if suppressed/failed."""
    if not user_id:
        return None
    try:
        user = User.query.get(user_id)
        if not user or not user.is_active or not user.notifications_enabled:
            return None
        notification = Notification(
            user_id=user_id,
            type=notif_type,
            title=title,
            body=body,
            link=link,
            target_type=target_type,
            target_id=target_id,
        )
        db.session.add(notification)
        db.session.commit()
        return notification
    except Exception:
        db.session.rollback()
        logger.warning("Failed to create notification for user %s (%s)", user_id, notif_type, exc_info=True)
        return None


def notify_role_at_least(min_role, notif_type, title, body=None, link=None, target_type=None, target_id=None, exclude_user_id=None):
    """Create an inbox notification for every active user whose role meets or
    exceeds min_role's level (e.g. broadcasting an approval request to
    everyone who can act on it)."""
    min_level = ROLE_LEVELS.get(min_role, 0)
    try:
        users = User.query.filter_by(is_active=True).all()
    except Exception:
        logger.warning("Failed to query users for role broadcast (%s)", notif_type, exc_info=True)
        return 0

    count = 0
    for user in users:
        if user.id == exclude_user_id:
            continue
        if user.role_level < min_level:
            continue
        if notify_user(user.id, notif_type, title, body=body, link=link, target_type=target_type, target_id=target_id):
            count += 1
    return count
