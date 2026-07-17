"""
Permission catalog + checks for the admin platform.

Roles live in the DB (see models_admin.Role) but we keep a canonical catalog of
permission keys here, plus sensible defaults per legacy role so the system is
safe before any custom roles are created. Existing role-level checks
(app/utils/rbac.require_role) continue to work unchanged; new admin features use
`require_permission` / `has_permission` on top.
"""
from functools import wraps

from flask import jsonify, request
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request

# Canonical permission catalog (key -> human label + group).
PERMISSION_CATALOG = [
    {"key": "view_dashboard", "label": "View dashboard", "group": "General"},
    {"key": "manage_users", "label": "Manage users", "group": "People"},
    {"key": "view_audit_logs", "label": "View audit logs", "group": "Security"},
    {"key": "manage_secrets", "label": "Manage secrets", "group": "Security"},
    {"key": "manage_certificates", "label": "Manage certificates", "group": "Security"},
    {"key": "manage_roles", "label": "Manage roles & permissions", "group": "Security"},
    {"key": "manage_mfa_policy", "label": "Manage MFA policy", "group": "Security"},
    {"key": "manage_sso", "label": "Manage SSO / identity providers", "group": "Security"},
    {"key": "manage_org_settings", "label": "Manage organization settings", "group": "Admin"},
    {"key": "manage_integrations", "label": "Manage integrations", "group": "Admin"},
    {"key": "manage_deployments", "label": "Manage deployments", "group": "DevOps"},
    {"key": "manage_email_campaigns", "label": "Manage email campaigns", "group": "Marketing"},
    {"key": "global_search", "label": "Use global search", "group": "General"},
]

ALL_PERMISSION_KEYS = [p["key"] for p in PERMISSION_CATALOG]

# Default permission sets keyed by legacy role name. superadmin implicitly gets all.
DEFAULT_ROLE_PERMISSIONS = {
    "superadmin": list(ALL_PERMISSION_KEYS),
    "hr_admin": ["view_dashboard", "manage_users", "view_audit_logs", "global_search"],
    "admin": [
        "view_dashboard", "manage_users", "view_audit_logs", "manage_secrets",
        "manage_certificates", "manage_roles", "manage_mfa_policy", "manage_sso",
        "manage_org_settings", "manage_integrations", "manage_deployments",
        "manage_email_campaigns", "global_search",
    ],
    "people_manager": ["view_dashboard", "manage_users", "global_search"],
    "team_lead": ["view_dashboard", "global_search"],
    "mentor": ["view_dashboard", "global_search"],
    "viewer": ["view_dashboard", "view_audit_logs", "global_search"],
    "user": ["view_dashboard"],
}

# Seed rows for system roles (mirrors ROLE_LEVELS in models.py).
SYSTEM_ROLE_SEED = [
    {"name": "superadmin", "label": "Super Admin", "level": 100},
    {"name": "hr_admin", "label": "HR Admin", "level": 80},
    {"name": "admin", "label": "Admin", "level": 50},
    {"name": "people_manager", "label": "People Manager", "level": 40},
    {"name": "team_lead", "label": "Team Lead", "level": 30},
    {"name": "mentor", "label": "Mentor", "level": 20},
    {"name": "viewer", "label": "Viewer", "level": 10},
    {"name": "user", "label": "User", "level": 1},
]


def permissions_for_role(role_name):
    """Return the effective permission list for a role name (DB row first, else defaults)."""
    if role_name == "superadmin":
        return list(ALL_PERMISSION_KEYS)
    try:
        from app.models import Role
        row = Role.query.filter_by(name=role_name).first()
        if row and isinstance(row.permissions, list):
            return row.permissions
    except Exception:
        pass
    return DEFAULT_ROLE_PERMISSIONS.get(role_name, [])


def has_permission(user, key):
    """True if the user's role grants the permission key."""
    if user is None:
        return False
    if getattr(user, "role", None) == "superadmin":
        return True
    return key in permissions_for_role(getattr(user, "role", None))


def _resolve_actor():
    """Authenticate the request as a HUMAN user and return the acting User.

    Returns:
      * User            — authenticated human
      * None            — unauthenticated
      * "api_key"       — an API key was presented (permission endpoints are
                          human-only; the caller must reject with 403)
    """
    # Permission-gated endpoints (roles, org settings, SSO, MFA policy) are
    # human-only. API keys are a separate authorization domain and are denied
    # here regardless of scope — they must never manage roles/org/SSO/secrets.
    if request.headers.get("X-API-Key"):
        return "api_key"
    try:
        verify_jwt_in_request()
    except Exception:
        return None
    from app.models import User
    return User.query.get(int(get_jwt_identity()))


def require_permission(permission_key):
    """Decorator: require an authenticated, active user whose role grants `permission_key`."""
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            actor = _resolve_actor()
            if actor == "api_key":
                return jsonify({
                    "error": "API keys cannot access this endpoint. Use a scoped API endpoint.",
                    "code": "API_KEY_NOT_PERMITTED",
                }), 403
            if actor is None:
                return jsonify({"error": "Authentication required", "code": "AUTH_REQUIRED"}), 401
            if not getattr(actor, "is_active", True):
                return jsonify({"error": "Account is disabled", "code": "ACCOUNT_DISABLED"}), 403
            if not has_permission(actor, permission_key):
                return jsonify({
                    "error": f"Missing permission: {permission_key}",
                    "code": "INSUFFICIENT_PERMISSIONS",
                }), 403
            request.current_user = actor
            return fn(*args, **kwargs)
        return wrapper
    return decorator
