"""add governance tables (policy, approval_request, approval_decision)

Revision ID: b2c3d4e5f6g7
Revises: 9784669010ea
Create Date: 2026-01-23 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b2c3d4e5f6g7'
down_revision = '9784669010ea'
branch_labels = None
depends_on = None


def upgrade():
    # Policy table
    op.create_table(
        'policy',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('action', sa.String(length=100), nullable=False),
        sa.Column('environment', sa.String(length=50), nullable=True, server_default='all'),
        sa.Column('required_role', sa.String(length=50), nullable=True, server_default='admin'),
        sa.Column('requires_approval', sa.Boolean(), nullable=True, server_default='0'),
        sa.Column('approvals_required', sa.Integer(), nullable=True, server_default='1'),
        sa.Column('approver_role', sa.String(length=50), nullable=True, server_default='admin'),
        sa.Column('is_active', sa.Boolean(), nullable=True, server_default='1'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['created_by'], ['user.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_policy_action', 'policy', ['action'])
    op.create_index('ix_policy_is_active', 'policy', ['is_active'])

    # Approval Request table
    op.create_table(
        'approval_request',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('policy_id', sa.Integer(), nullable=False),
        sa.Column('requester_id', sa.Integer(), nullable=False),
        sa.Column('action', sa.String(length=100), nullable=False),
        sa.Column('target_type', sa.String(length=50), nullable=True),
        sa.Column('target_id', sa.Integer(), nullable=True),
        sa.Column('target_label', sa.String(length=255), nullable=True),
        sa.Column('request_data', sa.JSON(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=True, server_default='pending'),
        sa.Column('approvals_received', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('resolved_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['policy_id'], ['policy.id'], ),
        sa.ForeignKeyConstraint(['requester_id'], ['user.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_approval_request_status', 'approval_request', ['status'])
    op.create_index('ix_approval_request_action', 'approval_request', ['action'])
    op.create_index('ix_approval_request_requester_id', 'approval_request', ['requester_id'])

    # Approval Decision table
    op.create_table(
        'approval_decision',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('request_id', sa.Integer(), nullable=False),
        sa.Column('approver_id', sa.Integer(), nullable=False),
        sa.Column('decision', sa.String(length=20), nullable=False),
        sa.Column('comment', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['approver_id'], ['user.id'], ),
        sa.ForeignKeyConstraint(['request_id'], ['approval_request.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_approval_decision_request_id', 'approval_decision', ['request_id'])


def downgrade():
    op.drop_index('ix_approval_decision_request_id', table_name='approval_decision')
    op.drop_table('approval_decision')
    
    op.drop_index('ix_approval_request_requester_id', table_name='approval_request')
    op.drop_index('ix_approval_request_action', table_name='approval_request')
    op.drop_index('ix_approval_request_status', table_name='approval_request')
    op.drop_table('approval_request')
    
    op.drop_index('ix_policy_is_active', table_name='policy')
    op.drop_index('ix_policy_action', table_name='policy')
    op.drop_table('policy')
