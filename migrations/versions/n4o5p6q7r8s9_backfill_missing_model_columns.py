"""backfill employment compensation and cohort columns missing from earlier migrations

The Employment compensation/payment fields and InternshipCohort
department/specialization fields exist in app/models.py but were never added
by a migration, so databases built via `flask db upgrade` diverge from
databases built via `db.create_all()` (e.g. the test suite). This migration
closes that drift. Column-existence checks make it safe to run against
databases created either way.

Revision ID: n4o5p6q7r8s9
Revises: m3n4o5p6q7r8
Create Date: 2026-07-06
"""

from alembic import op
import sqlalchemy as sa


revision = "n4o5p6q7r8s9"
down_revision = "m3n4o5p6q7r8"
branch_labels = None
depends_on = None


EMPLOYMENT_COLUMNS = [
    sa.Column("compensation_type", sa.String(50), nullable=True),
    sa.Column("salary_amount", sa.Numeric(10, 2), nullable=True),
    sa.Column("currency", sa.String(10), nullable=True),
    sa.Column("contract_signed_date", sa.Date(), nullable=True),
    sa.Column("payment_status", sa.String(50), nullable=True),
    sa.Column("amount_paid", sa.Numeric(10, 2), nullable=True),
    sa.Column("amount_outstanding", sa.Numeric(10, 2), nullable=True),
    sa.Column("payment_due_date", sa.Date(), nullable=True),
    sa.Column("payment_frequency", sa.String(50), nullable=True),
]

COHORT_COLUMNS = [
    sa.Column("department", sa.String(100), nullable=True),
    sa.Column("specialization", sa.String(100), nullable=True),
]


def _existing_columns(table_name):
    inspector = sa.inspect(op.get_bind())
    return {col["name"] for col in inspector.get_columns(table_name)}


def _existing_unique_constraints(table_name):
    inspector = sa.inspect(op.get_bind())
    return {uc["name"] for uc in inspector.get_unique_constraints(table_name)}


def upgrade():
    existing = _existing_columns("employment")
    for column in EMPLOYMENT_COLUMNS:
        if column.name not in existing:
            op.add_column("employment", column)

    existing = _existing_columns("internship_cohort")
    for column in COHORT_COLUMNS:
        if column.name not in existing:
            op.add_column("internship_cohort", column)

    # One milestone review per person per review type; previously only
    # enforced in application code, which is race-prone.
    if "uq_milestone_review_person_type" not in _existing_unique_constraints("milestone_review"):
        op.create_unique_constraint(
            "uq_milestone_review_person_type", "milestone_review", ["person_id", "review_type"]
        )


def downgrade():
    if "uq_milestone_review_person_type" in _existing_unique_constraints("milestone_review"):
        op.drop_constraint("uq_milestone_review_person_type", "milestone_review", type_="unique")

    existing = _existing_columns("internship_cohort")
    for column in reversed(COHORT_COLUMNS):
        if column.name in existing:
            op.drop_column("internship_cohort", column.name)

    existing = _existing_columns("employment")
    for column in reversed(EMPLOYMENT_COLUMNS):
        if column.name in existing:
            op.drop_column("employment", column.name)
