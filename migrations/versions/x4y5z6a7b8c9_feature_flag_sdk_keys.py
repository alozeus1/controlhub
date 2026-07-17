"""Add feature_flag_sdk_key table (audit A-10).

Introduces scoped, revocable, hashed-at-rest SDK keys so the previously public
/feature-flags/sdk/<project> endpoint requires a per-project credential.

Revision ID: x4y5z6a7b8c9
Revises: w3x4y5z6a7b8
"""
from alembic import op
import sqlalchemy as sa

revision = "x4y5z6a7b8c9"
down_revision = "w3x4y5z6a7b8"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "feature_flag_sdk_key",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project", sa.String(length=200), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=True),
        sa.Column("key_hash", sa.String(length=64), nullable=False),
        sa.Column("key_prefix", sa.String(length=12), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("key_hash", name="uq_ff_sdk_key_hash"),
    )
    op.create_index("ix_feature_flag_sdk_key_project", "feature_flag_sdk_key", ["project"])


def downgrade():
    op.drop_index("ix_feature_flag_sdk_key_project", table_name="feature_flag_sdk_key")
    op.drop_table("feature_flag_sdk_key")
