from flask import Blueprint, request, jsonify
from app.extensions import db
from app.models import Deployment
from app.utils.rbac import require_role, require_active_user

deployments_bp = Blueprint("deployments", __name__)

@deployments_bp.get("/deployments")
@require_active_user
def list_deployments():
    service = request.args.get("service")
    env = request.args.get("environment")
    page = int(request.args.get("page", 1))
    page_size = int(request.args.get("page_size", 20))
    q = Deployment.query
    if service:
        q = q.filter(Deployment.service_name.ilike(f"%{service}%"))
    if env:
        q = q.filter_by(environment=env)
    total = q.count()
    deployments = q.order_by(Deployment.deployed_at.desc()).offset((page-1)*page_size).limit(page_size).all()
    return jsonify({"items": [d.to_dict() for d in deployments], "total": total,
                    "page": page, "page_size": page_size})

@deployments_bp.post("/deployments")
@require_active_user
def create_deployment():
    data = request.get_json() or {}
    for f in ("service_name", "version", "environment"):
        if not data.get(f):
            return jsonify({"error": f"{f} is required"}), 400
    d = Deployment(
        service_name=data["service_name"], version=data["version"],
        environment=data["environment"], status=data.get("status", "success"),
        is_rollback=data.get("is_rollback", False),
        deployed_by_id=request.current_user.id,
        notes=data.get("notes"), pipeline_url=data.get("pipeline_url"),
    )
    db.session.add(d)
    db.session.commit()
    return jsonify(d.to_dict()), 201

@deployments_bp.get("/deployments/stats")
@require_active_user
def deployment_stats():
    from sqlalchemy import func
    total = Deployment.query.count()
    by_env = db.session.query(Deployment.environment, func.count(Deployment.id)).group_by(Deployment.environment).all()
    by_status = db.session.query(Deployment.status, func.count(Deployment.id)).group_by(Deployment.status).all()
    services = db.session.query(Deployment.service_name).distinct().all()
    return jsonify({
        "total": total,
        "by_environment": {e: c for e, c in by_env},
        "by_status": {s: c for s, c in by_status},
        "services": [s[0] for s in services],
    })

@deployments_bp.delete("/deployments/<int:deployment_id>")
@require_role("admin")
def delete_deployment(deployment_id):
    d = Deployment.query.get_or_404(deployment_id)
    db.session.delete(d)
    db.session.commit()
    return jsonify({"message": "Deleted"})
