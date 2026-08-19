"""
Roles & Permissions management (feature 2).

DB-backed roles with per-role permission toggles and custom-role creation.
Gated behind the `manage_roles` permission. System roles cannot be deleted or
renamed, but their permissions can be adjusted (except superadmin, which always
holds every permission).
"""
import re

from flask import Blueprint, jsonify, request

from app.extensions import db
from app.models import Role, User
from app.permissions import (
    require_elevated_permission, PERMISSION_CATALOG, ALL_PERMISSION_KEYS,
    SYSTEM_ROLE_SEED, DEFAULT_ROLE_PERMISSIONS,
)
from app.utils.audit import log_action

roles_bp = Blueprint("roles", __name__)

_SLUG = re.compile(r"^[a-z][a-z0-9_]{1,48}$")


def _ensure_seeded():
    """Idempotently ensure system roles exist (covers DBs created via create_all)."""
    if Role.query.count() > 0:
        return
    for seed in SYSTEM_ROLE_SEED:
        db.session.add(Role(
            name=seed["name"], label=seed["label"], level=seed["level"],
            is_system=True, permissions=DEFAULT_ROLE_PERMISSIONS.get(seed["name"], []),
        ))
    db.session.commit()


@roles_bp.get("/permissions/catalog")
@require_elevated_permission("manage_roles")
def permissions_catalog():
    return jsonify({"permissions": PERMISSION_CATALOG})


@roles_bp.get("/roles")
@require_elevated_permission("manage_roles")
def list_roles():
    _ensure_seeded()
    roles = Role.query.order_by(Role.level.desc()).all()
    # attach user counts per role
    counts = dict(db.session.query(User.role, db.func.count(User.id)).group_by(User.role).all())
    out = []
    for r in roles:
        d = r.to_dict()
        d["user_count"] = int(counts.get(r.name, 0))
        out.append(d)
    return jsonify({"roles": out})


@roles_bp.post("/roles")
@require_elevated_permission("manage_roles")
def create_role():
    _ensure_seeded()
    data = request.get_json() or {}
    name = (data.get("name") or "").strip().lower()
    label = (data.get("label") or "").strip()
    if not _SLUG.match(name):
        return jsonify({"error": "name must be a lowercase slug (letters, digits, underscore)"}), 400
    if not label:
        return jsonify({"error": "label is required"}), 400
    if Role.query.filter_by(name=name).first():
        return jsonify({"error": "A role with that name already exists"}), 409
    perms = [p for p in (data.get("permissions") or []) if p in ALL_PERMISSION_KEYS]
    level = int(data.get("level", 15))
    # Custom roles cannot exceed admin level to avoid privilege escalation.
    level = max(1, min(level, 49))
    role = Role(name=name, label=label, description=data.get("description"),
                level=level, is_system=False, permissions=perms)
    db.session.add(role)
    db.session.commit()
    log_action("role.created", actor=getattr(request, "current_user", None),
               target_type="role", target_id=role.id, target_label=name,
               details={"permissions": perms})
    return jsonify(role.to_dict()), 201


@roles_bp.patch("/roles/<int:role_id>")
@require_elevated_permission("manage_roles")
def update_role(role_id):
    _ensure_seeded()
    role = Role.query.get(role_id)
    if not role:
        return jsonify({"error": "Role not found"}), 404
    data = request.get_json() or {}

    if role.name == "superadmin":
        return jsonify({"error": "The superadmin role cannot be modified"}), 403

    if "permissions" in data:
        role.permissions = [p for p in (data["permissions"] or []) if p in ALL_PERMISSION_KEYS]
    if not role.is_system:
        if "label" in data and str(data["label"]).strip():
            role.label = str(data["label"]).strip()
        if "description" in data:
            role.description = data["description"]
        if "level" in data:
            role.level = max(1, min(int(data["level"]), 49))
    db.session.commit()
    log_action("role.updated", actor=getattr(request, "current_user", None),
               target_type="role", target_id=role.id, target_label=role.name,
               details={"permissions": role.permissions})
    return jsonify(role.to_dict())


@roles_bp.delete("/roles/<int:role_id>")
@require_elevated_permission("manage_roles")
def delete_role(role_id):
    role = Role.query.get(role_id)
    if not role:
        return jsonify({"error": "Role not found"}), 404
    if role.is_system:
        return jsonify({"error": "System roles cannot be deleted"}), 403
    in_use = User.query.filter_by(role=role.name).count()
    if in_use > 0:
        return jsonify({"error": f"{in_use} user(s) still have this role; reassign them first"}), 409
    db.session.delete(role)
    db.session.commit()
    log_action("role.deleted", actor=getattr(request, "current_user", None),
               target_type="role", target_label=role.name)
    return jsonify({"deleted": True})
