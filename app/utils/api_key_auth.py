"""
API Key Authentication Middleware

Supports authentication via X-API-Key header for service accounts.
Does not interfere with existing JWT authentication.
"""
from functools import wraps
from flask import request, jsonify, g, current_app

from app.services.service_accounts import ApiKeyService


def get_api_key_from_request():
    """
    Extract API key from request headers.
    
    Supports:
    - X-API-Key: <key>
    """
    return request.headers.get("X-API-Key")


def validate_api_key_auth():
    """
    Validate API key authentication if present.
    
    Sets g.api_key and g.service_account if valid.
    Returns None if no API key present (allows fallback to JWT).
    Returns error tuple if invalid key.
    """
    if not current_app.config.get("FEATURE_SERVICE_ACCOUNTS", False):
        return None

    api_key_value = get_api_key_from_request()
    if not api_key_value:
        return None

    api_key = ApiKeyService.validate_key(api_key_value)
    if not api_key:
        return {"error": "Invalid API key", "code": "INVALID_API_KEY"}, 401

    g.api_key = api_key
    g.service_account = api_key.service_account
    return api_key


def require_api_key_scope(scope: str):
    """
    Decorator to require a specific scope for API key authentication.
    
    If request is authenticated via JWT (not API key), allows access.
    If request is authenticated via API key, checks for required scope.
    """
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            api_key = getattr(g, "api_key", None)
            
            if api_key:
                if not ApiKeyService.check_scope(api_key, scope):
                    return jsonify({
                        "error": f"API key does not have required scope: {scope}",
                        "code": "INSUFFICIENT_SCOPE"
                    }), 403
            
            return fn(*args, **kwargs)
        return wrapper
    return decorator


def api_key_or_jwt_required(fn):
    """
    Decorator that allows either API key or JWT authentication.
    
    Checks API key first, then falls back to JWT.
    Sets request.current_user for JWT, or g.service_account for API key.
    """
    @wraps(fn)
    def wrapper(*args, **kwargs):
        # Try API key first
        result = validate_api_key_auth()
        
        if isinstance(result, tuple):
            # Invalid API key
            return jsonify(result[0]), result[1]
        
        if result:
            # Valid API key - proceed without JWT check
            return fn(*args, **kwargs)
        
        # No API key - fall through to normal JWT handling
        return fn(*args, **kwargs)
    
    return wrapper


# Available API scopes for documentation
API_SCOPES = {
    "uploads.read": "Read upload information",
    "uploads.write": "Create and delete uploads",
    "users.read": "Read user information",
    "jobs.read": "Read job information",
    "jobs.write": "Create and manage jobs",
    "audit.read": "Read audit logs",
    "*": "Full access to all resources",
}


def get_available_scopes():
    """Return list of available API scopes."""
    return [{"scope": k, "description": v} for k, v in API_SCOPES.items()]
