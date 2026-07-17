from flask import Blueprint, request, jsonify, Response

from app.extensions import db
from app.models import EnvProject, EnvConfig
from app.utils.audit import log_action
from app.utils.rbac import require_role

env_configs_bp = Blueprint("env_configs", __name__)

ALLOWED_ENVS = {"dev", "staging", "prod"}


def _validation_error(details):
    return jsonify({
        "error": "Validation failed",
        "code": "VALIDATION_ERROR",
        "details": details,
    }), 400


def _redact_value(value):
    if value in (None, ""):
        return value
    return "***redacted***"


def _value_change_for_audit(old_value, new_value, old_is_secret, new_is_secret):
    if old_is_secret or new_is_secret:
        return {"from": _redact_value(old_value), "to": _redact_value(new_value)}
    return {"from": old_value, "to": new_value}


def _config_snapshot(config: EnvConfig):
    # Use decrypted_value so change-detection compares plaintext, not ciphertext
    # (secret values are redacted before they ever reach an audit record).
    return {
        "environment": config.environment,
        "key": config.key,
        "value": _redact_value(config.decrypted_value) if config.is_secret else config.decrypted_value,
        "is_secret": config.is_secret,
        "description": config.description,
    }


def _compute_changes(before: dict, after: dict):
    changes = {}
    for field in set(before.keys()) | set(after.keys()):
        if before.get(field) != after.get(field):
            changes[field] = {"from": before.get(field), "to": after.get(field)}
    return changes


def _validate_payload(data, require_env_and_key=False):
    errors = []
    if require_env_and_key:
        if not isinstance(data.get("environment"), str) or data["environment"] not in ALLOWED_ENVS:
            errors.append(f"environment must be one of: {', '.join(sorted(ALLOWED_ENVS))}")
        if not isinstance(data.get("key"), str) or not data["key"].strip():
            errors.append("key is required and must be a non-empty string")

    if "environment" in data and data["environment"] not in ALLOWED_ENVS:
        errors.append(f"environment must be one of: {', '.join(sorted(ALLOWED_ENVS))}")
    if "key" in data and (not isinstance(data["key"], str) or not data["key"].strip()):
        errors.append("key must be a non-empty string")
    if "is_secret" in data and not isinstance(data["is_secret"], bool):
        errors.append("is_secret must be boolean")
    if "value" in data and data["value"] is not None and not isinstance(data["value"], str):
        errors.append("value must be a string or null")
    if "description" in data and data["description"] is not None and not isinstance(data["description"], str):
        errors.append("description must be a string or null")

    return errors


@env_configs_bp.get("/env-projects")
@require_role("viewer")
def list_projects():
    projects = EnvProject.query.order_by(EnvProject.created_at.desc()).all()
    return jsonify({
        "items": [
            {
                **p.to_dict(),
                "config_count": EnvConfig.query.filter_by(project_id=p.id).count(),
            }
            for p in projects
        ],
        "total": len(projects),
    })


@env_configs_bp.post("/env-projects")
@require_role("admin")
def create_project():
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    if not name:
        return _validation_error(["name is required"])

    actor = request.current_user
    p = EnvProject(
        name=name,
        description=data.get("description"),
        created_by_id=actor.id,
    )
    db.session.add(p)
    db.session.commit()

    log_action(
        action="env_project.created",
        actor=actor,
        target_type="env_project",
        target_id=p.id,
        target_label=p.name,
    )
    return jsonify({"message": "Project created", "project": p.to_dict()}), 201


@env_configs_bp.delete("/env-projects/<int:project_id>")
@require_role("admin")
def delete_project(project_id):
    actor = request.current_user
    p = EnvProject.query.get_or_404(project_id)
    config_count = EnvConfig.query.filter_by(project_id=project_id).count()
    EnvConfig.query.filter_by(project_id=project_id).delete()
    db.session.delete(p)
    db.session.commit()

    log_action(
        action="env_project.deleted",
        actor=actor,
        target_type="env_project",
        target_id=project_id,
        target_label=p.name,
        details={"deleted_configs": config_count},
    )
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
    show_secrets = request.current_user.role in ("admin", "superadmin", "hr_admin")
    return jsonify({"items": [c.to_dict(show_secrets=show_secrets) for c in configs], "total": len(configs)})


@env_configs_bp.post("/env-projects/<int:project_id>/configs")
@require_role("admin")
def upsert_config(project_id):
    EnvProject.query.get_or_404(project_id)
    data = request.get_json() or {}
    errors = _validate_payload(data, require_env_and_key=True)
    if errors:
        return _validation_error(errors)

    actor = request.current_user
    key = data["key"].strip()
    env = data["environment"]

    existing = EnvConfig.query.filter_by(project_id=project_id, environment=env, key=key).first()
    if existing:
        old_value = existing.decrypted_value
        old_is_secret = existing.is_secret
        before = _config_snapshot(existing)
        if "value" in data:
            existing.value = data.get("value")
        if "is_secret" in data:
            existing.is_secret = data.get("is_secret")
        if "description" in data:
            existing.description = data.get("description")
        existing.updated_by_id = actor.id
        after = _config_snapshot(existing)
        changes = _compute_changes(before, after)
        if old_value != existing.value:
            changes["value"] = _value_change_for_audit(
                old_value,
                existing.value,
                old_is_secret,
                existing.is_secret,
            )
        db.session.commit()

        if changes:
            log_action(
                action="env_config.updated",
                actor=actor,
                target_type="env_config",
                target_id=existing.id,
                target_label=f"{env}:{key}",
                details={"changes": changes},
            )
        return jsonify({"message": "Config updated", "config": existing.to_dict(show_secrets=True), "changes": changes})

    c = EnvConfig(
        project_id=project_id,
        environment=env,
        key=key,
        value=data.get("value"),
        is_secret=data.get("is_secret", False),
        description=data.get("description"),
        created_by_id=actor.id,
    )
    db.session.add(c)
    db.session.commit()

    log_action(
        action="env_config.created",
        actor=actor,
        target_type="env_config",
        target_id=c.id,
        target_label=f"{env}:{key}",
        details={"is_secret": c.is_secret},
    )

    return jsonify({"message": "Config created", "config": c.to_dict(show_secrets=True)}), 201


@env_configs_bp.put("/env-projects/<int:project_id>/configs/<int:config_id>")
@require_role("admin")
def update_config(project_id, config_id):
    config = EnvConfig.query.filter_by(id=config_id, project_id=project_id).first_or_404()
    data = request.get_json() or {}
    if not data:
        return _validation_error(["Request body is required"])

    allowed = {"value", "description", "is_secret"}
    unexpected = sorted(set(data.keys()) - allowed)
    if unexpected:
        return _validation_error([f"Unexpected fields: {', '.join(unexpected)}"])

    errors = _validate_payload(data)
    if errors:
        return _validation_error(errors)

    actor = request.current_user
    old_value = config.decrypted_value
    old_is_secret = config.is_secret
    before = _config_snapshot(config)

    if "value" in data:
        config.value = data["value"]
    if "description" in data:
        config.description = data["description"]
    if "is_secret" in data:
        config.is_secret = data["is_secret"]
    config.updated_by_id = actor.id

    after = _config_snapshot(config)
    changes = _compute_changes(before, after)
    if old_value != config.value:
        changes["value"] = _value_change_for_audit(
            old_value,
            config.value,
            old_is_secret,
            config.is_secret,
        )
    if not changes:
        return jsonify({"message": "No changes made", "config": config.to_dict(show_secrets=True), "changes": {}})

    db.session.commit()
    log_action(
        action="env_config.updated",
        actor=actor,
        target_type="env_config",
        target_id=config.id,
        target_label=f"{config.environment}:{config.key}",
        details={"changes": changes},
    )
    return jsonify({"message": "Config updated", "config": config.to_dict(show_secrets=True), "changes": changes})


@env_configs_bp.delete("/env-projects/<int:project_id>/configs/<int:config_id>")
@require_role("admin")
def delete_config(project_id, config_id):
    actor = request.current_user
    c = EnvConfig.query.filter_by(id=config_id, project_id=project_id).first_or_404()
    label = f"{c.environment}:{c.key}"
    db.session.delete(c)
    db.session.commit()
    log_action(
        action="env_config.deleted",
        actor=actor,
        target_type="env_config",
        target_id=config_id,
        target_label=label,
    )
    return jsonify({"message": "Deleted"})


@env_configs_bp.get("/env-projects/<int:project_id>/export")
@require_role("admin")
def export_configs(project_id):
    actor = request.current_user
    env = request.args.get("environment", "dev")
    fmt = request.args.get("format", "dotenv")
    if env not in ALLOWED_ENVS:
        return _validation_error([f"environment must be one of: {', '.join(sorted(ALLOWED_ENVS))}"])
    if fmt not in {"dotenv", "json"}:
        return _validation_error(["format must be one of: dotenv, json"])

    configs = EnvConfig.query.filter_by(project_id=project_id, environment=env).order_by(EnvConfig.key).all()
    log_action(
        action="env_config.exported",
        actor=actor,
        target_type="env_project",
        target_id=project_id,
        target_label=env,
        details={"format": fmt, "count": len(configs)},
    )

    if fmt == "json":
        return jsonify({c.key: c.decrypted_value for c in configs})

    lines = [f'{c.key}={c.decrypted_value or ""}' for c in configs]
    return Response(
        "\n".join(lines),
        mimetype="text/plain",
        headers={"Content-Disposition": f"attachment; filename={env}.env"},
    )
