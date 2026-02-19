"""
Assets Routes

Endpoints for IT asset inventory management.
Feature-flagged: FEATURE_ASSETS
"""
from datetime import datetime
from flask import Blueprint, jsonify, request, current_app

from app.utils.rbac import require_role
from app.services.assets import AssetService, ASSET_TYPES, ASSET_STATUSES

assets_bp = Blueprint("assets", __name__)


def check_feature_enabled():
    """Check if assets feature is enabled."""
    if not current_app.config.get("FEATURE_ASSETS", False):
        return jsonify({
            "error": "Assets feature is not enabled",
            "code": "FEATURE_DISABLED"
        }), 403
    return None


# =============================================================================
# ASSET ENDPOINTS
# =============================================================================

@assets_bp.get("/assets")
@require_role("viewer")
def list_assets():
    """List all assets with filters."""
    error = check_feature_enabled()
    if error:
        return error

    page = request.args.get("page", 1, type=int)
    page_size = min(request.args.get("page_size", 20, type=int), 100)
    asset_type = request.args.get("type")
    status = request.args.get("status")
    department = request.args.get("department")
    assigned_to_id = request.args.get("assigned_to_id", type=int)
    search = request.args.get("search")
    tags_param = request.args.get("tags")
    
    tags = None
    if tags_param:
        tags = [t.strip() for t in tags_param.split(",") if t.strip()]

    result = AssetService.list_assets(
        page=page,
        page_size=page_size,
        asset_type=asset_type,
        status=status,
        department=department,
        assigned_to_id=assigned_to_id,
        search=search,
        tags=tags,
    )
    return jsonify(result)


@assets_bp.get("/assets/<int:asset_id>")
@require_role("viewer")
def get_asset(asset_id):
    """Get a single asset."""
    error = check_feature_enabled()
    if error:
        return error

    asset = AssetService.get_asset(asset_id)
    if not asset:
        return jsonify({"error": "Asset not found"}), 404

    return jsonify(asset.to_dict())


@assets_bp.post("/assets")
@require_role("admin")
def create_asset():
    """Create a new asset."""
    error = check_feature_enabled()
    if error:
        return error

    actor = request.current_user
    data = request.get_json()

    name = data.get("name", "").strip()
    asset_type = data.get("type", "").strip()

    if not name:
        return jsonify({"error": "Asset name is required"}), 400
    if not asset_type:
        return jsonify({"error": "Asset type is required"}), 400

    # Parse dates if provided
    purchase_date = None
    warranty_expiry = None
    if data.get("purchase_date"):
        try:
            purchase_date = datetime.strptime(data["purchase_date"], "%Y-%m-%d").date()
        except ValueError:
            return jsonify({"error": "Invalid purchase_date format (use YYYY-MM-DD)"}), 400
    if data.get("warranty_expiry"):
        try:
            warranty_expiry = datetime.strptime(data["warranty_expiry"], "%Y-%m-%d").date()
        except ValueError:
            return jsonify({"error": "Invalid warranty_expiry format (use YYYY-MM-DD)"}), 400

    try:
        asset = AssetService.create_asset(
            name=name,
            asset_type=asset_type,
            actor=actor,
            asset_tag=data.get("asset_tag"),
            description=data.get("description"),
            location=data.get("location"),
            department=data.get("department"),
            assigned_to_id=data.get("assigned_to_id"),
            manufacturer=data.get("manufacturer"),
            model=data.get("model"),
            serial_number=data.get("serial_number"),
            ip_address=data.get("ip_address"),
            mac_address=data.get("mac_address"),
            purchase_date=purchase_date,
            warranty_expiry=warranty_expiry,
            attributes=data.get("attributes"),
            tags=data.get("tags"),
        )
        return jsonify({
            "message": "Asset created",
            "asset": asset.to_dict(),
        }), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@assets_bp.patch("/assets/<int:asset_id>")
@require_role("admin")
def update_asset(asset_id):
    """Update an asset."""
    error = check_feature_enabled()
    if error:
        return error

    asset = AssetService.get_asset(asset_id)
    if not asset:
        return jsonify({"error": "Asset not found"}), 404

    actor = request.current_user
    data = request.get_json()

    try:
        asset = AssetService.update_asset(
            asset=asset,
            actor=actor,
            **data,
        )
        return jsonify({
            "message": "Asset updated",
            "asset": asset.to_dict(),
        })
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@assets_bp.delete("/assets/<int:asset_id>")
@require_role("admin")
def delete_asset(asset_id):
    """Delete an asset."""
    error = check_feature_enabled()
    if error:
        return error

    asset = AssetService.get_asset(asset_id)
    if not asset:
        return jsonify({"error": "Asset not found"}), 404

    actor = request.current_user
    AssetService.delete_asset(asset, actor)

    return jsonify({"message": "Asset deleted"})


@assets_bp.get("/assets/<int:asset_id>/history")
@require_role("viewer")
def get_asset_history(asset_id):
    """Get asset change history."""
    error = check_feature_enabled()
    if error:
        return error

    asset = AssetService.get_asset(asset_id)
    if not asset:
        return jsonify({"error": "Asset not found"}), 404

    page = request.args.get("page", 1, type=int)
    page_size = min(request.args.get("page_size", 50, type=int), 100)

    result = AssetService.get_history(
        asset_id=asset_id,
        page=page,
        page_size=page_size,
    )
    return jsonify(result)


# =============================================================================
# METADATA ENDPOINTS
# =============================================================================

@assets_bp.get("/assets/metadata")
@require_role("viewer")
def get_metadata():
    """Get asset system metadata."""
    error = check_feature_enabled()
    if error:
        return error

    return jsonify({
        "asset_types": ASSET_TYPES,
        "statuses": ASSET_STATUSES,
        "departments": AssetService.get_departments(),
        "tags": AssetService.get_all_tags(),
    })


@assets_bp.get("/assets/stats")
@require_role("viewer")
def get_stats():
    """Get asset statistics."""
    error = check_feature_enabled()
    if error:
        return error

    return jsonify(AssetService.get_stats())


@assets_bp.post("/assets/generate-tag")
@require_role("admin")
def generate_tag():
    """Generate a unique asset tag for a type."""
    error = check_feature_enabled()
    if error:
        return error

    data = request.get_json()
    asset_type = data.get("type", "other")

    if asset_type not in ASSET_TYPES:
        return jsonify({"error": f"Invalid asset type: {asset_type}"}), 400

    tag = AssetService.generate_asset_tag(asset_type)
    return jsonify({"asset_tag": tag})
