"""
Integration gateways for Taiga, Mattermost, and Resend-style email notifications.

Default behavior is MOCK mode: no credentials required, nothing leaves the app,
and every attempt is audit-logged with a `mocked` marker. Real delivery is
env-gated per provider (see config.py):

- Taiga:      TAIGA_API_ENABLED + TAIGA_API_URL + TAIGA_AUTH_TOKEN
- Mattermost: MATTERMOST_API_ENABLED + MATTERMOST_WEBHOOK_URL
- Email:      EMAIL_NOTIFICATIONS_ENABLED + RESEND_API_KEY (+ RESEND_FROM_EMAIL)

All functions are best-effort: a failure to render, deliver, or audit a
notification must never break the calling workflow. Real-delivery failures
fall back to mock behavior and are recorded in the audit details.
"""
import logging
from datetime import datetime
from flask import current_app
from app.utils.audit import log_action

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT_SECONDS = 5


class _SafeDict(dict):
    """Leave unknown format placeholders intact instead of raising KeyError."""

    def __missing__(self, key):
        return "{" + key + "}"


def _safe_format(template, **context):
    try:
        return template.format_map(_SafeDict(**context))
    except Exception:
        return template


def _safe_log_action(**kwargs):
    """Audit-log an integration attempt; never raise (e.g. outside app context)."""
    try:
        log_action(**kwargs)
    except Exception:
        logger.warning("Could not audit integration action %s", kwargs.get("action"), exc_info=True)


def _config(key, default=None):
    try:
        return current_app.config.get(key, default)
    except RuntimeError:
        return default


def _mock_taiga_metrics(taiga_username):
    """Deterministic synthetic metrics per username (stable across calls),
    without touching the global random state."""
    import random
    rng = random.Random(sum(ord(c) for c in taiga_username))

    completed = rng.randint(5, 30)
    active = rng.randint(1, 8)
    comments = rng.randint(10, 50)
    score = min(100, int((completed * 3) + (comments * 0.5) + 30))
    return {
        "completed_tasks": completed,
        "active_issues": active,
        "comments_posted": comments,
        "participation_score": score,
        "last_active": datetime.utcnow().date().isoformat(),
        "source": "mock",
    }


def _fetch_real_taiga_metrics(taiga_username):
    """Fetch member stats from a real Taiga instance. Returns None on any failure."""
    base_url = (_config("TAIGA_API_URL") or "").rstrip("/")
    token = _config("TAIGA_AUTH_TOKEN")
    if not base_url or not token:
        return None

    import requests

    headers = {"Authorization": f"Bearer {token}"}
    users = requests.get(
        f"{base_url}/api/v1/users",
        params={"username": taiga_username},
        headers=headers,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    users.raise_for_status()
    matches = [u for u in users.json() if u.get("username") == taiga_username]
    if not matches:
        return None
    user = matches[0]

    stats = requests.get(
        f"{base_url}/api/v1/users/{user['id']}/stats",
        headers=headers,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    stats.raise_for_status()
    data = stats.json()

    completed = int(data.get("total_num_closed_userstories") or 0)
    active = int(data.get("total_num_open_userstories") or data.get("total_num_userstories") or 0)
    comments = int(data.get("total_num_comments") or 0)
    score = min(100, int((completed * 3) + (comments * 0.5) + 30)) if (completed or comments) else 0
    return {
        "completed_tasks": completed,
        "active_issues": active,
        "comments_posted": comments,
        "participation_score": score,
        "last_active": data.get("last_login") or datetime.utcnow().date().isoformat(),
        "source": "taiga",
    }


def get_taiga_activity(taiga_username):
    """
    Fetch activity details from Taiga for a given username.
    Uses the real Taiga API when TAIGA_API_ENABLED is set and configured;
    otherwise (or on any failure) returns deterministic mock metrics.
    """
    if not taiga_username:
        return {
            "completed_tasks": 0,
            "active_issues": 0,
            "comments_posted": 0,
            "participation_score": 0,
            "last_active": None,
            "source": "mock",
        }

    activity = None
    error = None
    if _config("TAIGA_API_ENABLED", False):
        try:
            activity = _fetch_real_taiga_metrics(taiga_username)
        except Exception as exc:
            error = str(exc)
            logger.warning("Taiga fetch failed for %s; falling back to mock: %s", taiga_username, exc)

    if activity is None:
        activity = _mock_taiga_metrics(taiga_username)

    details = {"mocked": activity["source"] == "mock", "participation_score": activity["participation_score"]}
    if error:
        details["fallback_reason"] = error[:300]
    _safe_log_action(
        action="integration.taiga.activity_fetched",
        actor=None,
        target_type="user",
        target_id=None,
        target_label=taiga_username,
        details=details,
    )
    return activity


def send_mattermost_notification(username, template_type, context):
    """
    Send a Mattermost DM/channel notification. Posts to the configured incoming
    webhook when MATTERMOST_API_ENABLED is set; otherwise logs a mock delivery.
    """
    templates = {
        "onboarding_reminder": "Hello @{username}, this is a reminder to complete your onboarding task: '{task_title}'. Due: {due_date}.",
        "review_reminder": "Hello @{username}, your biweekly performance review is now open. Please complete the self-reflection form.",
        "manager_task": "Hello @{username}, you have a pending manager review action for {intern_name}.",
        "overdue_review": "Attention @{username}, your review for period ending {period_end} is OVERDUE. Please submit it immediately.",
        "governance_alert": "ALERT: A sensitive governance action '{action}' requires approval. Approval ID: {approval_id}.",
    }

    msg_template = templates.get(template_type, "Notification: {context}")
    message = _safe_format(msg_template, username=username, **(context or {}))

    delivered = False
    error = None
    webhook_url = _config("MATTERMOST_WEBHOOK_URL")
    if _config("MATTERMOST_API_ENABLED", False) and webhook_url:
        try:
            import requests
            resp = requests.post(webhook_url, json={"text": message}, timeout=REQUEST_TIMEOUT_SECONDS)
            resp.raise_for_status()
            delivered = True
        except Exception as exc:
            error = str(exc)
            logger.warning("Mattermost delivery failed for @%s: %s", username, exc)

    if not delivered:
        logger.info(f"[MATTERMOST MOCK] Notification sent to @{username}: {message}")

    details = {"template_type": template_type, "message": message, "mocked": not delivered}
    if error:
        details["delivery_error"] = error[:300]
    _safe_log_action(
        action="integration.mattermost.notify",
        actor=None,
        target_type="user",
        target_id=None,
        target_label=username,
        details=details,
    )
    return True, message


def send_email_notification(email, template_type, context):
    """
    Send a transactional email. Delivers through the Resend API when
    EMAIL_NOTIFICATIONS_ENABLED is set; otherwise logs a mock delivery.
    """
    templates = {
        "onboarding_initialized": {
            "subject": "Your ControlHub Onboarding Checklist is Ready!",
            "body": "Hi {name},\n\nYour cohort onboarding checklist has been initialized with {count} tasks. Please log in to complete them."
        },
        "biweekly_reminder": {
            "subject": "Review Open: Biweekly Performance Checkin",
            "body": "Hi {name},\n\nYour checkin for the period {period_start} to {period_end} is open. Please fill out your progress review."
        },
        "manager_reminder": {
            "subject": "Action Required: Complete Intern Review",
            "body": "Hi Manager,\n\nPlease evaluate progress and complete review for intern {intern_name}."
        },
        "milestone_completed": {
            "subject": "Milestone Review Summary Ready",
            "body": "Hi {name},\n\nYour {review_type} milestone review is complete. Decision: {decision}."
        }
    }

    tpl = templates.get(template_type, {
        "subject": "ControlHub Notification",
        "body": "Notification update: {context}"
    })

    subject = _safe_format(tpl["subject"], **(context or {}))
    body = _safe_format(tpl["body"], **(context or {}))

    delivered = False
    error = None
    api_key = _config("RESEND_API_KEY")
    if _config("EMAIL_NOTIFICATIONS_ENABLED", False) and api_key:
        try:
            import requests
            resp = requests.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "from": _config("RESEND_FROM_EMAIL", "controlhub@notifications.webforxtech.com"),
                    "to": [email],
                    "subject": subject,
                    "text": body,
                },
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            resp.raise_for_status()
            delivered = True
        except Exception as exc:
            error = str(exc)
            logger.warning("Email delivery failed for %s: %s", email, exc)

    if not delivered:
        logger.info(f"[EMAIL MOCK] Sent to {email}\nSubject: {subject}\nBody: {body}")

    details = {"template_type": template_type, "subject": subject, "mocked": not delivered}
    if error:
        details["delivery_error"] = error[:300]
    _safe_log_action(
        action="integration.email.send",
        actor=None,
        target_type="user",
        target_id=None,
        target_label=email,
        details=details,
    )
    return True, subject
