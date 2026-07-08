"""
Mocked Integration Gateways for Taiga, Mattermost, and Email Notification Workflows.
This module supports both realistic mock triggers and integrates with env-gated configurations.

All functions here are best-effort: a failure to render or audit a mock
notification must never break the calling workflow.
"""
import logging
from datetime import datetime
from flask import current_app
from app.utils.audit import log_action

logger = logging.getLogger(__name__)


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


def _flag_enabled(flag):
    try:
        return bool(current_app.config.get(flag, False))
    except RuntimeError:
        return False


def get_taiga_activity(taiga_username):
    """
    Simulates fetching activity details from Taiga for a given username.
    In development mode or when mock is enabled, returns synthetic metrics.
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

    # Synthetic but realistic response for local dev/testing.
    # Deterministic per username so results are stable across calls,
    # without touching the global random state.
    import random
    rng = random.Random(sum(ord(c) for c in taiga_username))

    completed = rng.randint(5, 30)
    active = rng.randint(1, 8)
    comments = rng.randint(10, 50)
    score = min(100, int((completed * 3) + (comments * 0.5) + 30))

    activity = {
        "completed_tasks": completed,
        "active_issues": active,
        "comments_posted": comments,
        "participation_score": score,
        "last_active": datetime.utcnow().date().isoformat(),
        "source": "mock",
    }

    _safe_log_action(
        action="integration.taiga.activity_fetched",
        actor=None,
        target_type="user",
        target_id=None,
        target_label=taiga_username,
        details={"mocked": not _flag_enabled("TAIGA_API_ENABLED"), "participation_score": score},
    )
    return activity


def send_mattermost_notification(username, template_type, context):
    """
    Simulates sending a channel or DM notification to Mattermost.
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

    use_real = _flag_enabled("MATTERMOST_API_ENABLED")
    if use_real:
        # In production/live mode, we would call the Mattermost webhook endpoint
        # e.g., requests.post(webhook_url, json={"text": message})
        pass

    logger.info(f"[MATTERMOST MOCK] Notification sent to @{username}: {message}")

    _safe_log_action(
        action="integration.mattermost.notify",
        actor=None,
        target_type="user",
        target_id=None,
        target_label=username,
        details={
            "template_type": template_type,
            "message": message,
            "mocked": not use_real,
        },
    )
    return True, message


def send_email_notification(email, template_type, context):
    """
    Simulates sending a transactional email using a Resend-style delivery model.
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

    use_real = _flag_enabled("EMAIL_NOTIFICATIONS_ENABLED")
    if use_real:
        # In a real environment, we would trigger the Resend SDK or Flask-Mail
        pass

    logger.info(f"[EMAIL MOCK] Sent to {email}\nSubject: {subject}\nBody: {body}")

    _safe_log_action(
        action="integration.email.send",
        actor=None,
        target_type="user",
        target_id=None,
        target_label=email,
        details={
            "template_type": template_type,
            "subject": subject,
            "mocked": not use_real,
        },
    )
    return True, subject
