from datetime import datetime

from flask import Blueprint, jsonify, request

from app.extensions import db
from app.models import Secret, SecretAccessLog, ApprovalRequest
from app.services.secret_crypto import encrypt_secret, decrypt_secret
from app.utils.audit import log_action
from app.utils.rbac import require_role

secrets_bp = Blueprint("secrets", __name__)

SENSITIVE_SECRET_FIELDS = {"value"}


def _validation_error(details):
    return jsonify({
        "error": "Validation failed",
        "code": "VALIDATION_ERROR",
        "details": details,
    }), 400


def _parse_expires(value):
    if value in (None, ""):
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        raise ValueError("expires_at must be a valid ISO-8601 datetime")


def _mask_value(value):
    if value is None:
        return None
    return "***redacted***"


def _secret_changes(before: dict, after: dict):
    changes = {}
    for field in set(before.keys()) | set(after.keys()):
        if before.get(field) == after.get(field):
            continue
        if field in SENSITIVE_SECRET_FIELDS:
            changes[field] = {"from": _mask_value(before.get(field)), "to": _mask_value(after.get(field))}
        else:
            changes[field] = {"from": before.get(field), "to": after.get(field)}
    return changes


def _approved_reveal_request_or_none(request_id: int, secret_id: int, requester_id: int):
    approval = ApprovalRequest.query.get(request_id)
    if not approval:
        return None
    if approval.action != "secret.reveal":
        return None
    if approval.target_id != secret_id:
        return None
    if approval.requester_id != requester_id:
        return None
    if approval.status != "approved":
        return None
    return approval


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
    actor = request.current_user

    approval_request_id = request.args.get("approval_request_id", type=int)
    if approval_request_id:
        approval = _approved_reveal_request_or_none(approval_request_id, s.id, actor.id)
        if not approval:
            return jsonify({
                "error": "Invalid or non-approved reveal approval_request_id",
                "code": "INVALID_APPROVAL",
            }), 403
    else:
        # Optional governance gate: if a policy exists and requires approval,
        # return approval request instead of revealing immediately.
        from app.routes.governance import check_policy

        requires_approval, _policy, approval_request = check_policy(
            action="secret.reveal",
            actor=actor,
            target_type="secret",
            target_id=s.id,
            target_label=s.name,
            request_data={"secret_id": s.id},
        )
        if requires_approval and approval_request:
            return jsonify({
                "message": "Approval required for secret reveal",
                "code": "APPROVAL_REQUIRED",
                "approval_request": approval_request.to_dict(),
            }), 202

    revealed_value = decrypt_secret(s.value_encrypted)
    access_log = SecretAccessLog(
        secret_id=s.id,
        user_id=actor.id,
        action="read",
        ip_address=request.remote_addr,
    )
    db.session.add(access_log)
    db.session.commit()

    log_action(
        action="secret.revealed",
        actor=actor,
        target_type="secret",
        target_id=s.id,
        target_label=s.name,
        details={"project": s.project, "environment": s.environment},
    )

    return jsonify({"value": revealed_value})


@secrets_bp.post("/secrets")
@require_role("admin")
def create_secret():
    data = request.get_json() or {}
    errors = []
    if not isinstance(data.get("name"), str) or not data.get("name").strip():
        errors.append("name is required and must be a non-empty string")
    if not isinstance(data.get("value"), str) or not data.get("value"):
        errors.append("value is required and must be a non-empty string")
    if errors:
        return _validation_error(errors)

    try:
        expires_at = _parse_expires(data.get("expires_at"))
    except ValueError as exc:
        return _validation_error([str(exc)])

    actor = request.current_user
    s = Secret(
        name=data["name"].strip(),
        description=data.get("description"),
        project=data.get("project"),
        environment=data.get("environment"),
        value_encrypted=encrypt_secret(data["value"]),
        tags=data.get("tags"),
        expires_at=expires_at,
        created_by_id=actor.id,
    )
    db.session.add(s)
    db.session.commit()

    log_action(
        action="secret.created",
        actor=actor,
        target_type="secret",
        target_id=s.id,
        target_label=s.name,
        details={
            "project": s.project,
            "environment": s.environment,
            "tags": s.tags or [],
            "has_expiry": bool(s.expires_at),
        },
    )

    return jsonify({"message": "Secret created", "secret": s.to_dict()}), 201


@secrets_bp.put("/secrets/<int:secret_id>")
@require_role("admin")
def update_secret(secret_id):
    s = Secret.query.get_or_404(secret_id)
    data = request.get_json() or {}
    actor = request.current_user

    allowed_fields = {"name", "description", "project", "environment", "tags", "expires_at", "value"}
    unexpected_fields = sorted(set(data.keys()) - allowed_fields)
    if unexpected_fields:
        return _validation_error([f"Unexpected fields: {', '.join(unexpected_fields)}"])

    before = {
        "name": s.name,
        "description": s.description,
        "project": s.project,
        "environment": s.environment,
        "tags": s.tags,
        "expires_at": s.expires_at.isoformat() if s.expires_at else None,
        "value": "***redacted***",
    }

    if "name" in data:
        if not isinstance(data["name"], str) or not data["name"].strip():
            return _validation_error(["name must be a non-empty string"])
        s.name = data["name"].strip()
    for field in ("description", "project", "environment", "tags"):
        if field in data:
            setattr(s, field, data[field])
    if "expires_at" in data:
        try:
            s.expires_at = _parse_expires(data.get("expires_at"))
        except ValueError as exc:
            return _validation_error([str(exc)])
    if "value" in data:
        if not isinstance(data["value"], str) or not data["value"]:
            return _validation_error(["value must be a non-empty string when provided"])
        s.value_encrypted = encrypt_secret(data["value"])
        s.last_rotated_at = datetime.utcnow()
        access_log = SecretAccessLog(
            secret_id=s.id,
            user_id=actor.id,
            action="update",
            ip_address=request.remote_addr,
        )
        db.session.add(access_log)

    after = {
        "name": s.name,
        "description": s.description,
        "project": s.project,
        "environment": s.environment,
        "tags": s.tags,
        "expires_at": s.expires_at.isoformat() if s.expires_at else None,
        "value": "***redacted***" if "value" in data else "***unchanged***",
    }
    changes = _secret_changes(before, after)
    if not changes:
        return jsonify({"message": "No changes made", "secret": s.to_dict()})

    db.session.commit()
    log_action(
        action="secret.updated",
        actor=actor,
        target_type="secret",
        target_id=s.id,
        target_label=s.name,
        details={"changes": changes},
    )
    return jsonify({"message": "Secret updated", "secret": s.to_dict(), "changes": changes})


@secrets_bp.delete("/secrets/<int:secret_id>")
@require_role("admin")
def delete_secret(secret_id):
    s = Secret.query.get_or_404(secret_id)
    actor = request.current_user

    access_log = SecretAccessLog(
        secret_id=s.id,
        user_id=actor.id,
        action="delete",
        ip_address=request.remote_addr,
    )
    db.session.add(access_log)
    db.session.delete(s)
    db.session.commit()

    log_action(
        action="secret.deleted",
        actor=actor,
        target_type="secret",
        target_id=secret_id,
        target_label=s.name,
        details={"project": s.project, "environment": s.environment},
    )

    return jsonify({"message": "Deleted"}), 200


@secrets_bp.get("/secrets/<int:secret_id>/logs")
@require_role("admin")
def secret_logs(secret_id):
    Secret.query.get_or_404(secret_id)
    logs = (
        SecretAccessLog.query
        .filter_by(secret_id=secret_id)
        .order_by(SecretAccessLog.created_at.desc())
        .limit(50)
        .all()
    )
    return jsonify({"items": [l.to_dict() for l in logs]})

