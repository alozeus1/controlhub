from flask import Blueprint, request, jsonify
from app.extensions import db
from app.models import EnvProject, EnvConfig
from app.utils.rbac import require_role

env_configs_bp = Blueprint("env_configs", __name__)

@env_configs_bp.get("/env-projects")
@require_role("viewer")
def list_projects():
    projects = EnvProject.query.order_by(EnvProject.created_at.desc()).all()
    return jsonify({"items": [p.to_dict() for p in projects], "total": len(projects)})

@env_configs_bp.post("/env-projects")
@require_role("admin")
def create_project():
    data = request.get_json() or {}
    if not data.get("name"):
        return jsonify({"error": "name is required"}), 400
    p = EnvProject(name=data["name"], description=data.get("description"),
                   created_by_id=request.current_user.id)
    db.session.add(p)
    db.session.commit()
    return jsonify(p.to_dict()), 201

@env_configs_bp.delete("/env-projects/<int:project_id>")
@require_role("admin")
def delete_project(project_id):
    p = EnvProject.query.get_or_404(project_id)
    EnvConfig.query.filter_by(project_id=project_id).delete()
    db.session.delete(p)
    db.session.commit()
    return jsonify({"message": "Deleted"})

@env_configs_bp.get("/env-projects/<int:project_id>/configs")
@require_role("viewer")
def list_configs(project_id):
    EnvProject.query.get_or_404(project_id)
    env = request.args.get("environment")
    q = EnvConfig.query.filter_by(project_id=project_id)
    if env:
        q = q.filter_by(environment=env)
    configs = q.order_by(EnvConfig.key).all()
    show_secrets = request.current_user.role in ("admin", "superadmin")
    return jsonify({"items": [c.to_dict(show_secrets=show_secrets) for c in configs]})

@env_configs_bp.post("/env-projects/<int:project_id>/configs")
@require_role("admin")
def upsert_config(project_id):
    EnvProject.query.get_or_404(project_id)
    data = request.get_json() or {}
    if not data.get("key") or not data.get("environment"):
        return jsonify({"error": "key and environment are required"}), 400
    existing = EnvConfig.query.filter_by(
        project_id=project_id, environment=data["environment"], key=data["key"]
    ).first()
    if existing:
        existing.value = data.get("value", existing.value)
        existing.is_secret = data.get("is_secret", existing.is_secret)
        existing.description = data.get("description", existing.description)
        existing.updated_by_id = request.current_user.id
        db.session.commit()
        return jsonify(existing.to_dict(show_secrets=True))
    c = EnvConfig(project_id=project_id, environment=data["environment"], key=data["key"],
                  value=data.get("value"), is_secret=data.get("is_secret", False),
                  description=data.get("description"),
                  created_by_id=request.current_user.id)
    db.session.add(c)
    db.session.commit()
    return jsonify(c.to_dict(show_secrets=True)), 201

@env_configs_bp.delete("/env-projects/<int:project_id>/configs/<int:config_id>")
@require_role("admin")
def delete_config(project_id, config_id):
    c = EnvConfig.query.filter_by(id=config_id, project_id=project_id).first_or_404()
    db.session.delete(c)
    db.session.commit()
    return jsonify({"message": "Deleted"})

@env_configs_bp.get("/env-projects/<int:project_id>/export")
@require_role("admin")
def export_configs(project_id):
    env = request.args.get("environment", "dev")
    fmt = request.args.get("format", "dotenv")
    configs = EnvConfig.query.filter_by(project_id=project_id, environment=env).order_by(EnvConfig.key).all()
    if fmt == "json":
        return jsonify({c.key: c.value for c in configs})
    # dotenv format
    lines = [f'{c.key}={c.value or ""}' for c in configs]
    from flask import Response
    return Response("\n".join(lines), mimetype="text/plain",
                    headers={"Content-Disposition": f"attachment; filename={env}.env"})
