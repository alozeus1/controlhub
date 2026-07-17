"""
Email Campaigns — business logic.

Owns subscribers, lists, suppression, campaign lifecycle, merge-tag rendering,
recipient resolution, the RQ send pipeline, and SES event ingestion.
"""
import os
import re
import html as html_lib
import logging
from datetime import datetime

from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import (
    Subscriber, ListMembership,
    Campaign, CampaignSend, Suppression, EmailEvent,
)
from app.services import email_ses
from app.services import n8n_events
from app.utils.audit import log_action

logger = logging.getLogger(__name__)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
SEND_BATCH_SIZE = int(os.environ.get("CAMPAIGN_SEND_BATCH_SIZE", "100"))


def is_valid_email(email: str) -> bool:
    return bool(email and EMAIL_RE.match(email.strip()))


# ─── Merge-tag rendering ──────────────────────────────────────────────────────

def render_merge_tags(text: str, subscriber: Subscriber, extra: dict = None) -> str:
    """
    Replace {{ name }}, {{ email }}, and {{ attributes.key }} tokens.
    Values are HTML-escaped to prevent injection from contact data.
    """
    if not text:
        return text or ""
    ctx = {
        "email": subscriber.email or "",
        "name": subscriber.name or "",
    }
    for k, v in (subscriber.attributes or {}).items():
        ctx[f"attributes.{k}"] = v
        ctx[k] = v
    for k, v in (extra or {}).items():
        ctx[k] = v

    def _sub(match):
        key = match.group(1).strip()
        val = ctx.get(key, "")
        return html_lib.escape(str(val))

    return re.sub(r"\{\{\s*([\w.]+)\s*\}\}", _sub, text)


def build_unsubscribe_url(subscriber: Subscriber) -> str:
    base = os.environ.get("PUBLIC_BASE_URL", "http://localhost:9000")
    return f"{base.rstrip('/')}/email/unsubscribe/{subscriber.unsubscribe_token}"


def ensure_compliance_footer(html: str, subscriber: Subscriber) -> str:
    """Append physical address + one-click unsubscribe link if absent (CAN-SPAM).

    Uses the EmailSettings footer configuration when present, else falls back to
    the ORG_POSTAL_ADDRESS env default.
    """
    if not html:
        html = ""
    if "{{unsubscribe_url}}" in html or "unsubscribe" in html.lower():
        return html.replace("{{unsubscribe_url}}", build_unsubscribe_url(subscriber))

    org_name = os.environ.get("ORG_POSTAL_ADDRESS", "Web Forx Technology Limited")
    address = None
    try:
        from app.models import EmailSettings
        s = EmailSettings.query.get(1)
        if s:
            if s.footer_html:
                return html + s.footer_html.replace("{{unsubscribe_url}}", build_unsubscribe_url(subscriber))
            if s.footer_org_name:
                org_name = s.footer_org_name
            if s.footer_address:
                address = s.footer_address
    except Exception:
        pass

    org_block = html_lib.escape(org_name)
    if address:
        org_block += "<br/>" + html_lib.escape(address)
    footer = (
        f'<hr style="margin-top:32px;border:none;border-top:1px solid #e5e7eb"/>'
        f'<p style="font-size:12px;color:#6b7280;text-align:center;margin-top:16px">'
        f'{org_block}<br/>'
        f'<a href="{build_unsubscribe_url(subscriber)}" style="color:#6b7280">Unsubscribe</a>'
        f'</p>'
    )
    return html + footer


# ─── Subscribers ──────────────────────────────────────────────────────────────

class SubscriberService:
    @staticmethod
    def upsert(email, name=None, attributes=None, status="subscribed",
               consent_source=None, consent_ip=None, actor=None, emit=True):
        email = (email or "").strip().lower()
        if not is_valid_email(email):
            raise ValueError(f"Invalid email: {email}")
        sub = Subscriber.query.filter_by(email=email).first()
        created = False
        if not sub:
            sub = Subscriber(email=email, consent_at=datetime.utcnow())
            created = True
            db.session.add(sub)
        if name is not None:
            sub.name = name
        if attributes is not None:
            merged = dict(sub.attributes or {})
            merged.update(attributes)
            sub.attributes = merged
        if consent_source:
            sub.consent_source = consent_source
        if consent_ip:
            sub.consent_ip = consent_ip
        # Never silently resurrect a suppressed contact.
        if status and not Suppression.query.filter_by(email=email).first():
            sub.status = status
        db.session.commit()
        if created:
            log_action("email.subscriber.created", actor=actor, target_type="subscriber",
                       target_id=sub.id, target_label=email)
            if emit:
                n8n_events.emit("subscriber.created", sub.to_dict())
        return sub, created

    @staticmethod
    def unsubscribe_by_token(token):
        sub = Subscriber.query.filter_by(unsubscribe_token=token).first()
        if not sub:
            return None
        sub.status = "unsubscribed"
        SuppressionService.add(sub.email, reason="unsubscribe", detail="One-click unsubscribe")
        db.session.commit()
        n8n_events.emit("subscriber.unsubscribed", sub.to_dict())
        return sub

    @staticmethod
    def bulk_import(rows, actor=None):
        """rows: iterable of dicts with at least 'email'. Returns summary."""
        created = updated = skipped = 0
        errors = []
        for row in rows:
            try:
                _, was_created = SubscriberService.upsert(
                    email=row.get("email"),
                    name=row.get("name"),
                    attributes={k: v for k, v in row.items() if k not in ("email", "name")},
                    consent_source="import",
                    actor=actor,
                    emit=False,
                )
                created += 1 if was_created else 0
                updated += 0 if was_created else 1
            except ValueError as exc:
                skipped += 1
                errors.append(str(exc))
        return {"created": created, "updated": updated, "skipped": skipped, "errors": errors[:20]}


# ─── Lists ────────────────────────────────────────────────────────────────────

class ListService:
    @staticmethod
    def add_member(list_id, subscriber_id):
        """Add a subscriber to a list. Returns (membership, created:bool)."""
        m = ListMembership.query.filter_by(list_id=list_id, subscriber_id=subscriber_id).first()
        if m:
            return m, False
        m = ListMembership(list_id=list_id, subscriber_id=subscriber_id)
        db.session.add(m)
        try:
            db.session.commit()
            return m, True
        except IntegrityError:
            db.session.rollback()
            m = ListMembership.query.filter_by(list_id=list_id, subscriber_id=subscriber_id).first()
            return m, False

    @staticmethod
    def remove_member(list_id, subscriber_id):
        ListMembership.query.filter_by(list_id=list_id, subscriber_id=subscriber_id).delete()
        db.session.commit()


# ─── Suppression ──────────────────────────────────────────────────────────────

class SuppressionService:
    @staticmethod
    def is_suppressed(email):
        return Suppression.query.filter_by(email=email.strip().lower()).first() is not None

    @staticmethod
    def add(email, reason, detail=None):
        email = (email or "").strip().lower()
        existing = Suppression.query.filter_by(email=email).first()
        if existing:
            return existing
        s = Suppression(email=email, reason=reason, detail=detail)
        db.session.add(s)
        # Reflect on the subscriber record too.
        sub = Subscriber.query.filter_by(email=email).first()
        if sub:
            sub.status = "complained" if reason == "complaint" else (
                "bounced" if reason == "hard_bounce" else "unsubscribed")
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            existing = Suppression.query.filter_by(email=email).first()
            return existing
        return s

    @staticmethod
    def remove(email):
        Suppression.query.filter_by(email=email.strip().lower()).delete()
        db.session.commit()


# ─── Campaigns ────────────────────────────────────────────────────────────────

def send_transactional(email, subject, html, from_name=None, from_address=None, reply_to=None):
    """
    Send a single, suppression-aware transactional email. Used by n8n to drive
    real per-contact drip sequences (welcome, follow-up, re-engagement).

    Honors suppression + unsubscribe status, renders merge tags against the
    subscriber if one exists, and attaches one-click unsubscribe headers.
    Returns a dict describing the outcome (never raises for suppression).
    """
    from app.models import Subscriber
    email = (email or "").strip().lower()
    if not is_valid_email(email):
        return {"sent": False, "reason": "invalid_email"}
    if SuppressionService.is_suppressed(email):
        return {"sent": False, "reason": "suppressed"}

    sub = Subscriber.query.filter_by(email=email).first()
    if sub and sub.status != "subscribed":
        return {"sent": False, "reason": f"status_{sub.status}"}

    headers = None
    if sub:
        subject = render_merge_tags(subject, sub)
        html = render_merge_tags(html or "", sub)
        html = ensure_compliance_footer(html, sub)
        unsub = build_unsubscribe_url(sub)
        headers = {
            "List-Unsubscribe": f"<{unsub}>",
            "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
        }

    result = email_ses.send_email(
        to_address=email, subject=subject, html_body=html or "",
        from_address=from_address, from_name=from_name, reply_to=reply_to,
        headers=headers,
    )
    if result.ok:
        return {"sent": True, "message_id": result.message_id}
    return {"sent": False, "reason": "ses_error", "error": result.error}


class CampaignService:
    @staticmethod
    def resolve_recipients(campaign):
        """Return sendable Subscriber rows for a campaign's target list, minus suppression."""
        if not campaign.target_list_id:
            return []
        q = (
            db.session.query(Subscriber)
            .join(ListMembership, ListMembership.subscriber_id == Subscriber.id)
            .filter(ListMembership.list_id == campaign.target_list_id)
            .filter(Subscriber.status == "subscribed")
        )
        subs = q.all()
        suppressed = {s.email for s in Suppression.query.all()}
        return [s for s in subs if s.email not in suppressed]

    @staticmethod
    def enqueue_send(campaign, actor=None):
        """
        Validate + move to 'sending' and dispatch the RQ job.
        Falls back to synchronous execution if RQ/Redis is unavailable or
        CAMPAIGN_SEND_SYNC=true (handy for local testing without a worker).
        """
        if campaign.status not in ("draft", "scheduled"):
            raise ValueError(f"Campaign cannot be sent from status '{campaign.status}'")
        if not campaign.from_address:
            campaign.from_address = email_ses.get_ses_config()["from_address"]
        recipients = CampaignService.resolve_recipients(campaign)
        campaign.total_recipients = len(recipients)
        campaign.status = "sending"
        db.session.commit()
        log_action("email.campaign.send_started", actor=actor, target_type="campaign",
                   target_id=campaign.id, target_label=campaign.name,
                   details={"recipients": len(recipients)})

        sync = os.environ.get("CAMPAIGN_SEND_SYNC", "false").lower() == "true"
        if not sync:
            try:
                from app.services.email_jobs import get_queue
                from rq import Retry
                q = get_queue()
                # Bounded retry with exponential-ish backoff; RQ moves a job that
                # exhausts retries to the FailedJobRegistry (dead-letter).
                q.enqueue("app.services.email_jobs.send_campaign_job", campaign.id,
                          job_timeout=3600, retry=Retry(max=3, interval=[30, 120, 300]))
                return {"mode": "queued", "recipients": len(recipients)}
            except Exception as exc:
                logger.warning("RQ enqueue failed (%s); running synchronously", exc)
        from app.services.email_jobs import run_campaign_send
        run_campaign_send(campaign.id)
        return {"mode": "sync", "recipients": len(recipients)}

    # ── SES event ingestion (called by the SNS webhook) ──
    @staticmethod
    def process_ses_event(event_type, ses_message_id, email, raw):
        """
        Idempotent per (message_id, event_type). Updates the send record,
        campaign counters, suppression list, and emits an n8n event.
        """
        etype = (event_type or "").strip()
        norm = etype.lower()

        # Dedupe.
        if ses_message_id:
            existing = EmailEvent.query.filter_by(
                ses_message_id=ses_message_id, event_type=etype).first()
            if existing:
                return {"deduped": True}

        send = None
        if ses_message_id:
            send = CampaignSend.query.filter_by(ses_message_id=ses_message_id).first()
        if not send and email:
            send = (CampaignSend.query.filter_by(email=email.strip().lower())
                    .order_by(CampaignSend.id.desc()).first())

        evt = EmailEvent(
            campaign_send_id=send.id if send else None,
            ses_message_id=ses_message_id,
            event_type=etype,
            email=(email or (send.email if send else None)),
            raw=raw,
        )
        db.session.add(evt)

        campaign = Campaign.query.get(send.campaign_id) if send else None
        now = datetime.utcnow()

        if norm == "delivery":
            if send:
                send.status = "delivered"
                send.delivered_at = now
            if campaign:
                campaign.delivered_count = (campaign.delivered_count or 0) + 1
        elif norm == "open":
            if send and not send.opened_at:
                send.opened_at = now
                if campaign:
                    campaign.open_count = (campaign.open_count or 0) + 1
        elif norm == "click":
            if send and not send.clicked_at:
                send.clicked_at = now
                if campaign:
                    campaign.click_count = (campaign.click_count or 0) + 1
        elif norm == "bounce":
            if send:
                send.status = "bounced"
            if campaign:
                campaign.bounce_count = (campaign.bounce_count or 0) + 1
            if email:
                SuppressionService.add(email, reason="hard_bounce", detail="SES bounce")
        elif norm == "complaint":
            if send:
                send.status = "complained"
            if campaign:
                campaign.complaint_count = (campaign.complaint_count or 0) + 1
            if email:
                SuppressionService.add(email, reason="complaint", detail="SES complaint")

        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            return {"deduped": True}

        n8n_events.emit(f"email.{norm}", {
            "campaign_id": campaign.id if campaign else None,
            "email": evt.email,
            "ses_message_id": ses_message_id,
        })
        return {"processed": etype}
