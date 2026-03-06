"""agent artifacts and google destinations

Revision ID: k1l2m3n4o5p6
Revises: j0k1l2m3n4o5
Create Date: 2026-03-05
"""

from alembic import op
import sqlalchemy as sa


revision = "k1l2m3n4o5p6"
down_revision = "j0k1l2m3n4o5"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "export_template",
        sa.Column("id", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("module_scope", sa.String(length=50), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("allowed_fields", sa.JSON(), nullable=False),
        sa.Column("masking_rules", sa.JSON(), nullable=True),
        sa.Column("classification", sa.String(length=50), nullable=False, server_default="internal"),
        sa.Column("pii_flag", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_export_template_module_scope", "export_template", ["module_scope"], unique=False)
    op.create_index("ix_export_template_active", "export_template", ["is_active"], unique=False)

    op.create_table(
        "external_destination",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("destination_type", sa.String(length=50), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("allowed_template_ids", sa.JSON(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_external_destination_type", "external_destination", ["destination_type"], unique=False)
    op.create_index("ix_external_destination_active", "external_destination", ["is_active"], unique=False)

    with op.batch_alter_table("generated_artifact", schema=None) as batch_op:
        batch_op.add_column(sa.Column("s3_bucket", sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column("s3_key", sa.String(length=500), nullable=True))
        batch_op.add_column(sa.Column("classification", sa.String(length=50), nullable=False, server_default="internal"))
        batch_op.add_column(sa.Column("pii_flag", sa.Boolean(), nullable=False, server_default=sa.text("false")))

    op.execute("UPDATE generated_artifact SET s3_bucket='legacy', s3_key=storage_url")

    with op.batch_alter_table("generated_artifact", schema=None) as batch_op:
        batch_op.alter_column("s3_bucket", existing_type=sa.String(length=120), nullable=False)
        batch_op.alter_column("s3_key", existing_type=sa.String(length=500), nullable=False)
        batch_op.drop_column("storage_url")


def downgrade():
    with op.batch_alter_table("generated_artifact", schema=None) as batch_op:
        batch_op.add_column(sa.Column("storage_url", sa.String(length=500), nullable=True))

    op.execute("UPDATE generated_artifact SET storage_url=s3_key")

    with op.batch_alter_table("generated_artifact", schema=None) as batch_op:
        batch_op.alter_column("storage_url", existing_type=sa.String(length=500), nullable=False)
        batch_op.drop_column("pii_flag")
        batch_op.drop_column("classification")
        batch_op.drop_column("s3_key")
        batch_op.drop_column("s3_bucket")

    op.drop_index("ix_external_destination_active", table_name="external_destination")
    op.drop_index("ix_external_destination_type", table_name="external_destination")
    op.drop_table("external_destination")

    op.drop_index("ix_export_template_active", table_name="export_template")
    op.drop_index("ix_export_template_module_scope", table_name="export_template")
    op.drop_table("export_template")
