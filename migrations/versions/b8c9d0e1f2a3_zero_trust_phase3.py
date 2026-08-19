"""zero trust phase 3: just-in-time privilege grants

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2

Adds privilege_grant: a time-boxed activation of a permission the user is
already eligible for. Inert until JIT_ELEVATED_PERMISSIONS lists a key, so this
migration changes no behavior on its own.
"""
import sqlalchemy as sa
from alembic import op

revision = "b8c9d0e1f2a3"
down_revision = "a7b8c9d0e1f2"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "privilege_grant",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("permission_key", sa.String(length=64), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("session_family", sa.String(length=64), nullable=True),
        sa.Column("granted_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_reason", sa.String(length=255), nullable=True),
        sa.Column("approved_by_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("used_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
    )
    op.create_index("ix_privilege_grant_user_id", "privilege_grant", ["user_id"])
    op.create_index("ix_privilege_grant_permission_key", "privilege_grant", ["permission_key"])
    op.create_index("ix_privilege_grant_session_family", "privilege_grant", ["session_family"])
    # The hot path is "is there a live grant for this user+permission".
    op.create_index("ix_privilege_grant_lookup", "privilege_grant",
                    ["user_id", "permission_key", "expires_at"])


def downgrade():
    op.drop_index("ix_privilege_grant_lookup", table_name="privilege_grant")
    op.drop_index("ix_privilege_grant_session_family", table_name="privilege_grant")
    op.drop_index("ix_privilege_grant_permission_key", table_name="privilege_grant")
    op.drop_index("ix_privilege_grant_user_id", table_name="privilege_grant")
    op.drop_table("privilege_grant")
