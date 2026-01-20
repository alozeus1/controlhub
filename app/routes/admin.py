from flask import Blueprint, jsonify, request
from app.models import User, FileUpload, Job, AuditLog, ROLE_LEVELS
from app.extensions import db
from app.utils.rbac import (
    require_role,
    can_manage_user,
    can_assign_role,
    is_last_superadmin,
)
from app.utils.audit import (
    log_user_created,
    log_user_updated,
    log_role_changed,
    log_user_disabled,
    log_user_enabled,
)

admin_bp = Blueprint("admin", __name__)


def paginate_query(query, default_page_size=20, max_page_size=100):
    """Helper to paginate a SQLAlchemy query."""
    page = request.args.get("page", 1, type=int)
    page_size = request.args.get("page_size", default_page_size, type=int)
    page_size = min(page_size, max_page_size)

    pagination = query.paginate(page=page, per_page=page_size, error_out=False)

    return {
        "items": [item.to_dict() for item in pagination.items],
        "total": pagination.total,
        "page": pagination.page,
        "page_size": pagination.per_page,
        "pages": pagination.pages,
        "has_next": pagination.has_next,
        "has_prev": pagination.has_prev,
    }


# ============================================================================
# USERS
# ============================================================================

@admin_bp.get("/users")
@require_role("viewer")
def list_users():
    """List all users with pagination and filtering."""
    query = User.query

    # Filters
    role = request.args.get("role")
    if role:
        query = query.filter(User.role == role)

    is_active = request.args.get("is_active")
    if is_active is not None:
        query = query.filter(User.is_active == (is_active.lower() == "true"))

    search = request.args.get("search")
    if search:
        query = query.filter(User.email.ilike(f"%{search}%"))

    # Sort
    sort = request.args.get("sort", "created_at")
    order = request.args.get("order", "desc")
    if hasattr(User, sort):
        sort_col = getattr(User, sort)
        query = query.order_by(sort_col.desc() if order == "desc" else sort_col.asc())

    return jsonify(paginate_query(query))


@admin_bp.get("/users/<int:user_id>")
@require_role("viewer")
def get_user(user_id):
    """Get a single user by ID."""
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404
    return jsonify(user.to_dict())


@admin_bp.post("/users")
@require_role("admin")
def create_user():
    """Create a new user (admin only)."""
    actor = request.current_user
    data = request.get_json()

    email = data.get("email", "").strip().lower()
    password = data.get("password", "")
    role = data.get("role", "user")

    # Validation
    if not email or not password:
        return jsonify({"error": "Email and password are required"}), 400

    if len(password) < 8:
        return jsonify({"error": "Password must be at least 8 characters"}), 400

    if role not in ROLE_LEVELS:
        return jsonify({"error": f"Invalid role. Valid roles: {list(ROLE_LEVELS.keys())}"}), 400

    # Check if actor can assign this role
    can_assign, reason = can_assign_role(actor, role)
    if not can_assign:
        return jsonify({"error": reason}), 403

    # Check email uniqueness
    if User.query.filter_by(email=email).first():
        return jsonify({"error": "Email already exists"}), 400

    # Create user
    new_user = User(email=email, role=role)
    new_user.set_password(password)

    db.session.add(new_user)
    db.session.commit()

    # Audit log
    log_user_created(actor, new_user)

    return jsonify({"message": "User created", "user": new_user.to_dict()}), 201


@admin_bp.patch("/users/<int:user_id>")
@require_role("admin")
def update_user(user_id):
    """Update user (role, is_active). Admin only."""
    actor = request.current_user
    target = User.query.get(user_id)

    if not target:
        return jsonify({"error": "User not found"}), 404

    # Check if actor can manage this user
    can_manage, reason = can_manage_user(actor, target)
    if not can_manage:
        return jsonify({"error": reason}), 403

    data = request.get_json()
    changes = {}

    # Handle role change
    if "role" in data:
        new_role = data["role"]
        if new_role not in ROLE_LEVELS:
            return jsonify({"error": f"Invalid role. Valid roles: {list(ROLE_LEVELS.keys())}"}), 400

        can_assign, reason = can_assign_role(actor, new_role)
        if not can_assign:
            return jsonify({"error": reason}), 403

        # Bootstrap safety: prevent demoting last superadmin
        if target.role == "superadmin" and new_role != "superadmin":
            if is_last_superadmin(target):
                return jsonify({
                    "error": "Cannot demote the last superadmin. Promote another user first."
                }), 400

        if target.role != new_role:
            old_role = target.role
            target.role = new_role
            changes["role"] = {"from": old_role, "to": new_role}
            log_role_changed(actor, target, old_role, new_role)

    # Handle is_active change
    if "is_active" in data:
        new_status = bool(data["is_active"])

        # Bootstrap safety: prevent disabling last superadmin
        if target.role == "superadmin" and not new_status:
            if is_last_superadmin(target):
                return jsonify({
                    "error": "Cannot disable the last superadmin."
                }), 400

        if target.is_active != new_status:
            target.is_active = new_status
            changes["is_active"] = new_status
            if new_status:
                log_user_enabled(actor, target)
            else:
                log_user_disabled(actor, target)

    if changes:
        db.session.commit()
        return jsonify({"message": "User updated", "user": target.to_dict(), "changes": changes})

    return jsonify({"message": "No changes made", "user": target.to_dict()})


# Convenience aliases for disable/enable
@admin_bp.put("/users/<int:user_id>/disable")
@require_role("admin")
def disable_user(user_id):
    """Disable a user account."""
    request._cached_data = {"is_active": False}
    request.get_json = lambda: request._cached_data
    return update_user(user_id)


@admin_bp.put("/users/<int:user_id>/enable")
@require_role("admin")
def enable_user(user_id):
    """Enable a user account."""
    request._cached_data = {"is_active": True}
    request.get_json = lambda: request._cached_data
    return update_user(user_id)


# ============================================================================
# UPLOADS - Moved to app/routes/uploads.py
# ============================================================================
# Upload endpoints are now in uploads.py blueprint:
# - POST /admin/uploads - Upload file
# - GET /admin/uploads - List uploads  
# - GET /admin/uploads/<id> - Get single upload
# - GET /admin/uploads/<id>/download - Get presigned URL
# - DELETE /admin/uploads/<id> - Delete upload


# ============================================================================
# JOBS
# ============================================================================

@admin_bp.get("/jobs")
@require_role("viewer")
def list_jobs():
    """List all jobs with pagination."""
    query = Job.query

    status = request.args.get("status")
    if status:
        query = query.filter(Job.status == status)

    user_id = request.args.get("user_id", type=int)
    if user_id:
        query = query.filter(Job.user_id == user_id)

    query = query.order_by(Job.created_at.desc())

    pagination = query.paginate(
        page=request.args.get("page", 1, type=int),
        per_page=request.args.get("page_size", 20, type=int),
        error_out=False
    )

    return jsonify({
        "items": [
            {
                "id": j.id,
                "job_id": j.job_id,
                "user_id": j.user_id,
                "status": j.status,
                "created_at": j.created_at.isoformat() if j.created_at else None,
            }
            for j in pagination.items
        ],
        "total": pagination.total,
        "page": pagination.page,
        "page_size": pagination.per_page,
        "pages": pagination.pages,
    })


# ============================================================================
# AUDIT LOGS
# ============================================================================

@admin_bp.get("/audit-logs")
@require_role("viewer")
def list_audit_logs():
    """List audit logs with pagination and filtering."""
    query = AuditLog.query

    # Filters
    action = request.args.get("action")
    if action:
        query = query.filter(AuditLog.action == action)

    actor_id = request.args.get("actor_id", type=int)
    if actor_id:
        query = query.filter(AuditLog.actor_id == actor_id)

    target_type = request.args.get("target_type")
    if target_type:
        query = query.filter(AuditLog.target_type == target_type)

    target_id = request.args.get("target_id", type=int)
    if target_id:
        query = query.filter(AuditLog.target_id == target_id)

    search = request.args.get("search")
    if search:
        query = query.filter(
            (AuditLog.actor_email.ilike(f"%{search}%")) |
            (AuditLog.target_label.ilike(f"%{search}%"))
        )

    # Date range
    from_date = request.args.get("from_date")
    if from_date:
        from datetime import datetime as dt
        try:
            query = query.filter(AuditLog.created_at >= dt.fromisoformat(from_date))
        except ValueError:
            pass

    to_date = request.args.get("to_date")
    if to_date:
        from datetime import datetime as dt
        try:
            query = query.filter(AuditLog.created_at <= dt.fromisoformat(to_date))
        except ValueError:
            pass

    # Sort (default: newest first)
    query = query.order_by(AuditLog.created_at.desc())

    # Paginate
    page = request.args.get("page", 1, type=int)
    page_size = min(request.args.get("page_size", 50, type=int), 100)

    pagination = query.paginate(page=page, per_page=page_size, error_out=False)

    return jsonify({
        "items": [log.to_dict() for log in pagination.items],
        "total": pagination.total,
        "page": pagination.page,
        "page_size": pagination.per_page,
        "pages": pagination.pages,
        "has_next": pagination.has_next,
        "has_prev": pagination.has_prev,
    })


@admin_bp.get("/audit-logs/actions")
@require_role("viewer")
def list_audit_actions():
    """List all unique action types for filtering."""
    actions = db.session.query(AuditLog.action).distinct().all()
    return jsonify([a[0] for a in actions])
