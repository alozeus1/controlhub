"""
Email Campaigns Module — data models.

Native "Mailchimp" for ControlHub. Sends via Amazon SES (LocalStack in dev).
n8n owns automation/orchestration; this module owns contacts, campaigns,
deliverability hygiene (suppression), and analytics.

Kept in a separate module and imported at the end of app/models.py so the
SQLAlchemy metadata (and Flask-Migrate autogenerate) registers these tables
without bloating the primary models file.
"""
import secrets
from datetime import datetime

from app.extensions import db


# ─── Subscribers ──────────────────────────────────────────────────────────────

SUBSCRIBER_STATUSES = ("subscribed", "unsubscribed", "bounced", "complained", "pending")


class Subscriber(db.Model):
    """A marketing contact. Consent fields support CAN-SPAM / GDPR."""
    __tablename__ = "email_subscriber"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), nullable=False, index=True)
    name = db.Column(db.String(200), nullable=True)
    status = db.Column(db.String(20), nullable=False, default="subscribed")
    attributes = db.Column(db.JSON, nullable=True)  # arbitrary merge-tag data

    # Consent / provenance
    consent_source = db.Column(db.String(120), nullable=True)  # e.g. "signup_form", "import", "api"
    consent_ip = db.Column(db.String(64), nullable=True)
    consent_at = db.Column(db.DateTime, nullable=True)
    double_optin_at = db.Column(db.DateTime, nullable=True)

    # Public token used for one-click unsubscribe links (unguessable)
    unsubscribe_token = db.Column(db.String(64), nullable=False, unique=True,
                                  default=lambda: secrets.token_urlsafe(32))

    created_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    memberships = db.relationship("ListMembership", backref="subscriber",
                                  cascade="all, delete-orphan")

    __table_args__ = (
        db.UniqueConstraint("email", name="uq_email_subscriber_email"),
    )

    @property
    def is_sendable(self):
        return self.status == "subscribed"

    def to_dict(self, include_lists=False):
        d = {
            "id": self.id,
            "email": self.email,
            "name": self.name,
            "status": self.status,
            "attributes": self.attributes or {},
            "consent_source": self.consent_source,
            "consent_at": self.consent_at.isoformat() if self.consent_at else None,
            "double_optin_at": self.double_optin_at.isoformat() if self.double_optin_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_lists:
            d["lists"] = [m.list_id for m in self.memberships]
        return d


# ─── Lists & membership ───────────────────────────────────────────────────────

class EmailList(db.Model):
    """A static mailing list. (Dynamic SQL segments can be layered later.)"""
    __tablename__ = "email_list"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=True)
    list_type = db.Column(db.String(20), default="static")  # static | dynamic_sql
    segment_query = db.Column(db.Text, nullable=True)  # reserved for dynamic lists
    created_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    memberships = db.relationship("ListMembership", backref="list",
                                  cascade="all, delete-orphan")

    def member_count(self):
        return ListMembership.query.filter_by(list_id=self.id).count()

    def to_dict(self, with_count=True):
        d = {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "list_type": self.list_type,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if with_count:
            d["member_count"] = self.member_count()
        return d


class ListMembership(db.Model):
    __tablename__ = "email_list_membership"

    id = db.Column(db.Integer, primary_key=True)
    list_id = db.Column(db.Integer, db.ForeignKey("email_list.id"), nullable=False, index=True)
    subscriber_id = db.Column(db.Integer, db.ForeignKey("email_subscriber.id"), nullable=False, index=True)
    added_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint("list_id", "subscriber_id", name="uq_list_membership"),
    )


# ─── Templates ────────────────────────────────────────────────────────────────

class EmailTemplate(db.Model):
    __tablename__ = "email_template"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    subject = db.Column(db.String(255), nullable=True)
    html = db.Column(db.Text, nullable=True)
    blocks = db.Column(db.JSON, nullable=True)  # editor block model (GrapesJS-ready)
    created_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "subject": self.subject,
            "html": self.html,
            "blocks": self.blocks,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# ─── Campaigns ────────────────────────────────────────────────────────────────

CAMPAIGN_STATUSES = ("draft", "scheduled", "sending", "sent", "paused", "failed", "cancelled")


class Campaign(db.Model):
    __tablename__ = "email_campaign"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    subject = db.Column(db.String(255), nullable=False)
    from_name = db.Column(db.String(150), nullable=True)
    from_address = db.Column(db.String(255), nullable=True)
    reply_to = db.Column(db.String(255), nullable=True)
    html = db.Column(db.Text, nullable=True)
    template_id = db.Column(db.Integer, db.ForeignKey("email_template.id"), nullable=True)
    target_list_id = db.Column(db.Integer, db.ForeignKey("email_list.id"), nullable=True)

    status = db.Column(db.String(20), nullable=False, default="draft")
    scheduled_at = db.Column(db.DateTime, nullable=True)
    sent_at = db.Column(db.DateTime, nullable=True)

    # Denormalized counters (updated by worker + event webhook) for fast dashboards
    total_recipients = db.Column(db.Integer, default=0)
    sent_count = db.Column(db.Integer, default=0)
    delivered_count = db.Column(db.Integer, default=0)
    open_count = db.Column(db.Integer, default=0)
    click_count = db.Column(db.Integer, default=0)
    bounce_count = db.Column(db.Integer, default=0)
    complaint_count = db.Column(db.Integer, default=0)
    failed_count = db.Column(db.Integer, default=0)

    created_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    template = db.relationship("EmailTemplate")
    target_list = db.relationship("EmailList")

    def open_rate(self):
        return round(100.0 * self.open_count / self.sent_count, 1) if self.sent_count else 0.0

    def click_rate(self):
        return round(100.0 * self.click_count / self.sent_count, 1) if self.sent_count else 0.0

    def bounce_rate(self):
        return round(100.0 * self.bounce_count / self.sent_count, 2) if self.sent_count else 0.0

    def complaint_rate(self):
        return round(100.0 * self.complaint_count / self.sent_count, 3) if self.sent_count else 0.0

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "subject": self.subject,
            "from_name": self.from_name,
            "from_address": self.from_address,
            "reply_to": self.reply_to,
            "html": self.html,
            "template_id": self.template_id,
            "target_list_id": self.target_list_id,
            "target_list_name": self.target_list.name if self.target_list else None,
            "status": self.status,
            "scheduled_at": self.scheduled_at.isoformat() if self.scheduled_at else None,
            "sent_at": self.sent_at.isoformat() if self.sent_at else None,
            "total_recipients": self.total_recipients or 0,
            "sent_count": self.sent_count or 0,
            "delivered_count": self.delivered_count or 0,
            "open_count": self.open_count or 0,
            "click_count": self.click_count or 0,
            "bounce_count": self.bounce_count or 0,
            "complaint_count": self.complaint_count or 0,
            "failed_count": self.failed_count or 0,
            "open_rate": self.open_rate(),
            "click_rate": self.click_rate(),
            "bounce_rate": self.bounce_rate(),
            "complaint_rate": self.complaint_rate(),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class CampaignSend(db.Model):
    """Per-recipient send record; the idempotency + tracking anchor."""
    __tablename__ = "email_campaign_send"

    id = db.Column(db.Integer, primary_key=True)
    campaign_id = db.Column(db.Integer, db.ForeignKey("email_campaign.id"), nullable=False, index=True)
    subscriber_id = db.Column(db.Integer, db.ForeignKey("email_subscriber.id"), nullable=True, index=True)
    email = db.Column(db.String(255), nullable=False)
    ses_message_id = db.Column(db.String(255), nullable=True, index=True)
    status = db.Column(db.String(20), default="queued")  # queued|sent|delivered|bounced|complained|failed|suppressed
    error = db.Column(db.Text, nullable=True)
    sent_at = db.Column(db.DateTime, nullable=True)
    delivered_at = db.Column(db.DateTime, nullable=True)
    opened_at = db.Column(db.DateTime, nullable=True)
    clicked_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint("campaign_id", "email", name="uq_campaign_send_recipient"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "campaign_id": self.campaign_id,
            "email": self.email,
            "ses_message_id": self.ses_message_id,
            "status": self.status,
            "sent_at": self.sent_at.isoformat() if self.sent_at else None,
            "opened_at": self.opened_at.isoformat() if self.opened_at else None,
            "clicked_at": self.clicked_at.isoformat() if self.clicked_at else None,
        }


# ─── Suppression & events ─────────────────────────────────────────────────────

SUPPRESSION_REASONS = ("hard_bounce", "complaint", "manual", "unsubscribe")


class Suppression(db.Model):
    """Global do-not-send list. Checked before every send. Sacred for reputation."""
    __tablename__ = "email_suppression"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), nullable=False, unique=True, index=True)
    reason = db.Column(db.String(20), nullable=False)
    detail = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "email": self.email,
            "reason": self.reason,
            "detail": self.detail,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class EmailSettings(db.Model):
    """Singleton (id=1) — module-level sender + compliance footer configuration."""
    __tablename__ = "email_settings"

    id = db.Column(db.Integer, primary_key=True)
    from_name = db.Column(db.String(150), nullable=True)
    from_address = db.Column(db.String(255), nullable=True)
    reply_to = db.Column(db.String(255), nullable=True)
    footer_org_name = db.Column(db.String(200), nullable=True)
    footer_address = db.Column(db.Text, nullable=True)      # physical postal address (CAN-SPAM)
    footer_html = db.Column(db.Text, nullable=True)          # optional custom footer HTML
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            "from_name": self.from_name,
            "from_address": self.from_address,
            "reply_to": self.reply_to,
            "footer_org_name": self.footer_org_name,
            "footer_address": self.footer_address,
            "footer_html": self.footer_html,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    @classmethod
    def get(cls):
        row = cls.query.get(1)
        if not row:
            row = cls(id=1)
            db.session.add(row)
            db.session.commit()
        return row


class EmailEvent(db.Model):
    """Raw event log from SES (via SNS): delivery/bounce/complaint/open/click."""
    __tablename__ = "email_event"

    id = db.Column(db.Integer, primary_key=True)
    campaign_send_id = db.Column(db.Integer, db.ForeignKey("email_campaign_send.id"), nullable=True, index=True)
    ses_message_id = db.Column(db.String(255), nullable=True, index=True)
    event_type = db.Column(db.String(40), nullable=False)  # Send|Delivery|Bounce|Complaint|Open|Click|Reject
    email = db.Column(db.String(255), nullable=True)
    raw = db.Column(db.JSON, nullable=True)
    occurred_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint("ses_message_id", "event_type", name="uq_email_event_dedupe"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "event_type": self.event_type,
            "email": self.email,
            "ses_message_id": self.ses_message_id,
            "occurred_at": self.occurred_at.isoformat() if self.occurred_at else None,
        }
