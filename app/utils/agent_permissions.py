"""Permission mapping for governed agent service."""

from app.models import ROLE_LEVELS


AGENT_PERMISSIONS_BY_ROLE = {
    "superadmin": {"agent:run", "agent:export", "agent:write_external"},
    "hr_admin": {"agent:run", "agent:export", "agent:write_external"},
    "admin": {"agent:run", "agent:export", "agent:write_external"},
    "people_manager": {"agent:run", "agent:export"},
    "mentor": {"agent:run", "agent:export"},
    "viewer": {"agent:run", "agent:export"},
    "user": set(),
}


AGENT_PERMISSIONS = ["agent:run", "agent:export", "agent:write_external"]


def has_permission(user, permission):
    if not user:
        return False
    role_permissions = AGENT_PERMISSIONS_BY_ROLE.get(user.role, set())
    return permission in role_permissions


def ensure_permission(user, permission):
    if has_permission(user, permission):
        return True, None
    role_label = user.role if user else "anonymous"
    return False, f"Role '{role_label}' lacks required permission '{permission}'"


def known_roles_for_permission(permission):
    return sorted(
        role for role, perms in AGENT_PERMISSIONS_BY_ROLE.items() if permission in perms
    )


def role_level(role):
    return ROLE_LEVELS.get(role, 0)
