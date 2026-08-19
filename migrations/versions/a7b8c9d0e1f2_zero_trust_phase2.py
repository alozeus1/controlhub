"""zero trust phase 2: system_state for the audit mirror high-water mark

Revision ID: a7b8c9d0e1f2
Revises: z6a7b8c9d0e1

The KMS secret backend needs no schema change — ciphertexts are self-describing
('fernet:v1:' / 'kms:v1:'), so both formats coexist in the existing columns and
`flask secrets rewrap` migrates values in place.
"""
import sqlalchemy as sa
from alembic import op

revision = "a7b8c9d0e1f2"
down_revision = "z6a7b8c9d0e1"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "system_state",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column("value", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False,
                  server_default=sa.func.now()),
        sa.UniqueConstraint("key", name="uq_system_state_key"),
    )
    op.create_index("ix_system_state_key", "system_state", ["key"])


def downgrade():
    op.drop_index("ix_system_state_key", table_name="system_state")
    op.drop_table("system_state")
