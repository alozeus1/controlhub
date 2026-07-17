"""Allow approval requests to survive policy deletion.

Revision ID: y5z6a7b8c9d0
Revises: x4y5z6a7b8c9
"""
from alembic import op
import sqlalchemy as sa

revision = "y5z6a7b8c9d0"
down_revision = "x4y5z6a7b8c9"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("approval_request") as batch_op:
        batch_op.drop_constraint("approval_request_policy_id_fkey", type_="foreignkey")
        batch_op.alter_column("policy_id", existing_type=sa.Integer(), nullable=True)
        batch_op.create_foreign_key(
            "approval_request_policy_id_fkey",
            "policy",
            ["policy_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade():
    with op.batch_alter_table("approval_request") as batch_op:
        batch_op.drop_constraint("approval_request_policy_id_fkey", type_="foreignkey")
        batch_op.alter_column("policy_id", existing_type=sa.Integer(), nullable=False)
        batch_op.create_foreign_key(
            "approval_request_policy_id_fkey",
            "policy",
            ["policy_id"],
            ["id"],
        )
