"""
Canonical API-key scope registry and deny-by-default matching.

Service-account API keys are a SEPARATE authorization domain from human users.
They are NOT granted human roles and MUST NOT be able to reach human-only or
platform-owner operations (secrets, user management, roles/permissions, org
settings, superadmin controls) — regardless of any scope, including wildcards.

Enforcement model (see app/utils/rbac.py):
  * Endpoints protected by `require_role` / `require_permission` are HUMAN-ONLY.
    An API key presented to one of these is rejected (403 API_KEY_NOT_PERMITTED).
  * Only endpoints explicitly annotated with `require_scope(<scope>)` accept API
    keys, and only when the key holds a scope that satisfies the requirement.

Scope grammar:
  * Exact scope, e.g. "email:send".
  * Namespace wildcard, e.g. "email:*", which satisfies any registered scope in
    that namespace. A bare "*" is intentionally NOT honored — it is not in the
    registry and therefore grants nothing.
Unknown / malformed scopes never satisfy a requirement.
"""

# key -> human-readable semantics. This is the authoritative allow-list.
SCOPE_REGISTRY = {
    "email:read": "Read email subscribers, lists, campaigns, settings and stats.",
    "email:write": "Create/update subscribers, lists, list membership, campaigns and email settings.",
    "email:send": "Trigger campaign sends and transactional email delivery.",
}

# Namespaces that support a ':*' wildcard grant.
WILDCARD_NAMESPACES = {"email"}


def is_registered_scope(scope: str) -> bool:
    return scope in SCOPE_REGISTRY


def normalize_scopes(raw):
    """Coerce a stored scopes value into a clean list of strings."""
    if not raw:
        return []
    if isinstance(raw, str):
        raw = [raw]
    return [str(s).strip() for s in raw if str(s).strip()]


def scope_satisfies(held_scopes, required_scope: str) -> bool:
    """
    Deny-by-default: return True only if `held_scopes` explicitly satisfies
    `required_scope`. The requirement itself must be a registered scope.
    """
    if not is_registered_scope(required_scope):
        # Never allow access against an unregistered/typo'd requirement.
        return False
    ns = required_scope.split(":", 1)[0]
    for s in normalize_scopes(held_scopes):
        if s == required_scope:
            return True
        if s.endswith(":*"):
            s_ns = s[:-2]
            if s_ns == ns and s_ns in WILDCARD_NAMESPACES:
                return True
        # A bare "*" or any other unregistered token grants nothing.
    return False
