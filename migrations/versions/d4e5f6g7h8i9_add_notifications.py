"""add notification_channel, alert_rule, alert_event tables

Revision ID: d4e5f6g7h8i9
Revises: c3d4e5f6g7h8
Create Date: 2026-01-23 15:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'd4e5f6g7h8i9'
down_revision = 'c3d4e5f6g7h8'
branch_labels = None
depends_on = None


def upgrade():
    # Notification Channel table
    op.create_table(
        'notification_channel',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('type', sa.String(length=20), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('config', sa.JSON(), nullable=False),
        sa.Column('is_enabled', sa.Boolean(), nullable=True, server_default='1'),
        sa.Column('created_by_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['created_by_id'], ['user.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_notification_channel_type', 'notification_channel', ['type'])
    op.create_index('ix_notification_channel_is_enabled', 'notification_channel', ['is_enabled'])

    # Alert Rule table
    op.create_table(
        'alert_rule',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('event_type', sa.String(length=50), nullable=False),
        sa.Column('severity', sa.String(length=20), nullable=True, server_default='medium'),
        sa.Column('conditions', sa.JSON(), nullable=True),
        sa.Column('channel_ids', sa.JSON(), nullable=False),
        sa.Column('is_enabled', sa.Boolean(), nullable=True, server_default='1'),
        sa.Column('created_by_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['created_by_id'], ['user.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_alert_rule_event_type', 'alert_rule', ['event_type'])
    op.create_index('ix_alert_rule_is_enabled', 'alert_rule', ['is_enabled'])

    # Alert Event table
    op.create_table(
        'alert_event',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('rule_id', sa.Integer(), nullable=True),
        sa.Column('event_type', sa.String(length=50), nullable=False),
        sa.Column('severity', sa.String(length=20), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=True),
        sa.Column('channels_notified', sa.JSON(), nullable=True),
        sa.Column('delivery_status', sa.String(length=20), nullable=True, server_default='pending'),
        sa.Column('delivery_details', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['rule_id'], ['alert_rule.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_alert_event_event_type', 'alert_event', ['event_type'])
    op.create_index('ix_alert_event_severity', 'alert_event', ['severity'])
    op.create_index('ix_alert_event_delivery_status', 'alert_event', ['delivery_status'])
    op.create_index('ix_alert_event_created_at', 'alert_event', ['created_at'])


def downgrade():
    op.drop_index('ix_alert_event_created_at', table_name='alert_event')
    op.drop_index('ix_alert_event_delivery_status', table_name='alert_event')
    op.drop_index('ix_alert_event_severity', table_name='alert_event')
    op.drop_index('ix_alert_event_event_type', table_name='alert_event')
    op.drop_table('alert_event')
    
    op.drop_index('ix_alert_rule_is_enabled', table_name='alert_rule')
    op.drop_index('ix_alert_rule_event_type', table_name='alert_rule')
    op.drop_table('alert_rule')
    
    op.drop_index('ix_notification_channel_is_enabled', table_name='notification_channel')
    op.drop_index('ix_notification_channel_type', table_name='notification_channel')
    op.drop_table('notification_channel')
