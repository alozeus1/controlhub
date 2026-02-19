from flask import Blueprint, request, jsonify, current_app
from app.extensions import db
from app.models import Secret, SecretAccessLog
from app.utils.rbac import require_role, require_active_user
from datetime import datetime
import os

secrets_bp = Blueprint("secrets", __name__)

def _encrypt(value):
    """Simple base64 obfuscation - in production use Fernet with a key from env."""
    import base64
    key = current_app.config.get("SECRET_KEY", "dev-key").encode()[:32].ljust(32, b'0')
    # XOR-based simple encryption for demo; replace with Fernet in production
    encoded = base64.b64encode(value.encode()).decode()
    return f"enc:{encoded}"

def _decrypt(value):
    import base64
    if value.startswith("enc:"):
        return base64.b64decode(value[4:]).decode()
    return value

@secrets_bp.get("/secrets")
@require_role("viewer")
def list_secrets():
    project = request.args.get("project")
    environment = request.args.get("environment")
    q = Secret.query
    if project:
        q = q.filter_by(project=project)
    if environment:
        q = q.filter_by(environment=environment)
    secrets = q.order_by(Secret.created_at.desc()).all()
    return jsonify({"items": [s.to_dict() for s in secrets], "total": len(secrets)})

@secrets_bp.get("/secrets/<int:secret_id>")
@require_role("viewer")
def get_secret(secret_id):
    s = Secret.query.get_or_404(secret_id)
    return jsonify(s.to_dict())

@secrets_bp.post("/secrets/<int:secret_id>/reveal")
@require_role("admin")
def reveal_secret(secret_id):
    s = Secret.query.get_or_404(secret_id)
    user = request.current_user
    log = SecretAccessLog(secret_id=s.id, user_id=user.id, action="read",
                          ip_address=request.remote_addr)
    db.session.add(log)
    db.session.commit()
    return jsonify({"value": _decrypt(s.value_encrypted)})

@secrets_bp.post("/secrets")
@require_role("admin")
def create_secret():
    data = request.get_json() or {}
    if not data.get("name") or not data.get("value"):
        return jsonify({"error": "name and value are required"}), 400
    s = Secret(
        name=data["name"], description=data.get("description"),
        project=data.get("project"), environment=data.get("environment"),
        value_encrypted=_encrypt(data["value"]),
        tags=data.get("tags"), expires_at=None,
        created_by_id=request.current_user.id,
    )
    if data.get("expires_at"):
        s.expires_at = datetime.fromisoformat(data["expires_at"])
    db.session.add(s)
    db.session.commit()
    return jsonify(s.to_dict()), 201

@secrets_bp.put("/secrets/<int:secret_id>")
@require_role("admin")
def update_secret(secret_id):
    s = Secret.query.get_or_404(secret_id)
    data = request.get_json() or {}
    for field in ("name", "description", "project", "environment", "tags"):
        if field in data:
            setattr(s, field, data[field])
    if "value" in data:
        s.value_encrypted = _encrypt(data["value"])
        s.last_rotated_at = datetime.utcnow()
        log = SecretAccessLog(secret_id=s.id, user_id=request.current_user.id,
                               action="update", ip_address=request.remote_addr)
        db.session.add(log)
    if "expires_at" in data:
        s.expires_at = datetime.fromisoformat(data["expires_at"]) if data["expires_at"] else None
    db.session.commit()
    return jsonify(s.to_dict())

@secrets_bp.delete("/secrets/<int:secret_id>")
@require_role("admin")
def delete_secret(secret_id):
    s = Secret.query.get_or_404(secret_id)
    log = SecretAccessLog(secret_id=s.id, user_id=request.current_user.id,
                           action="delete", ip_address=request.remote_addr)
    db.session.add(log)
    db.session.delete(s)
    db.session.commit()
    return jsonify({"message": "Deleted"}), 200

@secrets_bp.get("/secrets/<int:secret_id>/logs")
@require_role("admin")
def secret_logs(secret_id):
    Secret.query.get_or_404(secret_id)
    logs = SecretAccessLog.query.filter_by(secret_id=secret_id).order_by(SecretAccessLog.created_at.desc()).limit(50).all()
    return jsonify({"items": [l.to_dict() for l in logs]})
