"""add new feature tables

Revision ID: h8i9j0k1l2m3
Revises: g7h8i9j0k1l2
Create Date: 2026-02-19
"""
from alembic import op
import sqlalchemy as sa

revision = 'h8i9j0k1l2m3'
down_revision = 'g7h8i9j0k1l2'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('secret',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('project', sa.String(100), nullable=True),
        sa.Column('environment', sa.String(50), nullable=True),
        sa.Column('value_encrypted', sa.Text(), nullable=False),
        sa.Column('tags', sa.JSON(), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('last_rotated_at', sa.DateTime(), nullable=True),
        sa.Column('created_by_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['created_by_id'], ['user.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_table('secret_access_log',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('secret_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('action', sa.String(20), nullable=False),
        sa.Column('ip_address', sa.String(45), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['secret_id'], ['secret.id']),
        sa.ForeignKeyConstraint(['user_id'], ['user.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_table('env_project',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_by_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['created_by_id'], ['user.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_table('env_config',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('environment', sa.String(50), nullable=False),
        sa.Column('key', sa.String(200), nullable=False),
        sa.Column('value', sa.Text(), nullable=True),
        sa.Column('is_secret', sa.Boolean(), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_by_id', sa.Integer(), nullable=False),
        sa.Column('updated_by_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['created_by_id'], ['user.id']),
        sa.ForeignKeyConstraint(['updated_by_id'], ['user.id']),
        sa.ForeignKeyConstraint(['project_id'], ['env_project.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('project_id', 'environment', 'key', name='uq_env_config')
    )
    op.create_table('incident',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('severity', sa.String(10), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('affected_services', sa.JSON(), nullable=True),
        sa.Column('commander_id', sa.Integer(), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('resolved_at', sa.DateTime(), nullable=True),
        sa.Column('root_cause', sa.Text(), nullable=True),
        sa.Column('created_by_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['commander_id'], ['user.id']),
        sa.ForeignKeyConstraint(['created_by_id'], ['user.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_table('incident_update',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('incident_id', sa.Integer(), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('status_change', sa.String(20), nullable=True),
        sa.Column('posted_by_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['incident_id'], ['incident.id']),
        sa.ForeignKeyConstraint(['posted_by_id'], ['user.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_table('runbook',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('slug', sa.String(255), nullable=False),
        sa.Column('content_md', sa.Text(), nullable=True),
        sa.Column('category', sa.String(100), nullable=True),
        sa.Column('tags', sa.JSON(), nullable=True),
        sa.Column('is_published', sa.Boolean(), nullable=True),
        sa.Column('created_by_id', sa.Integer(), nullable=False),
        sa.Column('updated_by_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['created_by_id'], ['user.id']),
        sa.ForeignKeyConstraint(['updated_by_id'], ['user.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('slug')
    )
    op.create_table('deployment',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('service_name', sa.String(100), nullable=False),
        sa.Column('version', sa.String(100), nullable=False),
        sa.Column('environment', sa.String(50), nullable=False),
        sa.Column('status', sa.String(20), nullable=True),
        sa.Column('is_rollback', sa.Boolean(), nullable=True),
        sa.Column('deployed_by_id', sa.Integer(), nullable=True),
        sa.Column('deployed_at', sa.DateTime(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('pipeline_url', sa.String(500), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['deployed_by_id'], ['user.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_table('certificate',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('domain', sa.String(255), nullable=False),
        sa.Column('issuer', sa.String(255), nullable=True),
        sa.Column('environment', sa.String(50), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('auto_renew', sa.Boolean(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('tags', sa.JSON(), nullable=True),
        sa.Column('created_by_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['created_by_id'], ['user.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_table('feature_flag',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project', sa.String(100), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('key', sa.String(100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('flag_type', sa.String(20), nullable=True),
        sa.Column('value', sa.JSON(), nullable=True),
        sa.Column('is_enabled', sa.Boolean(), nullable=True),
        sa.Column('environments', sa.JSON(), nullable=True),
        sa.Column('created_by_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['created_by_id'], ['user.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('project', 'key', name='uq_feature_flag')
    )
    op.create_table('license',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('vendor', sa.String(100), nullable=False),
        sa.Column('product', sa.String(100), nullable=False),
        sa.Column('license_type', sa.String(50), nullable=True),
        sa.Column('seats', sa.Integer(), nullable=True),
        sa.Column('seats_used', sa.Integer(), nullable=True),
        sa.Column('cost_monthly', sa.Numeric(12, 2), nullable=True),
        sa.Column('renewal_date', sa.Date(), nullable=True),
        sa.Column('owner_id', sa.Integer(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('status', sa.String(20), nullable=True),
        sa.Column('created_by_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['owner_id'], ['user.id']),
        sa.ForeignKeyConstraint(['created_by_id'], ['user.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_table('workflow_template',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('workflow_type', sa.String(20), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.Column('created_by_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['created_by_id'], ['user.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_table('workflow_template_step',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('template_id', sa.Integer(), nullable=False),
        sa.Column('order', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('assignee_role', sa.String(50), nullable=True),
        sa.ForeignKeyConstraint(['template_id'], ['workflow_template.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_table('workflow_run',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('template_id', sa.Integer(), nullable=False),
        sa.Column('subject_user_id', sa.Integer(), nullable=True),
        sa.Column('subject_name', sa.String(200), nullable=True),
        sa.Column('status', sa.String(20), nullable=True),
        sa.Column('started_by_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['template_id'], ['workflow_template.id']),
        sa.ForeignKeyConstraint(['subject_user_id'], ['user.id']),
        sa.ForeignKeyConstraint(['started_by_id'], ['user.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_table('workflow_run_step',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('run_id', sa.Integer(), nullable=False),
        sa.Column('template_step_id', sa.Integer(), nullable=False),
        sa.Column('order', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('status', sa.String(20), nullable=True),
        sa.Column('assigned_to_id', sa.Integer(), nullable=True),
        sa.Column('completed_by_id', sa.Integer(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['run_id'], ['workflow_run.id']),
        sa.ForeignKeyConstraint(['template_step_id'], ['workflow_template_step.id']),
        sa.ForeignKeyConstraint(['assigned_to_id'], ['user.id']),
        sa.ForeignKeyConstraint(['completed_by_id'], ['user.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_table('cost_entry',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('cloud_provider', sa.String(30), nullable=False),
        sa.Column('service_name', sa.String(100), nullable=False),
        sa.Column('team', sa.String(100), nullable=True),
        sa.Column('project', sa.String(100), nullable=True),
        sa.Column('amount', sa.Numeric(12, 2), nullable=False),
        sa.Column('currency', sa.String(3), nullable=True),
        sa.Column('period', sa.String(7), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_by_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['created_by_id'], ['user.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_table('budget_request',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('team', sa.String(100), nullable=True),
        sa.Column('project', sa.String(100), nullable=True),
        sa.Column('amount_requested', sa.Numeric(12, 2), nullable=False),
        sa.Column('currency', sa.String(3), nullable=True),
        sa.Column('justification', sa.Text(), nullable=True),
        sa.Column('status', sa.String(20), nullable=True),
        sa.Column('reviewed_by_id', sa.Integer(), nullable=True),
        sa.Column('review_notes', sa.Text(), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(), nullable=True),
        sa.Column('requested_by_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['reviewed_by_id'], ['user.id']),
        sa.ForeignKeyConstraint(['requested_by_id'], ['user.id']),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade():
    for table in ['budget_request','cost_entry','workflow_run_step','workflow_run',
                  'workflow_template_step','workflow_template','license','feature_flag',
                  'certificate','deployment','runbook','incident_update','incident',
                  'env_config','env_project','secret_access_log','secret']:
        op.drop_table(table)
