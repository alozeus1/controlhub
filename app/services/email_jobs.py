"""
RQ jobs for the email campaigns module.

The worker runs `send_campaign_job` which builds its own Flask app context so it
can use SQLAlchemy models and the SES service outside a request.
"""
import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def get_queue():
    """Return an RQ queue bound to REDIS_URL. Raises if unavailable."""
    import redis
    from rq import Queue
    conn = redis.from_url(os.environ.get("REDIS_URL", "redis://localhost:6379/0"))
    return Queue(os.environ.get("CAMPAIGN_QUEUE", "campaigns"), connection=conn)


def send_campaign_job(campaign_id):
    """RQ entrypoint — wraps run_campaign_send in an app context."""
    from app import create_app
    app = create_app()
    with app.app_context():
        return run_campaign_send(campaign_id)


def run_campaign_send(campaign_id):
    """
    Core send loop. Idempotent per recipient via the unique (campaign_id, email)
    CampaignSend row: a restart mid-batch will not double-send already-sent rows.
    """
    from app.extensions import db
    from app.models import Campaign, CampaignSend
    from app.services.campaigns import (
        CampaignService, SuppressionService, render_merge_tags, ensure_compliance_footer,
        build_unsubscribe_url,
    )
    from app.services import email_ses, n8n_events

    campaign = Campaign.query.get(campaign_id)
    if not campaign:
        logger.error("Campaign %s not found", campaign_id)
        return {"error": "not_found"}

    recipients = CampaignService.resolve_recipients(campaign)
    sent = failed = skipped = 0

    for sub in recipients:
        if SuppressionService.is_suppressed(sub.email):
            skipped += 1
            continue

        # Idempotency guard.
        existing = CampaignSend.query.filter_by(campaign_id=campaign.id, email=sub.email).first()
        if existing and existing.status in ("sent", "delivered", "opened", "clicked"):
            continue
        record = existing or CampaignSend(campaign_id=campaign.id, subscriber_id=sub.id, email=sub.email)
        if not existing:
            db.session.add(record)
            db.session.commit()

        subject = render_merge_tags(campaign.subject, sub)
        body = render_merge_tags(campaign.html or "", sub)
        body = ensure_compliance_footer(body, sub)
        unsub = build_unsubscribe_url(sub)
        headers = {
            "List-Unsubscribe": f"<{unsub}>",
            "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
        }

        result = email_ses.send_email(
            to_address=sub.email,
            subject=subject,
            html_body=body,
            from_address=campaign.from_address,
            from_name=campaign.from_name,
            reply_to=campaign.reply_to,
            headers=headers,
        )

        if result.ok:
            record.ses_message_id = result.message_id
            record.status = "sent"
            record.sent_at = datetime.utcnow()
            sent += 1
        else:
            record.status = "failed"
            record.error = (result.error or "")[:2000]
            failed += 1
        db.session.commit()

    campaign.sent_count = sent
    campaign.failed_count = failed
    campaign.status = "sent"
    campaign.sent_at = datetime.utcnow()
    db.session.commit()

    n8n_events.emit("campaign.sent", {
        "campaign_id": campaign.id,
        "name": campaign.name,
        "sent": sent,
        "failed": failed,
        "skipped": skipped,
    })
    logger.info("Campaign %s complete: sent=%s failed=%s skipped=%s",
                campaign.id, sent, failed, skipped)
    return {"sent": sent, "failed": failed, "skipped": skipped}
