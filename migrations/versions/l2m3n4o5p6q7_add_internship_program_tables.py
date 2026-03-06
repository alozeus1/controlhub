"""add internship program tables

Revision ID: l2m3n4o5p6q7
Revises: k1l2m3n4o5p6
Create Date: 2026-03-06
"""

from alembic import op
import sqlalchemy as sa


revision = "l2m3n4o5p6q7"
down_revision = "k1l2m3n4o5p6"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "internship_program",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="planned"),
        sa.Column("created_by_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_internship_program_name"),
    )
    op.create_index("ix_internship_program_status", "internship_program", ["status"], unique=False)

    op.create_table(
        "internship_cohort",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("program_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("track", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("created_by_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_id"], ["user.id"]),
        sa.ForeignKeyConstraint(["program_id"], ["internship_program.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("program_id", "name", name="uq_internship_cohort_program_name"),
    )
    op.create_index("ix_internship_cohort_program_id", "internship_cohort", ["program_id"], unique=False)
    op.create_index("ix_internship_cohort_status", "internship_cohort", ["status"], unique=False)

    op.create_table(
        "internship_cohort_member",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("cohort_id", sa.Integer(), nullable=False),
        sa.Column("person_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False, server_default="intern"),
        sa.Column("created_by_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["cohort_id"], ["internship_cohort.id"]),
        sa.ForeignKeyConstraint(["created_by_id"], ["user.id"]),
        sa.ForeignKeyConstraint(["person_id"], ["person.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("cohort_id", "person_id", "role", name="uq_internship_cohort_member_unique"),
    )
    op.create_index("ix_internship_cohort_member_cohort_id", "internship_cohort_member", ["cohort_id"], unique=False)
    op.create_index("ix_internship_cohort_member_person_id", "internship_cohort_member", ["person_id"], unique=False)

    op.create_table(
        "onboarding_template_item",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_by_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_onboarding_template_item_active", "onboarding_template_item", ["is_active"], unique=False)

    op.create_table(
        "person_onboarding_item",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("person_id", sa.Integer(), nullable=False),
        sa.Column("template_item_id", sa.Integer(), nullable=False),
        sa.Column("checked", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("checked_at", sa.DateTime(), nullable=True),
        sa.Column("updated_by_id", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["person_id"], ["person.id"]),
        sa.ForeignKeyConstraint(["template_item_id"], ["onboarding_template_item.id"]),
        sa.ForeignKeyConstraint(["updated_by_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("person_id", "template_item_id", name="uq_person_onboarding_item_unique"),
    )
    op.create_index("ix_person_onboarding_item_person_id", "person_onboarding_item", ["person_id"], unique=False)

    op.create_table(
        "internship_completion_checklist",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("person_id", sa.Integer(), nullable=False),
        sa.Column("project_submitted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("evaluation_done", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("admin_validated", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("updated_by_id", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["person_id"], ["person.id"]),
        sa.ForeignKeyConstraint(["updated_by_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("person_id", name="uq_internship_completion_person"),
    )

    op.create_table(
        "internship_certificate",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("person_id", sa.Integer(), nullable=False),
        sa.Column("certificate_no", sa.String(length=80), nullable=False),
        sa.Column("issued_at", sa.DateTime(), nullable=False),
        sa.Column("pdf_url", sa.String(length=500), nullable=True),
        sa.Column("issued_by_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["issued_by_id"], ["user.id"]),
        sa.ForeignKeyConstraint(["person_id"], ["person.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("certificate_no", name="uq_internship_certificate_no"),
    )
    op.create_index("ix_internship_certificate_person_id", "internship_certificate", ["person_id"], unique=False)


def downgrade():
    op.drop_index("ix_internship_certificate_person_id", table_name="internship_certificate")
    op.drop_table("internship_certificate")

    op.drop_table("internship_completion_checklist")

    op.drop_index("ix_person_onboarding_item_person_id", table_name="person_onboarding_item")
    op.drop_table("person_onboarding_item")

    op.drop_index("ix_onboarding_template_item_active", table_name="onboarding_template_item")
    op.drop_table("onboarding_template_item")

    op.drop_index("ix_internship_cohort_member_person_id", table_name="internship_cohort_member")
    op.drop_index("ix_internship_cohort_member_cohort_id", table_name="internship_cohort_member")
    op.drop_table("internship_cohort_member")

    op.drop_index("ix_internship_cohort_status", table_name="internship_cohort")
    op.drop_index("ix_internship_cohort_program_id", table_name="internship_cohort")
    op.drop_table("internship_cohort")

    op.drop_index("ix_internship_program_status", table_name="internship_program")
    op.drop_table("internship_program")
