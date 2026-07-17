"""add admin platform: roles, org settings, mfa, sso

Revision ID: s9t0u1v2w3x4
Revises: r8s9t0u1v2w3
Create Date: 2026-07-16
"""
from alembic import op
import sqlalchemy as sa

revision = "s9t0u1v2w3x4"
down_revision = "r8s9t0u1v2w3"
branch_labels = None
depends_on = None


# Seed data kept in sync with app/permissions.py.
_SYSTEM_ROLES = [
    ("superadmin", "Super Admin", 100),
    ("hr_admin", "HR Admin", 80),
    ("admin", "Admin", 50),
    ("people_manager", "People Manager", 40),
    ("team_lead", "Team Lead", 30),
    ("mentor", "Mentor", 20),
    ("viewer", "Viewer", 10),
    ("user", "User", 1),
]
_DEFAULT_PERMS = {
    "superadmin": ["view_dashboard", "manage_users", "view_audit_logs", "manage_secrets",
                   "manage_certificates", "manage_roles", "manage_mfa_policy", "manage_sso",
                   "manage_org_settings", "manage_integrations", "manage_deployments",
                   "manage_email_campaigns", "global_search"],
    "hr_admin": ["view_dashboard", "manage_users", "view_audit_logs", "global_search"],
    "admin": ["view_dashboard", "manage_users", "view_audit_logs", "manage_secrets",
              "manage_certificates", "manage_roles", "manage_mfa_policy", "manage_sso",
              "manage_org_settings", "manage_integrations", "manage_deployments",
              "manage_email_campaigns", "global_search"],
    "people_manager": ["view_dashboard", "manage_users", "global_search"],
    "team_lead": ["view_dashboard", "global_search"],
    "mentor": ["view_dashboard", "global_search"],
    "viewer": ["view_dashboard", "view_audit_logs", "global_search"],
    "user": ["view_dashboard"],
}


def upgrade():
    role = op.create_table(
        "role",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("label", sa.String(length=80), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("level", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("permissions", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    op.create_table(
        "org_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("org_name", sa.String(length=150), nullable=False,
                  server_default="Web Forx Technology Limited"),
        sa.Column("logo_url", sa.String(length=500), nullable=True),
        sa.Column("timezone", sa.String(length=64), nullable=False, server_default="UTC"),
        sa.Column("locale", sa.String(length=16), nullable=False, server_default="en-US"),
        sa.Column("allowed_signup_domains", sa.JSON(), nullable=True),
        sa.Column("mfa_required", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("mfa_required_roles", sa.JSON(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "user_mfa",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("secret_enc", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("pending", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("backup_codes", sa.JSON(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )

    op.create_table(
        "sso_config",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("provider", sa.String(length=20), nullable=False, server_default="oidc"),
        sa.Column("display_name", sa.String(length=80), nullable=True),
        sa.Column("discovery_url", sa.String(length=500), nullable=True),
        sa.Column("client_id", sa.String(length=255), nullable=True),
        sa.Column("client_secret_enc", sa.Text(), nullable=True),
        sa.Column("default_role", sa.String(length=50), nullable=False, server_default="user"),
        sa.Column("claim_role_map", sa.JSON(), nullable=True),
        sa.Column("role_claim", sa.String(length=80), nullable=True, server_default="groups"),
        sa.Column("allowed_domains", sa.JSON(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    # Seed system roles with default permissions.
    now = sa.func.now()
    op.bulk_insert(role, [
        {"name": n, "label": lbl, "level": lvl, "is_system": True,
         "permissions": _DEFAULT_PERMS.get(n, [])}
        for (n, lbl, lvl) in _SYSTEM_ROLES
    ])

    # Seed the org-settings singleton.
    op.execute(
        "INSERT INTO org_settings (id, org_name, timezone, locale, mfa_required) "
        "VALUES (1, 'Web Forx Technology Limited', 'UTC', 'en-US', false)"
    )
    # Seed the SSO singleton (disabled).
    op.execute(
        "INSERT INTO sso_config (id, enabled, provider, default_role, role_claim) "
        "VALUES (1, false, 'oidc', 'user', 'groups')"
    )


def downgrade():
    op.drop_table("sso_config")
    op.drop_table("user_mfa")
    op.drop_table("org_settings")
    op.drop_table("role")
