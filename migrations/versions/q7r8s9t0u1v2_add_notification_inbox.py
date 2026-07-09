"""add per-user notification inbox

Adds the `notification` table (personal in-app inbox items, distinct from the
existing ops-facing NotificationChannel/AlertRule/AlertEvent system) and a
`notifications_enabled` preference column on `user`.

Revision ID: q7r8s9t0u1v2
Revises: p6q7r8s9t0u1
Create Date: 2026-07-09
"""

from alembic import op
import sqlalchemy as sa


revision = "q7r8s9t0u1v2"
down_revision = "p6q7r8s9t0u1"
branch_labels = None
depends_on = None


def _has_table(name):
    return name in sa.inspect(op.get_bind()).get_table_names()


def _has_column(table, column):
    return column in {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade():
    if not _has_column("user", "notifications_enabled"):
        op.add_column(
            "user",
            sa.Column("notifications_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        )

    if not _has_table("notification"):
        op.create_table(
            "notification",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("type", sa.String(length=50), nullable=False),
            sa.Column("title", sa.String(length=200), nullable=False),
            sa.Column("body", sa.Text(), nullable=True),
            sa.Column("link", sa.String(length=255), nullable=True),
            sa.Column("target_type", sa.String(length=50), nullable=True),
            sa.Column("target_id", sa.Integer(), nullable=True),
            sa.Column("is_read", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_notification_user_id", "notification", ["user_id"], unique=False)
        op.create_index("ix_notification_user_unread", "notification", ["user_id", "is_read"], unique=False)


def downgrade():
    if _has_table("notification"):
        op.drop_index("ix_notification_user_unread", table_name="notification")
        op.drop_index("ix_notification_user_id", table_name="notification")
        op.drop_table("notification")

    if _has_column("user", "notifications_enabled"):
        op.drop_column("user", "notifications_enabled")
