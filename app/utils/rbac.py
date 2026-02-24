"""
Role-Based Access Control (RBAC) decorators and utilities.
"""
from functools import wraps
from flask import jsonify, request, current_app, g
from flask_jwt_extended import get_jwt_identity, get_jwt, verify_jwt_in_request
from app.auth.cognito_service import link_or_provision_user
from app.auth.token_verifier import TokenVerificationError, get_cognito_verifier
from app.models import User, ROLE_LEVELS


def _resolve_user_from_bearer():
    mode = current_app.config.get("AUTH_MODE", "hybrid")
    try:
        verify_jwt_in_request()
        user_id = int(get_jwt_identity())
        claims = get_jwt() or {}
        user = User.query.get(user_id)
        if user:
            request.auth_provider = claims.get("provider", "local")
        return user
    except Exception:
        if mode not in ("hybrid", "cognito"):
            return None

    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    token = auth.split(" ", 1)[1].strip()
    if not token:
        return None

    try:
        identity = get_cognito_verifier().verify(token)
        user = link_or_provision_user(identity)
        request.auth_provider = "cognito"
        return user
    except Exception:
        return None


def get_current_user():
    try:
        return _resolve_user_from_bearer()
    except Exception:
        return None


def require_role(min_role):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if current_app.config.get("FEATURE_SERVICE_ACCOUNTS", False):
                api_key_value = request.headers.get("X-API-Key")
                if api_key_value:
                    from app.services.service_accounts import ApiKeyService
                    api_key = ApiKeyService.validate_key(api_key_value)
                    if not api_key:
                        return jsonify({"error": "Invalid API key", "code": "INVALID_API_KEY"}), 401
                    g.api_key = api_key
                    g.service_account = api_key.service_account
                    min_level = ROLE_LEVELS.get(min_role, 0)
                    if min_level > ROLE_LEVELS.get("admin", 50):
                        return jsonify({"error": "API keys cannot access superadmin endpoints", "code": "INSUFFICIENT_PERMISSIONS"}), 403
                    request.current_user = api_key.service_account.creator
                    request.auth_provider = "api_key"
                    request.roles = [request.current_user.role]
                    return fn(*args, **kwargs)

            user = _resolve_user_from_bearer()
            if not user:
                return jsonify({"error": "Authentication required", "code": "AUTH_REQUIRED"}), 401

            if not user.is_active:
                return jsonify({"error": "Account is disabled. Contact an administrator.", "code": "ACCOUNT_DISABLED"}), 403

            min_level = ROLE_LEVELS.get(min_role, 0)
            if user.role_level < min_level:
                return jsonify({"error": f"Insufficient permissions. Required: {min_role}", "code": "INSUFFICIENT_PERMISSIONS"}), 403

            request.current_user = user
            request.roles = [user.role]
            return fn(*args, **kwargs)
        return wrapper
    return decorator


def require_active_user(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = _resolve_user_from_bearer()
        if not user:
            return jsonify({"error": "Authentication required", "code": "AUTH_REQUIRED"}), 401
        if not user.is_active:
            return jsonify({"error": "Account is disabled. Contact an administrator.", "code": "ACCOUNT_DISABLED"}), 403
        request.current_user = user
        request.roles = [user.role]
        return fn(*args, **kwargs)
    return wrapper


def can_manage_user(actor, target):
    if actor.id == target.id:
        return False, "Cannot modify your own account"
    if actor.role == "superadmin":
        return True, None
    if actor.role_level > target.role_level:
        return True, None
    return False, "Cannot manage users with equal or higher privileges"


def can_assign_role(actor, new_role):
    if actor.role == "superadmin":
        return True, None
    if actor.role == "admin" and new_role in ("viewer", "user"):
        return True, None
    return False, f"Cannot assign role '{new_role}'"


def is_last_superadmin(user):
    if user.role != "superadmin":
        return False
    count = User.query.filter_by(role="superadmin", is_active=True).count()
    return count <= 1
