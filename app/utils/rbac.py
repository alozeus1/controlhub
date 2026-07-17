"""
Role-Based Access Control (RBAC) decorators and utilities.

Role hierarchy (higher = more privileges):
- superadmin (100): Full system access
- admin (50): Manage users (except superadmins), view all data
- viewer (10): Read-only access to admin panel
- user (1): Basic user, no admin panel access
"""
from functools import wraps
from flask import jsonify, request, g
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request
from app.models import User, ROLE_LEVELS


def _auth_error(exc):
    """Return a consistent 401 for auth failures, distinguishing a revoked or
    unverifiable token (fail-closed revocation) from a plain missing/invalid one."""
    try:
        from flask_jwt_extended.exceptions import RevokedTokenError
        if isinstance(exc, RevokedTokenError):
            return jsonify({
                "error": "Your session is no longer valid. Please sign in again.",
                "code": "TOKEN_REVOKED",
            }), 401
    except Exception:
        pass
    return jsonify({"error": "Authentication required", "code": "AUTH_REQUIRED"}), 401


def get_current_user():
    """Get the current authenticated user from JWT."""
    try:
        verify_jwt_in_request()
        user_id = int(get_jwt_identity())
        return User.query.get(user_id)
    except Exception:
        return None


def require_role(min_role):
    """
    Decorator that requires a minimum role level.
    Also enforces is_active check on every protected request.
    
    Supports both JWT authentication and API key authentication.

    Usage:
        @require_role("viewer")  # viewer, admin, superadmin can access
        @require_role("admin")   # admin, superadmin can access
        @require_role("superadmin")  # only superadmin can access
    """
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            # HUMAN-ONLY endpoint. Deny-by-default for API keys: a service-account
            # key presented here is rejected outright (secrets, users, roles,
            # org-settings, superadmin controls all use require_role/permission,
            # so this single rule keeps API keys out of every one of them).
            if request.headers.get("X-API-Key"):
                return jsonify({
                    "error": "API keys cannot access this endpoint. Use a scoped API endpoint.",
                    "code": "API_KEY_NOT_PERMITTED",
                }), 403

            # Fall back to JWT authentication
            try:
                verify_jwt_in_request()
            except Exception as exc:
                return _auth_error(exc)

            # Get user
            user_id = int(get_jwt_identity())
            user = User.query.get(user_id)

            if not user:
                return jsonify({"error": "User not found", "code": "USER_NOT_FOUND"}), 401

            # Check if user is active
            if not user.is_active:
                return jsonify({
                    "error": "Account is disabled. Contact an administrator.",
                    "code": "ACCOUNT_DISABLED"
                }), 403

            # Check role level
            min_level = ROLE_LEVELS.get(min_role, 0)
            user_level = user.role_level

            if user_level < min_level:
                return jsonify({
                    "error": f"Insufficient permissions. Required: {min_role}",
                    "code": "INSUFFICIENT_PERMISSIONS"
                }), 403

            # Store user in request context for use in route handlers
            request.current_user = user

            return fn(*args, **kwargs)
        return wrapper
    return decorator


def _reject_api_key_if_present():
    """Deny-by-default: API keys are not human principals. Returns a 403 response
    tuple if an X-API-Key header is present, else None."""
    if request.headers.get("X-API-Key"):
        return jsonify({
            "error": "API keys cannot access this endpoint. Use a scoped API endpoint.",
            "code": "API_KEY_NOT_PERMITTED",
        }), 403
    return None


def _authenticate_api_key():
    """
    Validate the X-API-Key header. Returns (api_key, None) on success or
    (None, (response, status)) on failure. Rejects invalid, expired, revoked,
    and disabled-service-account keys.
    """
    from app.services.service_accounts import ApiKeyService
    raw = request.headers.get("X-API-Key")
    api_key = ApiKeyService.validate_key(raw) if raw else None
    if not api_key:
        return None, (jsonify({"error": "Invalid API key", "code": "INVALID_API_KEY"}), 401)
    # Defense in depth beyond validate_key().
    if getattr(api_key, "is_valid", True) is False:
        return None, (jsonify({"error": "Invalid API key", "code": "INVALID_API_KEY"}), 401)
    sa = api_key.service_account
    if not sa or not sa.is_active:
        return None, (jsonify({"error": "Service account is disabled", "code": "SERVICE_ACCOUNT_DISABLED"}), 403)
    return api_key, None


def require_scope(required_scope, also_role="admin"):
    """
    Authorize an API-accessible endpoint.

    * Service-account API keys: allowed ONLY if the key holds a scope that
      satisfies `required_scope` (deny-by-default). The service account is set
      as the request principal; the creator is NEVER impersonated as a user.
    * Human users (JWT): allowed if their role >= `also_role` (set None to allow
      any active user).
    """
    from app.api_scopes import scope_satisfies

    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if request.headers.get("X-API-Key"):
                api_key, err = _authenticate_api_key()
                if err:
                    return err
                if not scope_satisfies(api_key.scopes, required_scope):
                    from app.utils.audit import log_action
                    try:
                        log_action("api_key.denied_scope", actor=None,
                                   target_type="service_account",
                                   target_id=api_key.service_account_id,
                                   target_label=required_scope,
                                   details={"key_prefix": api_key.key_prefix,
                                            "required_scope": required_scope})
                    except Exception:
                        pass
                    return jsonify({
                        "error": f"API key is missing the required scope: {required_scope}",
                        "code": "INSUFFICIENT_SCOPE",
                    }), 403
                g.api_key = api_key
                g.service_account = api_key.service_account
                request.service_account = api_key.service_account
                request.current_user = None  # never impersonate a human
                return fn(*args, **kwargs)

            # Human path
            try:
                verify_jwt_in_request()
            except Exception as exc:
                return _auth_error(exc)
            user = User.query.get(int(get_jwt_identity()))
            if not user:
                return jsonify({"error": "User not found", "code": "USER_NOT_FOUND"}), 401
            if not user.is_active:
                return jsonify({"error": "Account is disabled. Contact an administrator.",
                                "code": "ACCOUNT_DISABLED"}), 403
            if also_role is not None and user.role_level < ROLE_LEVELS.get(also_role, 0):
                return jsonify({"error": f"Insufficient permissions. Required: {also_role}",
                                "code": "INSUFFICIENT_PERMISSIONS"}), 403
            request.current_user = user
            return fn(*args, **kwargs)
        return wrapper
    return decorator


def require_active_user(fn):
    """
    Decorator that only checks if user is authenticated and active.
    Does not check role - use for endpoints available to all authenticated users.
    Human-only: API keys are rejected (they are not human principals).
    """
    @wraps(fn)
    def wrapper(*args, **kwargs):
        denied = _reject_api_key_if_present()
        if denied:
            return denied
        try:
            verify_jwt_in_request()
        except Exception as exc:
            return _auth_error(exc)

        user_id = int(get_jwt_identity())
        user = User.query.get(user_id)

        if not user:
            return jsonify({"error": "User not found", "code": "USER_NOT_FOUND"}), 401

        if not user.is_active:
            return jsonify({
                "error": "Account is disabled. Contact an administrator.",
                "code": "ACCOUNT_DISABLED"
            }), 403

        request.current_user = user
        return fn(*args, **kwargs)
    return wrapper


def can_manage_user(actor, target):
    """
    Check if actor can manage target user.
    
    Rules:
    - superadmin can manage anyone
    - admin can manage users with lower role level
    - No one can manage themselves (for role/status changes)
    """
    if actor.id == target.id:
        return False, "Cannot modify your own account"

    if actor.role == "superadmin":
        return True, None

    if actor.role_level > target.role_level:
        return True, None

    return False, "Cannot manage users with equal or higher privileges"


def can_assign_role(actor, new_role):
    """
    Check if actor can assign a specific role.

    Rules:
    - superadmin can assign any role
    - admin can only assign 'viewer' or 'user' roles
    """
    if actor.role == "superadmin":
        return True, None

    if actor.role == "admin" and new_role in ("viewer", "user"):
        return True, None

    return False, f"Cannot assign role '{new_role}'"


def count_superadmins():
    """Count the number of active superadmin users."""
    return User.query.filter_by(role="superadmin", is_active=True).count()


def is_last_superadmin(user):
    """Check if user is the last active superadmin."""
    if user.role != "superadmin":
        return False
    return count_superadmins() <= 1
