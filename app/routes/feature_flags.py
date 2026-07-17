from datetime import datetime

from flask import Blueprint, request, jsonify
from app.extensions import db, limiter
from app.models import FeatureFlag, FeatureFlagSdkKey
from app.utils.rbac import require_role, require_active_user
import re

feature_flags_bp = Blueprint("feature_flags", __name__)

def _slugify(s):
    return re.sub(r'[^a-z0-9_-]', '_', s.lower().strip())

@feature_flags_bp.get("/feature-flags")
@require_active_user
def list_flags():
    project = request.args.get("project")
    q = FeatureFlag.query
    if project:
        q = q.filter_by(project=project)
    flags = q.order_by(FeatureFlag.project, FeatureFlag.name).all()
    return jsonify({"items": [f.to_dict() for f in flags], "total": len(flags)})

@feature_flags_bp.get("/feature-flags/projects")
@require_active_user
def list_projects():
    from sqlalchemy import func
    projects = db.session.query(FeatureFlag.project, func.count(FeatureFlag.id)).group_by(FeatureFlag.project).all()
    return jsonify({"projects": [{"name": p, "count": c} for p, c in projects]})


@feature_flags_bp.get("/feature-flags/sdk/<project>")
@limiter.limit("60 per minute")
def sdk_endpoint(project):
    """
    SDK endpoint — returns enabled flags for a project as key:value.

    Deny-by-default (audit A-10): requires a valid, active SDK key scoped to this
    exact project, presented as `X-SDK-Key` or `?sdk_key=`. Keys are stored
    hashed at rest and are project-bound, preventing cross-project enumeration.
    """
    presented = request.headers.get("X-SDK-Key") or request.args.get("sdk_key")
    if not presented:
        return jsonify({"error": "SDK key required", "code": "SDK_KEY_REQUIRED"}), 401

    key = FeatureFlagSdkKey.query.filter_by(
        key_hash=FeatureFlagSdkKey.hash_key(presented),
        is_active=True,
    ).first()
    # Reject missing, revoked, or wrong-project keys identically to avoid oracles.
    if not key or key.revoked_at is not None or key.project != project:
        return jsonify({"error": "Invalid SDK key", "code": "SDK_KEY_INVALID"}), 403

    key.last_used_at = datetime.utcnow()
    db.session.commit()

    env = request.args.get("env", "production")
    flags = FeatureFlag.query.filter_by(project=project).all()
    result = {}
    for f in flags:
        if f.environments and env in f.environments:
            result[f.key] = f.environments[env]
        else:
            result[f.key] = f.is_enabled
    return jsonify(result)


# ─── SDK key management (admin) ───────────────────────────────────────────────

@feature_flags_bp.get("/feature-flags/sdk-keys")
@require_role("admin")
def list_sdk_keys():
    project = request.args.get("project")
    q = FeatureFlagSdkKey.query
    if project:
        q = q.filter_by(project=project)
    keys = q.order_by(FeatureFlagSdkKey.created_at.desc()).all()
    return jsonify({"items": [k.to_dict() for k in keys], "total": len(keys)})


@feature_flags_bp.post("/feature-flags/sdk-keys")
@require_role("admin")
def create_sdk_key():
    data = request.get_json() or {}
    project = (data.get("project") or "").strip()
    if not project:
        return jsonify({"error": "project is required"}), 400
    plaintext, key_hash, key_prefix = FeatureFlagSdkKey.generate_key()
    key = FeatureFlagSdkKey(
        project=project, name=data.get("name"),
        key_hash=key_hash, key_prefix=key_prefix,
        created_by_id=request.current_user.id,
    )
    db.session.add(key)
    db.session.commit()
    # The plaintext key is shown exactly once.
    return jsonify({**key.to_dict(), "key": plaintext}), 201


@feature_flags_bp.delete("/feature-flags/sdk-keys/<int:key_id>")
@require_role("admin")
def revoke_sdk_key(key_id):
    key = FeatureFlagSdkKey.query.get_or_404(key_id)
    key.is_active = False
    key.revoked_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"message": "Revoked", "id": key_id})


@feature_flags_bp.post("/feature-flags")
@require_role("admin")
def create_flag():
    data = request.get_json() or {}
    for f in ("project","name"):
        if not data.get(f):
            return jsonify({"error": f"{f} is required"}), 400
    key = data.get("key") or _slugify(data["name"])
    existing = FeatureFlag.query.filter_by(project=data["project"], key=key).first()
    if existing:
        return jsonify({"error": "Flag key already exists in this project"}), 409
    flag = FeatureFlag(
        project=data["project"], name=data["name"], key=key,
        description=data.get("description"),
        flag_type=data.get("flag_type", "boolean"),
        value=data.get("value", False),
        is_enabled=data.get("is_enabled", False),
        environments=data.get("environments"),
        created_by_id=request.current_user.id,
    )
    db.session.add(flag)
    db.session.commit()
    return jsonify(flag.to_dict()), 201

@feature_flags_bp.patch("/feature-flags/<int:flag_id>")
@require_role("admin")
def update_flag(flag_id):
    flag = FeatureFlag.query.get_or_404(flag_id)
    data = request.get_json() or {}
    for field in ("name","description","flag_type","value","is_enabled","environments"):
        if field in data:
            setattr(flag, field, data[field])
    db.session.commit()
    return jsonify(flag.to_dict())

@feature_flags_bp.post("/feature-flags/<int:flag_id>/toggle")
@require_role("admin")
def toggle_flag(flag_id):
    flag = FeatureFlag.query.get_or_404(flag_id)
    flag.is_enabled = not flag.is_enabled
    db.session.commit()
    return jsonify(flag.to_dict())

@feature_flags_bp.delete("/feature-flags/<int:flag_id>")
@require_role("admin")
def delete_flag(flag_id):
    flag = FeatureFlag.query.get_or_404(flag_id)
    db.session.delete(flag)
    db.session.commit()
    return jsonify({"message": "Deleted"})
