"""add agent service tables

Revision ID: j0k1l2m3n4o5
Revises: i9j0k1l2m3n4
Create Date: 2026-03-05
"""
from alembic import op
import sqlalchemy as sa


revision = "j0k1l2m3n4o5"
down_revision = "i9j0k1l2m3n4"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "agent_request",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("requester_user_id", sa.Integer(), nullable=False),
        sa.Column("org_id", sa.Integer(), nullable=True),
        sa.Column("module_scope", sa.String(length=50), nullable=False),
        sa.Column("filters_json", sa.JSON(), nullable=True),
        sa.Column("output_type", sa.String(length=20), nullable=False),
        sa.Column("template_id", sa.String(length=100), nullable=False),
        sa.Column("destination_type", sa.String(length=30), nullable=False, server_default="download"),
        sa.Column("destination_ref", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("approval_required", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("approved_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["requester_user_id"], ["user.id"]),
        sa.ForeignKeyConstraint(["approved_by"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_request_requester", "agent_request", ["requester_user_id"], unique=False)
    op.create_index("ix_agent_request_scope", "agent_request", ["module_scope"], unique=False)
    op.create_index("ix_agent_request_status", "agent_request", ["status"], unique=False)
    op.create_index("ix_agent_request_created_at", "agent_request", ["created_at"], unique=False)

    op.create_table(
        "generated_artifact",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("agent_request_id", sa.Integer(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("mime_type", sa.String(length=120), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("storage_url", sa.String(length=500), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["agent_request_id"], ["agent_request.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_generated_artifact_request", "generated_artifact", ["agent_request_id"], unique=False)
    op.create_index("ix_generated_artifact_expires", "generated_artifact", ["expires_at"], unique=False)
    op.create_index("ix_generated_artifact_sha256", "generated_artifact", ["sha256"], unique=False)


def downgrade():
    op.drop_index("ix_generated_artifact_sha256", table_name="generated_artifact")
    op.drop_index("ix_generated_artifact_expires", table_name="generated_artifact")
    op.drop_index("ix_generated_artifact_request", table_name="generated_artifact")
    op.drop_table("generated_artifact")

    op.drop_index("ix_agent_request_created_at", table_name="agent_request")
    op.drop_index("ix_agent_request_status", table_name="agent_request")
    op.drop_index("ix_agent_request_scope", table_name="agent_request")
    op.drop_index("ix_agent_request_requester", table_name="agent_request")
    op.drop_table("agent_request")
