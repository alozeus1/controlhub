"""add service_account and api_key tables

Revision ID: c3d4e5f6g7h8
Revises: b2c3d4e5f6g7
Create Date: 2026-01-23 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'c3d4e5f6g7h8'
down_revision = 'b2c3d4e5f6g7'
branch_labels = None
depends_on = None


def upgrade():
    # Service Account table
    op.create_table(
        'service_account',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True, server_default='1'),
        sa.Column('created_by_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['created_by_id'], ['user.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_service_account_name', 'service_account', ['name'])
    op.create_index('ix_service_account_is_active', 'service_account', ['is_active'])

    # API Key table
    op.create_table(
        'api_key',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('service_account_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('key_hash', sa.String(length=64), nullable=False),
        sa.Column('key_prefix', sa.String(length=8), nullable=False),
        sa.Column('scopes', sa.JSON(), nullable=True),
        sa.Column('last_used_at', sa.DateTime(), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('created_by_id', sa.Integer(), nullable=False),
        sa.Column('revoked_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['created_by_id'], ['user.id'], ),
        sa.ForeignKeyConstraint(['service_account_id'], ['service_account.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_api_key_key_hash', 'api_key', ['key_hash'])
    op.create_index('ix_api_key_key_prefix', 'api_key', ['key_prefix'])
    op.create_index('ix_api_key_service_account_id', 'api_key', ['service_account_id'])


def downgrade():
    op.drop_index('ix_api_key_service_account_id', table_name='api_key')
    op.drop_index('ix_api_key_key_prefix', table_name='api_key')
    op.drop_index('ix_api_key_key_hash', table_name='api_key')
    op.drop_table('api_key')
    
    op.drop_index('ix_service_account_is_active', table_name='service_account')
    op.drop_index('ix_service_account_name', table_name='service_account')
    op.drop_table('service_account')
