from flask import Blueprint, request, jsonify
from app.extensions import db
from app.models import FeatureFlag
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
def sdk_endpoint(project):
    """Public SDK endpoint — returns all enabled flags for a project as key:value."""
    env = request.args.get("env", "production")
    flags = FeatureFlag.query.filter_by(project=project).all()
    result = {}
    for f in flags:
        # Check per-env override
        if f.environments and env in f.environments:
            result[f.key] = f.environments[env]
        else:
            result[f.key] = f.is_enabled
    return jsonify(result)

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
