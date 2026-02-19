"""add asset and asset_history tables

Revision ID: f6g7h8i9j0k1
Revises: e5f6g7h8i9j0
Create Date: 2026-01-23 17:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'f6g7h8i9j0k1'
down_revision = 'e5f6g7h8i9j0'
branch_labels = None
depends_on = None


def upgrade():
    # Asset table
    op.create_table(
        'asset',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('asset_tag', sa.String(length=50), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('asset_type', sa.String(length=30), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=True, server_default='active'),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('location', sa.String(length=100), nullable=True),
        sa.Column('department', sa.String(length=100), nullable=True),
        sa.Column('assigned_to_id', sa.Integer(), nullable=True),
        sa.Column('manufacturer', sa.String(length=100), nullable=True),
        sa.Column('model', sa.String(length=100), nullable=True),
        sa.Column('serial_number', sa.String(length=100), nullable=True),
        sa.Column('ip_address', sa.String(length=45), nullable=True),
        sa.Column('mac_address', sa.String(length=17), nullable=True),
        sa.Column('purchase_date', sa.Date(), nullable=True),
        sa.Column('warranty_expiry', sa.Date(), nullable=True),
        sa.Column('attributes', sa.JSON(), nullable=True),
        sa.Column('tags', sa.JSON(), nullable=True),
        sa.Column('created_by_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['assigned_to_id'], ['user.id'], ),
        sa.ForeignKeyConstraint(['created_by_id'], ['user.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('asset_tag')
    )
    op.create_index('ix_asset_asset_tag', 'asset', ['asset_tag'])
    op.create_index('ix_asset_asset_type', 'asset', ['asset_type'])
    op.create_index('ix_asset_status', 'asset', ['status'])
    op.create_index('ix_asset_assigned_to_id', 'asset', ['assigned_to_id'])
    op.create_index('ix_asset_department', 'asset', ['department'])

    # Asset History table
    op.create_table(
        'asset_history',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('asset_id', sa.Integer(), nullable=False),
        sa.Column('action', sa.String(length=30), nullable=False),
        sa.Column('changes', sa.JSON(), nullable=True),
        sa.Column('actor_id', sa.Integer(), nullable=True),
        sa.Column('actor_email', sa.String(length=120), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['actor_id'], ['user.id'], ),
        sa.ForeignKeyConstraint(['asset_id'], ['asset.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_asset_history_asset_id', 'asset_history', ['asset_id'])
    op.create_index('ix_asset_history_action', 'asset_history', ['action'])
    op.create_index('ix_asset_history_created_at', 'asset_history', ['created_at'])


def downgrade():
    op.drop_index('ix_asset_history_created_at', table_name='asset_history')
    op.drop_index('ix_asset_history_action', table_name='asset_history')
    op.drop_index('ix_asset_history_asset_id', table_name='asset_history')
    op.drop_table('asset_history')

    op.drop_index('ix_asset_department', table_name='asset')
    op.drop_index('ix_asset_assigned_to_id', table_name='asset')
    op.drop_index('ix_asset_status', table_name='asset')
    op.drop_index('ix_asset_asset_type', table_name='asset')
    op.drop_index('ix_asset_asset_tag', table_name='asset')
    op.drop_table('asset')
