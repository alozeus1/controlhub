"""add hybrid auth fields

Revision ID: i9j0k1l2m3n4
Revises: h8i9j0k1l2m3
Create Date: 2026-02-23
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "i9j0k1l2m3n4"
down_revision = "h8i9j0k1l2m3"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("user", sa.Column("auth_provider", sa.String(length=20), nullable=False, server_default="local"))
    op.add_column("user", sa.Column("cognito_sub", sa.String(length=255), nullable=True))
    op.add_column("user", sa.Column("email_verified", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("user", sa.Column("phone_number", sa.String(length=50), nullable=True))
    op.add_column("user", sa.Column("phone_verified", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("user", sa.Column("mfa_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("user", sa.Column("last_login_at", sa.DateTime(), nullable=True))
    op.add_column("user", sa.Column("failed_login_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("user", sa.Column("locked_until", sa.DateTime(), nullable=True))
    op.add_column("user", sa.Column("last_login_ip", sa.String(length=45), nullable=True))
    op.add_column("user", sa.Column("last_login_user_agent", sa.String(length=255), nullable=True))

    op.create_index(op.f("ix_user_auth_provider"), "user", ["auth_provider"], unique=False)
    op.create_index(op.f("ix_user_cognito_sub"), "user", ["cognito_sub"], unique=True)

    op.execute("UPDATE \"user\" SET auth_provider='local' WHERE auth_provider IS NULL")
    op.execute("UPDATE \"user\" SET email_verified=true WHERE email_verified=false")

    op.alter_column("user", "auth_provider", server_default=None)
    op.alter_column("user", "email_verified", server_default=None)
    op.alter_column("user", "phone_verified", server_default=None)
    op.alter_column("user", "mfa_enabled", server_default=None)
    op.alter_column("user", "failed_login_count", server_default=None)


def downgrade():
    op.drop_index(op.f("ix_user_cognito_sub"), table_name="user")
    op.drop_index(op.f("ix_user_auth_provider"), table_name="user")

    op.drop_column("user", "last_login_user_agent")
    op.drop_column("user", "last_login_ip")
    op.drop_column("user", "locked_until")
    op.drop_column("user", "failed_login_count")
    op.drop_column("user", "last_login_at")
    op.drop_column("user", "mfa_enabled")
    op.drop_column("user", "phone_verified")
    op.drop_column("user", "phone_number")
    op.drop_column("user", "email_verified")
    op.drop_column("user", "cognito_sub")
    op.drop_column("user", "auth_provider")
