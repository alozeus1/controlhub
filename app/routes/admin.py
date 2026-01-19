from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.models import User, FileUpload, Job
from app.extensions import db
from functools import wraps

admin_bp = Blueprint("admin", __name__)

# Admin-only decorator
def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user_id = int(get_jwt_identity())
        user = User.query.get(user_id)

        if not user or user.role != "admin":
            return jsonify({"error": "Admin access required"}), 403

        return fn(*args, **kwargs)
    return wrapper


@admin_bp.get("/users")
@jwt_required()
@admin_required
def list_users():
    users = User.query.all()
    return jsonify([
        {"id": u.id, "email": u.email, "role": u.role, "created_at": u.created_at}
        for u in users
    ])


@admin_bp.get("/uploads")
@jwt_required()
@admin_required
def list_uploads():
    uploads = FileUpload.query.all()
    return jsonify([
        {"id": f.id, "user_id": f.user_id, "filename": f.filename, "created_at": f.created_at}
        for f in uploads
    ])


@admin_bp.get("/jobs")
@jwt_required()
@admin_required
def list_jobs():
    jobs = Job.query.all()
    return jsonify([
        {"id": j.id, "user_id": j.user_id, "status": j.status, "created_at": j.created_at}
        for j in jobs
    ])
