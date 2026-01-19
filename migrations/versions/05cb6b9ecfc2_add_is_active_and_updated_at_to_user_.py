"""add is_active and updated_at to user model

Revision ID: 05cb6b9ecfc2
Revises: 05305ac13612
Create Date: 2026-01-19 21:48:57.130469

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '05cb6b9ecfc2'
down_revision = '05305ac13612'
branch_labels = None
depends_on = None


def upgrade():
    # Add is_active column with default True
    op.add_column('user', sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'))
    
    # Add updated_at column
    op.add_column('user', sa.Column('updated_at', sa.DateTime(), nullable=True))
    
    # Make role not nullable (it already has a default)
    op.alter_column('user', 'role',
                    existing_type=sa.VARCHAR(length=50),
                    nullable=False,
                    existing_server_default=sa.text("'user'::character varying"))


def downgrade():
    op.drop_column('user', 'updated_at')
    op.drop_column('user', 'is_active')
    op.alter_column('user', 'role',
                    existing_type=sa.VARCHAR(length=50),
                    nullable=True,
                    existing_server_default=sa.text("'user'::character varying"))
