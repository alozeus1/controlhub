"""zero trust phase 4: pin agent request egress destinations

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3

Adds agent_request.destination_fingerprint — a digest of the destination type
plus its resolved target id, captured when the request is created. The egress
chokepoint re-computes it at publish time and refuses on drift, so a destination
that is repointed after approval cannot redirect an already-blessed export.

Existing rows get NULL, which the chokepoint treats as "not pinned" and allows —
requests created before this migration keep working rather than failing closed on
a fingerprint that was never recorded.
"""
import sqlalchemy as sa
from alembic import op

revision = "c9d0e1f2a3b4"
down_revision = "b8c9d0e1f2a3"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("agent_request") as batch:
        batch.add_column(sa.Column("destination_fingerprint", sa.String(length=64), nullable=True))


def downgrade():
    with op.batch_alter_table("agent_request") as batch:
        batch.drop_column("destination_fingerprint")
