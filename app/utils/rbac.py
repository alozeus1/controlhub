"""
Role-Based Access Control (RBAC) decorators and utilities.

Role hierarchy (higher = more privileges):
- superadmin (100): Full system access
- admin (50): Manage users (except superadmins), view all data
- viewer (10): Read-only access to admin panel
- user (1): Basic user, no admin panel access
"""
from functools import wraps
from flask import jsonify, request
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request
from app.models import User, ROLE_LEVELS


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

    Usage:
        @require_role("viewer")  # viewer, admin, superadmin can access
        @require_role("admin")   # admin, superadmin can access
        @require_role("superadmin")  # only superadmin can access
    """
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            # Verify JWT first
            try:
                verify_jwt_in_request()
            except Exception as e:
                return jsonify({"error": "Authentication required", "code": "AUTH_REQUIRED"}), 401

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


def require_active_user(fn):
    """
    Decorator that only checks if user is authenticated and active.
    Does not check role - use for endpoints available to all authenticated users.
    """
    @wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            verify_jwt_in_request()
        except Exception:
            return jsonify({"error": "Authentication required", "code": "AUTH_REQUIRED"}), 401

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
