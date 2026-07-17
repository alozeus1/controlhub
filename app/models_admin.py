"""
Admin-platform models: roles/permissions, organization settings, MFA, and SSO.

Imported at the end of app/models.py so SQLAlchemy metadata + Flask-Migrate
register these tables.
"""
from datetime import datetime

from app.extensions import db


# ─── Roles & Permissions ──────────────────────────────────────────────────────

class Role(db.Model):
    """
    A role with an ordered privilege level and a set of permission keys.
    System roles mirror the legacy ROLE_LEVELS and cannot be deleted; admins can
    add custom roles and toggle permissions.
    """
    __tablename__ = "role"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False, unique=True)   # slug, e.g. "admin"
    label = db.Column(db.String(80), nullable=False)               # human label
    description = db.Column(db.Text, nullable=True)
    level = db.Column(db.Integer, nullable=False, default=10)       # privilege ordering
    is_system = db.Column(db.Boolean, nullable=False, default=False)
    permissions = db.Column(db.JSON, nullable=True)                 # list[str] of permission keys
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "label": self.label,
            "description": self.description,
            "level": self.level,
            "is_system": self.is_system,
            "permissions": self.permissions or [],
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# ─── Organization settings (singleton row, id=1) ──────────────────────────────

class OrgSettings(db.Model):
    __tablename__ = "org_settings"

    id = db.Column(db.Integer, primary_key=True)
    org_name = db.Column(db.String(150), nullable=False, default="Web Forx Technology Limited")
    logo_url = db.Column(db.String(500), nullable=True)
    timezone = db.Column(db.String(64), nullable=False, default="UTC")
    locale = db.Column(db.String(16), nullable=False, default="en-US")
    allowed_signup_domains = db.Column(db.JSON, nullable=True)  # list[str]; empty = allow any
    mfa_required = db.Column(db.Boolean, nullable=False, default=False)
    mfa_required_roles = db.Column(db.JSON, nullable=True)      # list[str] of role names
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            "org_name": self.org_name,
            "logo_url": self.logo_url,
            "timezone": self.timezone,
            "locale": self.locale,
            "allowed_signup_domains": self.allowed_signup_domains or [],
            "mfa_required": self.mfa_required,
            "mfa_required_roles": self.mfa_required_roles or [],
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    @classmethod
    def get(cls):
        row = cls.query.get(1)
        if not row:
            row = cls(id=1)
            db.session.add(row)
            db.session.commit()
        return row


# ─── MFA enrollment (per user) ────────────────────────────────────────────────

class UserMfa(db.Model):
    __tablename__ = "user_mfa"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, unique=True)
    secret_enc = db.Column(db.Text, nullable=True)      # encrypted TOTP secret (secret_crypto)
    enabled = db.Column(db.Boolean, nullable=False, default=False)
    pending = db.Column(db.Boolean, nullable=False, default=False)  # setup started, not confirmed
    backup_codes = db.Column(db.JSON, nullable=True)    # list of sha256 hashes of unused codes
    confirmed_at = db.Column(db.DateTime, nullable=True)
    # Brute-force lockout tracking
    failed_attempts = db.Column(db.Integer, nullable=False, default=0)
    locked_until = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = db.relationship("User", backref=db.backref("mfa", uselist=False))

    def to_dict(self):
        return {
            "enabled": self.enabled,
            "pending": self.pending,
            "backup_codes_remaining": len(self.backup_codes or []),
            "confirmed_at": self.confirmed_at.isoformat() if self.confirmed_at else None,
        }


# ─── SSO / OIDC configuration (singleton row, id=1) ───────────────────────────

class SsoConfig(db.Model):
    __tablename__ = "sso_config"

    id = db.Column(db.Integer, primary_key=True)
    enabled = db.Column(db.Boolean, nullable=False, default=False)
    provider = db.Column(db.String(20), nullable=False, default="oidc")  # oidc (saml later)
    display_name = db.Column(db.String(80), nullable=True)               # e.g. "Log in with Okta"
    discovery_url = db.Column(db.String(500), nullable=True)             # OIDC .well-known
    client_id = db.Column(db.String(255), nullable=True)
    client_secret_enc = db.Column(db.Text, nullable=True)               # encrypted
    default_role = db.Column(db.String(50), nullable=False, default="user")
    claim_role_map = db.Column(db.JSON, nullable=True)   # {claim_value: role_name}
    role_claim = db.Column(db.String(80), nullable=True, default="groups")  # which claim to map
    allowed_domains = db.Column(db.JSON, nullable=True)  # list[str] email domains permitted
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self, include_secret=False):
        d = {
            "enabled": self.enabled,
            "provider": self.provider,
            "display_name": self.display_name,
            "discovery_url": self.discovery_url,
            "client_id": self.client_id,
            "has_client_secret": bool(self.client_secret_enc),
            "default_role": self.default_role,
            "claim_role_map": self.claim_role_map or {},
            "role_claim": self.role_claim,
            "allowed_domains": self.allowed_domains or [],
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        return d

    @classmethod
    def get(cls):
        row = cls.query.get(1)
        if not row:
            row = cls(id=1)
            db.session.add(row)
            db.session.commit()
        return row
