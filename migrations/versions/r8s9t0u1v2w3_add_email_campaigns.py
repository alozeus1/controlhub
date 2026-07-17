"""add email campaigns module

Revision ID: r8s9t0u1v2w3
Revises: q7r8s9t0u1v2
Create Date: 2026-07-16

Tables for the native email-marketing module: subscribers, lists, membership,
templates, campaigns, per-recipient sends, suppression, and SES events.
"""
from alembic import op
import sqlalchemy as sa


revision = "r8s9t0u1v2w3"
down_revision = "q7r8s9t0u1v2"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "email_subscriber",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="subscribed"),
        sa.Column("attributes", sa.JSON(), nullable=True),
        sa.Column("consent_source", sa.String(length=120), nullable=True),
        sa.Column("consent_ip", sa.String(length=64), nullable=True),
        sa.Column("consent_at", sa.DateTime(), nullable=True),
        sa.Column("double_optin_at", sa.DateTime(), nullable=True),
        sa.Column("unsubscribe_token", sa.String(length=64), nullable=False),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["created_by_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email", name="uq_email_subscriber_email"),
        sa.UniqueConstraint("unsubscribe_token"),
    )
    op.create_index("ix_email_subscriber_email", "email_subscriber", ["email"])

    op.create_table(
        "email_list",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("list_type", sa.String(length=20), server_default="static", nullable=True),
        sa.Column("segment_query", sa.Text(), nullable=True),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["created_by_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "email_list_membership",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("list_id", sa.Integer(), nullable=False),
        sa.Column("subscriber_id", sa.Integer(), nullable=False),
        sa.Column("added_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["list_id"], ["email_list.id"]),
        sa.ForeignKeyConstraint(["subscriber_id"], ["email_subscriber.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("list_id", "subscriber_id", name="uq_list_membership"),
    )
    op.create_index("ix_email_list_membership_list_id", "email_list_membership", ["list_id"])
    op.create_index("ix_email_list_membership_subscriber_id", "email_list_membership", ["subscriber_id"])

    op.create_table(
        "email_template",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=True),
        sa.Column("html", sa.Text(), nullable=True),
        sa.Column("blocks", sa.JSON(), nullable=True),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["created_by_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "email_campaign",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("from_name", sa.String(length=150), nullable=True),
        sa.Column("from_address", sa.String(length=255), nullable=True),
        sa.Column("reply_to", sa.String(length=255), nullable=True),
        sa.Column("html", sa.Text(), nullable=True),
        sa.Column("template_id", sa.Integer(), nullable=True),
        sa.Column("target_list_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="draft"),
        sa.Column("scheduled_at", sa.DateTime(), nullable=True),
        sa.Column("sent_at", sa.DateTime(), nullable=True),
        sa.Column("total_recipients", sa.Integer(), server_default="0"),
        sa.Column("sent_count", sa.Integer(), server_default="0"),
        sa.Column("delivered_count", sa.Integer(), server_default="0"),
        sa.Column("open_count", sa.Integer(), server_default="0"),
        sa.Column("click_count", sa.Integer(), server_default="0"),
        sa.Column("bounce_count", sa.Integer(), server_default="0"),
        sa.Column("complaint_count", sa.Integer(), server_default="0"),
        sa.Column("failed_count", sa.Integer(), server_default="0"),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["template_id"], ["email_template.id"]),
        sa.ForeignKeyConstraint(["target_list_id"], ["email_list.id"]),
        sa.ForeignKeyConstraint(["created_by_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "email_campaign_send",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("campaign_id", sa.Integer(), nullable=False),
        sa.Column("subscriber_id", sa.Integer(), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("ses_message_id", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="queued"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("sent_at", sa.DateTime(), nullable=True),
        sa.Column("delivered_at", sa.DateTime(), nullable=True),
        sa.Column("opened_at", sa.DateTime(), nullable=True),
        sa.Column("clicked_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["campaign_id"], ["email_campaign.id"]),
        sa.ForeignKeyConstraint(["subscriber_id"], ["email_subscriber.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("campaign_id", "email", name="uq_campaign_send_recipient"),
    )
    op.create_index("ix_email_campaign_send_campaign_id", "email_campaign_send", ["campaign_id"])
    op.create_index("ix_email_campaign_send_subscriber_id", "email_campaign_send", ["subscriber_id"])
    op.create_index("ix_email_campaign_send_ses_message_id", "email_campaign_send", ["ses_message_id"])

    op.create_table(
        "email_suppression",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("reason", sa.String(length=20), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_index("ix_email_suppression_email", "email_suppression", ["email"])

    op.create_table(
        "email_event",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("campaign_send_id", sa.Integer(), nullable=True),
        sa.Column("ses_message_id", sa.String(length=255), nullable=True),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("raw", sa.JSON(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["campaign_send_id"], ["email_campaign_send.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ses_message_id", "event_type", name="uq_email_event_dedupe"),
    )
    op.create_index("ix_email_event_campaign_send_id", "email_event", ["campaign_send_id"])
    op.create_index("ix_email_event_ses_message_id", "email_event", ["ses_message_id"])


def downgrade():
    op.drop_table("email_event")
    op.drop_index("ix_email_suppression_email", table_name="email_suppression")
    op.drop_table("email_suppression")
    op.drop_table("email_campaign_send")
    op.drop_table("email_campaign")
    op.drop_table("email_template")
    op.drop_table("email_list_membership")
    op.drop_table("email_list")
    op.drop_index("ix_email_subscriber_email", table_name="email_subscriber")
    op.drop_table("email_subscriber")
