"""add MFA brute-force lockout columns

Revision ID: u1v2w3x4y5z6
Revises: t0u1v2w3x4y5
Create Date: 2026-07-16
"""
from alembic import op
import sqlalchemy as sa

revision = "u1v2w3x4y5z6"
down_revision = "t0u1v2w3x4y5"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("user_mfa", sa.Column("failed_attempts", sa.Integer(),
                                        nullable=False, server_default="0"))
    op.add_column("user_mfa", sa.Column("locked_until", sa.DateTime(), nullable=True))


def downgrade():
    op.drop_column("user_mfa", "locked_until")
    op.drop_column("user_mfa", "failed_attempts")
