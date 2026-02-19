"""
Service Account Routes

Endpoints for managing service accounts and API keys.
Feature-flagged: FEATURE_SERVICE_ACCOUNTS
"""
from datetime import datetime
from flask import Blueprint, jsonify, request, current_app

from app.utils.rbac import require_role
from app.services.service_accounts import ServiceAccountService, ApiKeyService

service_accounts_bp = Blueprint("service_accounts", __name__)


def check_feature_enabled():
    """Check if service accounts feature is enabled."""
    if not current_app.config.get("FEATURE_SERVICE_ACCOUNTS", False):
        return jsonify({
            "error": "Service accounts feature is not enabled",
            "code": "FEATURE_DISABLED"
        }), 403
    return None


# =============================================================================
# SERVICE ACCOUNT ENDPOINTS
# =============================================================================

@service_accounts_bp.get("/service-accounts")
@require_role("admin")
def list_service_accounts():
    """List all service accounts with pagination."""
    error = check_feature_enabled()
    if error:
        return error

    page = request.args.get("page", 1, type=int)
    page_size = min(request.args.get("page_size", 20, type=int), 100)
    is_active = request.args.get("is_active")
    search = request.args.get("search")

    is_active_bool = None
    if is_active is not None:
        is_active_bool = is_active.lower() == "true"

    result = ServiceAccountService.list_accounts(
        page=page,
        page_size=page_size,
        is_active=is_active_bool,
        search=search,
    )
    return jsonify(result)


@service_accounts_bp.get("/service-accounts/<int:account_id>")
@require_role("admin")
def get_service_account(account_id):
    """Get a single service account."""
    error = check_feature_enabled()
    if error:
        return error

    account = ServiceAccountService.get_account(account_id)
    if not account:
        return jsonify({"error": "Service account not found"}), 404

    return jsonify(account.to_dict())


@service_accounts_bp.post("/service-accounts")
@require_role("admin")
def create_service_account():
    """Create a new service account."""
    error = check_feature_enabled()
    if error:
        return error

    actor = request.current_user
    data = request.get_json()

    name = data.get("name", "").strip()
    if not name:
        return jsonify({"error": "Name is required"}), 400

    description = data.get("description", "").strip() or None

    account = ServiceAccountService.create_account(
        name=name,
        description=description,
        actor=actor,
    )

    return jsonify({
        "message": "Service account created",
        "service_account": account.to_dict(),
    }), 201


@service_accounts_bp.patch("/service-accounts/<int:account_id>")
@require_role("admin")
def update_service_account(account_id):
    """Update a service account (name, description, is_active)."""
    error = check_feature_enabled()
    if error:
        return error

    actor = request.current_user
    account = ServiceAccountService.get_account(account_id)
    
    if not account:
        return jsonify({"error": "Service account not found"}), 404

    data = request.get_json()
    
    name = data.get("name")
    description = data.get("description")
    is_active = data.get("is_active")

    account, changes = ServiceAccountService.update_account(
        account=account,
        actor=actor,
        name=name,
        description=description,
        is_active=is_active,
    )

    if changes:
        return jsonify({
            "message": "Service account updated",
            "service_account": account.to_dict(),
            "changes": changes,
        })

    return jsonify({
        "message": "No changes made",
        "service_account": account.to_dict(),
    })


# =============================================================================
# API KEY ENDPOINTS
# =============================================================================

@service_accounts_bp.get("/service-accounts/<int:account_id>/keys")
@require_role("admin")
def list_api_keys(account_id):
    """List API keys for a service account."""
    error = check_feature_enabled()
    if error:
        return error

    account = ServiceAccountService.get_account(account_id)
    if not account:
        return jsonify({"error": "Service account not found"}), 404

    include_revoked = request.args.get("include_revoked", "false").lower() == "true"
    keys = ApiKeyService.list_keys(account_id, include_revoked=include_revoked)

    return jsonify({
        "items": keys,
        "service_account": account.to_dict(),
    })


@service_accounts_bp.post("/service-accounts/<int:account_id>/keys")
@require_role("admin")
def create_api_key(account_id):
    """
    Create a new API key for a service account.
    
    Returns the plaintext key ONCE in the response.
    """
    error = check_feature_enabled()
    if error:
        return error

    actor = request.current_user
    account = ServiceAccountService.get_account(account_id)
    
    if not account:
        return jsonify({"error": "Service account not found"}), 404

    if not account.is_active:
        return jsonify({"error": "Cannot create key for inactive service account"}), 400

    data = request.get_json()
    name = data.get("name", "").strip()
    
    if not name:
        return jsonify({"error": "Key name is required"}), 400

    scopes = data.get("scopes")
    if scopes and not isinstance(scopes, list):
        return jsonify({"error": "Scopes must be a list"}), 400

    expires_at = None
    if data.get("expires_at"):
        try:
            expires_at = datetime.fromisoformat(data["expires_at"].replace("Z", "+00:00"))
        except ValueError:
            return jsonify({"error": "Invalid expires_at format"}), 400

    api_key, plaintext_key = ApiKeyService.create_key(
        service_account=account,
        name=name,
        actor=actor,
        scopes=scopes,
        expires_at=expires_at,
    )

    return jsonify({
        "message": "API key created",
        "api_key": api_key.to_dict(),
        "key": plaintext_key,  # Only returned once!
        "warning": "Store this key securely. It will not be shown again.",
    }), 201


@service_accounts_bp.post("/keys/<int:key_id>/revoke")
@require_role("admin")
def revoke_api_key(key_id):
    """Revoke an API key."""
    error = check_feature_enabled()
    if error:
        return error

    actor = request.current_user
    api_key = ApiKeyService.get_key(key_id)
    
    if not api_key:
        return jsonify({"error": "API key not found"}), 404

    if api_key.revoked_at:
        return jsonify({"error": "Key is already revoked"}), 400

    api_key = ApiKeyService.revoke_key(api_key, actor)

    return jsonify({
        "message": "API key revoked",
        "api_key": api_key.to_dict(),
    })


# =============================================================================
# FEATURE STATUS ENDPOINT
# =============================================================================

@service_accounts_bp.get("/service-accounts/status")
@require_role("viewer")
def get_feature_status():
    """Check if the service accounts feature is enabled."""
    enabled = current_app.config.get("FEATURE_SERVICE_ACCOUNTS", False)
    return jsonify({
        "feature": "service_accounts",
        "enabled": enabled,
    })
