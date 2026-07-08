"""add employee_review table (quarterly performance reviews)

Non-intern employees (including PoCs/team leads) get one performance review per
calendar quarter, aligned company-wide. Distinct from the intern BiweeklyReview
and MilestoneReview tracks.

Revision ID: p6q7r8s9t0u1
Revises: o5p6q7r8s9t0
Create Date: 2026-07-08
"""

from alembic import op
import sqlalchemy as sa


revision = "p6q7r8s9t0u1"
down_revision = "o5p6q7r8s9t0"
branch_labels = None
depends_on = None


def _has_table(name):
    inspector = sa.inspect(op.get_bind())
    return name in inspector.get_table_names()


def upgrade():
    if _has_table("employee_review"):
        return
    op.create_table(
        "employee_review",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("person_id", sa.Integer(), nullable=False),
        sa.Column("quarter", sa.String(length=10), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="pending_self"),
        sa.Column("self_report", sa.JSON(), nullable=True),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column("strengths", sa.Text(), nullable=True),
        sa.Column("concerns", sa.Text(), nullable=True),
        sa.Column("action_items", sa.JSON(), nullable=True),
        sa.Column("manager_notes", sa.Text(), nullable=True),
        sa.Column("ai_summary", sa.Text(), nullable=True),
        sa.Column("decision", sa.String(length=20), nullable=True),
        sa.Column("new_title", sa.String(length=150), nullable=True),
        sa.Column("reviewer_id", sa.Integer(), nullable=True),
        sa.Column("decision_date", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["person_id"], ["person.id"]),
        sa.ForeignKeyConstraint(["reviewer_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("person_id", "quarter", name="uq_employee_review_person_quarter"),
    )
    op.create_index("ix_employee_review_person_id", "employee_review", ["person_id"], unique=False)


def downgrade():
    if not _has_table("employee_review"):
        return
    op.drop_index("ix_employee_review_person_id", table_name="employee_review")
    op.drop_table("employee_review")
