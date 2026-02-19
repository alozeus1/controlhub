from flask import Blueprint, request, jsonify
from app.extensions import db
from app.models import Certificate
from app.utils.rbac import require_role, require_active_user
from datetime import datetime

certificates_bp = Blueprint("certificates", __name__)

@certificates_bp.get("/certificates")
@require_active_user
def list_certificates():
    env = request.args.get("environment")
    status = request.args.get("status")
    q = Certificate.query
    if env:
        q = q.filter_by(environment=env)
    certs = q.order_by(Certificate.expires_at.asc()).all()
    items = [c.to_dict() for c in certs]
    if status:
        items = [c for c in items if c["status"] == status]
    return jsonify({"items": items, "total": len(items)})

@certificates_bp.post("/certificates")
@require_role("admin")
def create_certificate():
    data = request.get_json() or {}
    if not data.get("domain") or not data.get("expires_at"):
        return jsonify({"error": "domain and expires_at are required"}), 400
    c = Certificate(
        domain=data["domain"], issuer=data.get("issuer"),
        environment=data.get("environment"),
        expires_at=datetime.fromisoformat(data["expires_at"]),
        auto_renew=data.get("auto_renew", False),
        notes=data.get("notes"), tags=data.get("tags"),
        created_by_id=request.current_user.id,
    )
    db.session.add(c)
    db.session.commit()
    return jsonify(c.to_dict()), 201

@certificates_bp.put("/certificates/<int:cert_id>")
@require_role("admin")
def update_certificate(cert_id):
    c = Certificate.query.get_or_404(cert_id)
    data = request.get_json() or {}
    for field in ("domain","issuer","environment","auto_renew","notes","tags"):
        if field in data:
            setattr(c, field, data[field])
    if "expires_at" in data:
        c.expires_at = datetime.fromisoformat(data["expires_at"])
    db.session.commit()
    return jsonify(c.to_dict())

@certificates_bp.delete("/certificates/<int:cert_id>")
@require_role("admin")
def delete_certificate(cert_id):
    c = Certificate.query.get_or_404(cert_id)
    db.session.delete(c)
    db.session.commit()
    return jsonify({"message": "Deleted"})

@certificates_bp.get("/certificates/expiring")
@require_active_user
def expiring_certs():
    """Certs expiring within 30 days."""
    from datetime import timedelta
    threshold = datetime.utcnow() + timedelta(days=30)
    certs = Certificate.query.filter(Certificate.expires_at <= threshold).order_by(Certificate.expires_at.asc()).all()
    return jsonify({"items": [c.to_dict() for c in certs], "total": len(certs)})
