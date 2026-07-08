"""evolve to saas org management

Revision ID: m3n4o5p6q7r8
Revises: l2m3n4o5p6q7
Create Date: 2026-07-06
"""

from alembic import op
import sqlalchemy as sa


revision = "m3n4o5p6q7r8"
down_revision = "l2m3n4o5p6q7"
branch_labels = None
depends_on = None


def upgrade():
    # Alter person table
    op.add_column("person", sa.Column("taiga_username", sa.String(100), nullable=True))
    op.add_column("person", sa.Column("mattermost_username", sa.String(100), nullable=True))
    op.add_column("person", sa.Column("assigned_projects", sa.JSON(), nullable=True))
    op.add_column("person", sa.Column("signed_documents", sa.JSON(), nullable=True))
    op.add_column("person", sa.Column("risk_flags", sa.JSON(), nullable=True))
    op.add_column("person", sa.Column("growth_summary", sa.Text(), nullable=True))

    # Alter onboarding_template_item table
    op.add_column("onboarding_template_item", sa.Column("role_target", sa.String(50), nullable=False, server_default="intern"))
    op.add_column("onboarding_template_item", sa.Column("owner_role", sa.String(50), nullable=False, server_default="intern"))
    op.add_column("onboarding_template_item", sa.Column("days_to_complete", sa.Integer(), nullable=False, server_default="7"))

    # Alter person_onboarding_item table
    op.add_column("person_onboarding_item", sa.Column("due_date", sa.Date(), nullable=True))
    op.add_column("person_onboarding_item", sa.Column("status", sa.String(20), nullable=False, server_default="pending"))
    op.add_column("person_onboarding_item", sa.Column("item_type", sa.String(50), nullable=False, server_default="general"))

    # Create biweekly_review table
    op.create_table(
        "biweekly_review",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("person_id", sa.Integer(), nullable=False),
        sa.Column("reviewer_id", sa.Integer(), nullable=True),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="pending_intern"),
        sa.Column("intern_responses", sa.JSON(), nullable=True),
        sa.Column("manager_questions", sa.JSON(), nullable=True),
        sa.Column("manager_responses", sa.JSON(), nullable=True),
        sa.Column("score_progress", sa.Integer(), nullable=True),
        sa.Column("blockers", sa.Text(), nullable=True),
        sa.Column("strengths", sa.Text(), nullable=True),
        sa.Column("action_items", sa.JSON(), nullable=True),
        sa.Column("ai_summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["person_id"], ["person.id"]),
        sa.ForeignKeyConstraint(["reviewer_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_biweekly_review_person_id", "biweekly_review", ["person_id"], unique=False)

    # Create milestone_review table
    op.create_table(
        "milestone_review",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("person_id", sa.Integer(), nullable=False),
        sa.Column("review_type", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="draft"),
        sa.Column("compiled_score", sa.Float(), nullable=True),
        sa.Column("onboarding_progress", sa.Float(), nullable=True),
        sa.Column("taiga_activity_summary", sa.JSON(), nullable=True),
        sa.Column("mattermost_activity_summary", sa.JSON(), nullable=True),
        sa.Column("disciplinary_summary", sa.Text(), nullable=True),
        sa.Column("ai_recommendations", sa.Text(), nullable=True),
        sa.Column("ai_recommendations_approved", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("final_decision", sa.String(length=30), nullable=True),
        sa.Column("decision_by_id", sa.Integer(), nullable=True),
        sa.Column("decision_date", sa.Date(), nullable=True),
        sa.Column("report_card_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["decision_by_id"], ["user.id"]),
        sa.ForeignKeyConstraint(["person_id"], ["person.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_milestone_review_person_id", "milestone_review", ["person_id"], unique=False)


def downgrade():
    op.drop_index("ix_milestone_review_person_id", table_name="milestone_review")
    op.drop_table("milestone_review")

    op.drop_index("ix_biweekly_review_person_id", table_name="biweekly_review")
    op.drop_table("biweekly_review")

    op.drop_column("person_onboarding_item", "item_type")
    op.drop_column("person_onboarding_item", "status")
    op.drop_column("person_onboarding_item", "due_date")

    op.drop_column("onboarding_template_item", "days_to_complete")
    op.drop_column("onboarding_template_item", "owner_role")
    op.drop_column("onboarding_template_item", "role_target")

    op.drop_column("person", "growth_summary")
    op.drop_column("person", "risk_flags")
    op.drop_column("person", "signed_documents")
    op.drop_column("person", "assigned_projects")
    op.drop_column("person", "mattermost_username")
    op.drop_column("person", "taiga_username")
