"""zero trust phase 1: session epoch, audit hash chain, agent export budget

Revision ID: z6a7b8c9d0e1
Revises: y5z6a7b8c9d0

Adds:
  * user.session_epoch      — bump to retire every token issued before now.
  * audit_log.prev_hash/row_hash — tamper-evident chain over the audit trail.
  * agent_request.row_count — enables the per-actor daily export budget.

Existing audit rows stay unsealed (NULL hashes); verify_chain skips them rather
than reporting the migration boundary as tampering. The chain therefore attests
to everything from this migration forward.
"""
import sqlalchemy as sa
from alembic import op

revision = "z6a7b8c9d0e1"
down_revision = "y5z6a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("user") as batch:
        batch.add_column(sa.Column("session_epoch", sa.Integer(), nullable=False,
                                   server_default="0"))

    with op.batch_alter_table("audit_log") as batch:
        batch.add_column(sa.Column("prev_hash", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("row_hash", sa.String(length=64), nullable=True))
        batch.create_index("ix_audit_log_row_hash", ["row_hash"])

    with op.batch_alter_table("agent_request") as batch:
        batch.add_column(sa.Column("row_count", sa.Integer(), nullable=False,
                                   server_default="0"))


def downgrade():
    with op.batch_alter_table("agent_request") as batch:
        batch.drop_column("row_count")

    with op.batch_alter_table("audit_log") as batch:
        batch.drop_index("ix_audit_log_row_hash")
        batch.drop_column("row_hash")
        batch.drop_column("prev_hash")

    with op.batch_alter_table("user") as batch:
        batch.drop_column("session_epoch")
