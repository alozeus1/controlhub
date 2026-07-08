"""add PoC (team lead) review workflow columns

Interns can be assigned a PoC/team lead (employment.poc_person_id) who conducts
the biweekly review first; their assessment is recorded on the review and then
passed on to the manager (status pending_intern -> pending_poc ->
pending_manager -> completed).

Revision ID: o5p6q7r8s9t0
Revises: n4o5p6q7r8s9
Create Date: 2026-07-08
"""

from alembic import op
import sqlalchemy as sa


revision = "o5p6q7r8s9t0"
down_revision = "n4o5p6q7r8s9"
branch_labels = None
depends_on = None


EMPLOYMENT_COLUMNS = [
    ("poc_person_id", sa.Column("poc_person_id", sa.Integer(), sa.ForeignKey("person.id"), nullable=True)),
]

BIWEEKLY_COLUMNS = [
    ("poc_reviewer_id", sa.Column("poc_reviewer_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=True)),
    ("poc_notes", sa.Column("poc_notes", sa.Text(), nullable=True)),
    ("poc_submitted_at", sa.Column("poc_submitted_at", sa.DateTime(), nullable=True)),
]


def _existing_columns(table_name):
    inspector = sa.inspect(op.get_bind())
    return {col["name"] for col in inspector.get_columns(table_name)}


def upgrade():
    existing = _existing_columns("employment")
    for name, column in EMPLOYMENT_COLUMNS:
        if name not in existing:
            op.add_column("employment", column)

    existing = _existing_columns("biweekly_review")
    for name, column in BIWEEKLY_COLUMNS:
        if name not in existing:
            op.add_column("biweekly_review", column)


def downgrade():
    existing = _existing_columns("biweekly_review")
    for name, _column in reversed(BIWEEKLY_COLUMNS):
        if name in existing:
            op.drop_column("biweekly_review", name)

    existing = _existing_columns("employment")
    for name, _column in reversed(EMPLOYMENT_COLUMNS):
        if name in existing:
            op.drop_column("employment", name)
