"""add integration, integration_log, audit_export_job tables

Revision ID: e5f6g7h8i9j0
Revises: d4e5f6g7h8i9
Create Date: 2026-01-23 16:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'e5f6g7h8i9j0'
down_revision = 'd4e5f6g7h8i9'
branch_labels = None
depends_on = None


def upgrade():
    # Integration table
    op.create_table(
        'integration',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('type', sa.String(length=30), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('config', sa.JSON(), nullable=False),
        sa.Column('events', sa.JSON(), nullable=True),
        sa.Column('is_enabled', sa.Boolean(), nullable=True, server_default='1'),
        sa.Column('last_triggered_at', sa.DateTime(), nullable=True),
        sa.Column('failure_count', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('created_by_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['created_by_id'], ['user.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_integration_type', 'integration', ['type'])
    op.create_index('ix_integration_is_enabled', 'integration', ['is_enabled'])

    # Integration Log table
    op.create_table(
        'integration_log',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('integration_id', sa.Integer(), nullable=False),
        sa.Column('event_type', sa.String(length=50), nullable=False),
        sa.Column('payload_summary', sa.String(length=255), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('response_code', sa.Integer(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('duration_ms', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['integration_id'], ['integration.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_integration_log_integration_id', 'integration_log', ['integration_id'])
    op.create_index('ix_integration_log_status', 'integration_log', ['status'])
    op.create_index('ix_integration_log_created_at', 'integration_log', ['created_at'])

    # Audit Export Job table
    op.create_table(
        'audit_export_job',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('export_format', sa.String(length=20), nullable=False),
        sa.Column('destination_type', sa.String(length=20), nullable=False),
        sa.Column('destination_config', sa.JSON(), nullable=True),
        sa.Column('filters', sa.JSON(), nullable=True),
        sa.Column('schedule', sa.String(length=50), nullable=True),
        sa.Column('last_run_at', sa.DateTime(), nullable=True),
        sa.Column('last_run_status', sa.String(length=20), nullable=True),
        sa.Column('last_run_records', sa.Integer(), nullable=True),
        sa.Column('is_enabled', sa.Boolean(), nullable=True, server_default='1'),
        sa.Column('created_by_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['created_by_id'], ['user.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_audit_export_job_is_enabled', 'audit_export_job', ['is_enabled'])


def downgrade():
    op.drop_index('ix_audit_export_job_is_enabled', table_name='audit_export_job')
    op.drop_table('audit_export_job')

    op.drop_index('ix_integration_log_created_at', table_name='integration_log')
    op.drop_index('ix_integration_log_status', table_name='integration_log')
    op.drop_index('ix_integration_log_integration_id', table_name='integration_log')
    op.drop_table('integration_log')

    op.drop_index('ix_integration_is_enabled', table_name='integration')
    op.drop_index('ix_integration_type', table_name='integration')
    op.drop_table('integration')
