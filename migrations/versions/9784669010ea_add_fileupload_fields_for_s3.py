"""Add FileUpload fields for S3

Revision ID: 9784669010ea
Revises: a1b2c3d4e5f6
Create Date: 2026-01-20 02:38:57.843790

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '9784669010ea'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade():
    # Add new columns to file_upload table
    with op.batch_alter_table('file_upload', schema=None) as batch_op:
        # Add original_filename (copy from filename initially)
        batch_op.add_column(sa.Column('original_filename', sa.String(255), nullable=True))
        batch_op.add_column(sa.Column('content_type', sa.String(100), nullable=True))
        batch_op.add_column(sa.Column('size_bytes', sa.BigInteger(), nullable=True))
        batch_op.add_column(sa.Column('s3_bucket', sa.String(100), nullable=True))
        batch_op.add_column(sa.Column('deleted_at', sa.DateTime(), nullable=True))
    
    # Backfill original_filename from filename
    op.execute("UPDATE file_upload SET original_filename = filename WHERE original_filename IS NULL")
    
    # Backfill s3_bucket with default value
    op.execute("UPDATE file_upload SET s3_bucket = 'controlhub-uploads' WHERE s3_bucket IS NULL")
    
    # Make columns non-nullable after backfill
    with op.batch_alter_table('file_upload', schema=None) as batch_op:
        batch_op.alter_column('original_filename', nullable=False)
        batch_op.alter_column('s3_bucket', nullable=False)
        # Expand s3_key to allow longer keys
        batch_op.alter_column('s3_key', type_=sa.String(500), existing_type=sa.String(255))


def downgrade():
    with op.batch_alter_table('file_upload', schema=None) as batch_op:
        batch_op.drop_column('deleted_at')
        batch_op.drop_column('s3_bucket')
        batch_op.drop_column('size_bytes')
        batch_op.drop_column('content_type')
        batch_op.drop_column('original_filename')
        batch_op.alter_column('s3_key', type_=sa.String(255), existing_type=sa.String(500))
