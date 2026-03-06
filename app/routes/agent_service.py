import io
from datetime import datetime, timedelta

from flask import Blueprint, current_app, jsonify, request, send_file

from app.extensions import db
from app.models import AgentRequest, ApprovalRequest, ExternalDestination, GeneratedArtifact, Policy
from app.services.agent_service import (
    APPROVAL_ROW_THRESHOLD_DEFAULT,
    evaluate_approval_requirements,
    process_agent_request,
    publish_generated_artifact,
)
from app.services.agent_templates import get_template, list_templates
from app.services.agent_tools import (
    LOCAL_ARTIFACT_BUCKET,
    SUPPORTED_DESTINATION_TYPES,
    SUPPORTED_MODULE_SCOPES,
    SUPPORTED_OUTPUT_TYPES,
    apply_masking,
    enforce_template_fields,
    generate_presigned_download,
    query_module_rows,
    read_artifact_bytes,
    resolve_requested_fields,
)
from app.utils.agent_permissions import AGENT_PERMISSIONS, ensure_permission
from app.utils.audit import log_action
from app.utils.rbac import require_role


agent_bp = Blueprint("agent_service", __name__)

MIN_PRESIGN_MINUTES = 5
MAX_PRESIGN_MINUTES = 30


def _feature_disabled():
    return jsonify({
        "error": "Agent Service feature is not enabled",
        "code": "FEATURE_DISABLED",
    }), 403


def check_feature_enabled():
    if not current_app.config.get("FEATURE_AGENT_SERVICE", False):
        return _feature_disabled()
    return None


def _validation_error(details):
    return jsonify({
        "error": "Validation failed",
        "code": "VALIDATION_ERROR",
        "details": details,
    }), 400


def _can_view_all_requests(actor):
    return actor.role in {"superadmin", "admin", "hr_admin"}


def _can_view_request(actor, agent_request):
    return _can_view_all_requests(actor) or agent_request.requester_user_id == actor.id


def _ensure_governed_policy(action, name):
    policy = Policy.query.filter_by(action=action, is_active=True).first()
    if policy and policy.requires_approval:
        return policy

    if not policy:
        policy = Policy(
            name=name,
            description=f"Governed approval policy for {action}",
            action=action,
            required_role="viewer",
            requires_approval=True,
            approvals_required=1,
            approver_role="admin",
            is_active=True,
            created_by=None,
        )
        db.session.add(policy)
    else:
        policy.requires_approval = True
        policy.approvals_required = max(policy.approvals_required or 1, 1)
        policy.approver_role = policy.approver_role or "admin"
    db.session.commit()
    return policy


def _approved_request_for_agent(agent_request_id):
    return (
        ApprovalRequest.query
        .filter_by(target_type="agent_request", target_id=agent_request_id, status="approved")
        .order_by(ApprovalRequest.resolved_at.desc())
        .first()
    )


def _approved_policy_request(action, target_type, target_id, requester_id=None, approval_request_id=None):
    query = ApprovalRequest.query.filter_by(
        action=action,
        target_type=target_type,
        target_id=target_id,
        status="approved",
    )
    if requester_id is not None:
        query = query.filter_by(requester_id=requester_id)

    if approval_request_id:
        query = query.filter_by(id=approval_request_id)

    return query.order_by(ApprovalRequest.resolved_at.desc()).first()


def _require_policy_approval(action, actor, target_type, target_id, target_label, request_data, approval_request_id=None):
    policy = Policy.query.filter_by(action=action, is_active=True).first()
    if not policy or not policy.requires_approval:
        return None

    approved = _approved_policy_request(
        action=action,
        target_type=target_type,
        target_id=target_id,
        requester_id=actor.id,
        approval_request_id=approval_request_id,
    )
    if approved:
        return None

    from app.routes.governance import check_policy

    requires_approval, _policy, approval_request = check_policy(
        action=action,
        actor=actor,
        target_type=target_type,
        target_id=target_id,
        target_label=target_label,
        request_data=request_data,
    )
    if requires_approval and approval_request:
        return jsonify({
            "message": "Approval required before this action",
            "code": "APPROVAL_REQUIRED",
            "approval_request": approval_request.to_dict(),
        }), 202

    return None


def _load_destination(destination_type, destination_ref):
    if destination_type == "download":
        return None

    try:
        destination_id = int(destination_ref)
    except (TypeError, ValueError):
        return None

    return ExternalDestination.query.filter_by(id=destination_id, is_active=True).first()


def _validate_destination(destination_type, destination_ref, template_id):
    if destination_type not in SUPPORTED_DESTINATION_TYPES:
        return f"destination_type must be one of: {', '.join(sorted(SUPPORTED_DESTINATION_TYPES))}", None

    if destination_type == "download":
        return None, None

    destination = _load_destination(destination_type, destination_ref)
    if not destination:
        return "destination_ref must reference an active destination", None
    if destination.destination_type != destination_type:
        return "destination_type does not match selected destination", None
    if template_id not in (destination.allowed_template_ids or []):
        return "selected template is not allowed for destination", None

    return None, destination


def _validate_destination_payload(payload, partial=False):
    errors = []

    name = payload.get("name")
    destination_type = payload.get("destination_type")
    config = payload.get("config")
    allowed_template_ids = payload.get("allowed_template_ids")

    if partial and destination_type is None and isinstance(config, dict):
        errors.append("destination_type is required when updating config")

    if not partial or "name" in payload:
        if not isinstance(name, str) or not name.strip():
            errors.append("name is required")

    allowed_types = {"google_drive_folder", "google_sheet_range"}
    if not partial or "destination_type" in payload:
        if destination_type not in allowed_types:
            errors.append("destination_type must be google_drive_folder or google_sheet_range")

    if not partial or "config" in payload:
        if not isinstance(config, dict):
            errors.append("config must be an object")
        elif destination_type == "google_drive_folder":
            if not isinstance(config.get("folder_id"), str) or not config.get("folder_id").strip():
                errors.append("config.folder_id is required for google_drive_folder")
        elif destination_type == "google_sheet_range":
            if not isinstance(config.get("spreadsheet_id"), str) or not config.get("spreadsheet_id").strip():
                errors.append("config.spreadsheet_id is required for google_sheet_range")
            if not isinstance(config.get("sheet_name"), str) or not config.get("sheet_name").strip():
                errors.append("config.sheet_name is required for google_sheet_range")
            if not isinstance(config.get("a1_range"), str) or not config.get("a1_range").strip():
                errors.append("config.a1_range is required for google_sheet_range")

    if not partial or "allowed_template_ids" in payload:
        if not isinstance(allowed_template_ids, list) or not allowed_template_ids:
            errors.append("allowed_template_ids must be a non-empty array")
        else:
            invalid = [item for item in allowed_template_ids if not isinstance(item, str) or not item.strip()]
            if invalid:
                errors.append("allowed_template_ids must contain non-empty strings")

    return errors


def _ensure_agent_request_approved(agent_request):
    if not agent_request.approval_required:
        return None
    if _approved_request_for_agent(agent_request.id):
        return None
    return jsonify({"error": "Approved request not found", "code": "APPROVAL_REQUIRED"}), 409


def _requested_ttl_minutes(payload):
    value = payload.get("ttl_minutes", 10)
    try:
        value_int = int(value)
    except (TypeError, ValueError):
        raise ValueError("ttl_minutes must be an integer")

    if value_int < MIN_PRESIGN_MINUTES or value_int > MAX_PRESIGN_MINUTES:
        raise ValueError(f"ttl_minutes must be between {MIN_PRESIGN_MINUTES} and {MAX_PRESIGN_MINUTES}")
    return value_int


@agent_bp.get("/agent/templates")
@require_role("viewer")
def list_agent_templates():
    error = check_feature_enabled()
    if error:
        return error

    module_scope = request.args.get("module_scope")
    templates = list_templates(module_scope=module_scope)

    return jsonify({
        "items": templates,
        "total": len(templates),
        "supported_outputs": sorted(SUPPORTED_OUTPUT_TYPES),
        "supported_modules": sorted(SUPPORTED_MODULE_SCOPES),
        "supported_destinations": sorted(SUPPORTED_DESTINATION_TYPES),
        "permissions": AGENT_PERMISSIONS,
    })


@agent_bp.get("/external-destinations")
@require_role("viewer")
def list_external_destinations():
    error = check_feature_enabled()
    if error:
        return error

    include_inactive = request.args.get("include_inactive", "false").lower() == "true"
    query = ExternalDestination.query

    if not include_inactive or not _can_view_all_requests(request.current_user):
        query = query.filter_by(is_active=True)

    destination_type = request.args.get("destination_type")
    if destination_type:
        query = query.filter_by(destination_type=destination_type)

    items = [d.to_dict() for d in query.order_by(ExternalDestination.updated_at.desc()).all()]
    return jsonify({"items": items, "total": len(items)})


@agent_bp.post("/external-destinations")
@require_role("admin")
def create_external_destination():
    error = check_feature_enabled()
    if error:
        return error

    actor = request.current_user
    payload = request.get_json() or {}
    errors = _validate_destination_payload(payload, partial=False)
    if errors:
        return _validation_error(errors)

    destination = ExternalDestination(
        name=payload["name"].strip(),
        destination_type=payload["destination_type"],
        config=payload["config"],
        allowed_template_ids=payload["allowed_template_ids"],
        is_active=bool(payload.get("is_active", True)),
        created_by_id=actor.id,
    )
    db.session.add(destination)
    db.session.commit()

    log_action(
        action="agent.destination.created",
        actor=actor,
        target_type="external_destination",
        target_id=destination.id,
        target_label=destination.name,
        details={
            "destination_type": destination.destination_type,
            "allowed_template_ids": destination.allowed_template_ids,
        },
    )

    return jsonify({"destination": destination.to_dict()}), 201


@agent_bp.patch("/external-destinations/<int:destination_id>")
@require_role("admin")
def update_external_destination(destination_id):
    error = check_feature_enabled()
    if error:
        return error

    actor = request.current_user
    destination = ExternalDestination.query.get_or_404(destination_id)
    payload = request.get_json() or {}

    errors = _validate_destination_payload(payload, partial=True)
    if errors:
        return _validation_error(errors)

    changes = {}
    for field in ["name", "destination_type", "config", "allowed_template_ids", "is_active"]:
        if field not in payload:
            continue
        old = getattr(destination, field)
        new = payload[field]
        if field == "name" and isinstance(new, str):
            new = new.strip()
        if old != new:
            setattr(destination, field, new)
            changes[field] = {"from": old, "to": new}

    if changes:
        db.session.commit()
        log_action(
            action="agent.destination.updated",
            actor=actor,
            target_type="external_destination",
            target_id=destination.id,
            target_label=destination.name,
            details={"changes": changes},
        )

    return jsonify({"destination": destination.to_dict(), "changes": changes})


@agent_bp.get("/agent-requests")
@require_role("viewer")
def list_agent_requests():
    error = check_feature_enabled()
    if error:
        return error

    actor = request.current_user
    query = AgentRequest.query

    if not _can_view_all_requests(actor):
        query = query.filter_by(requester_user_id=actor.id)

    status = request.args.get("status")
    module_scope = request.args.get("module_scope")
    if status:
        query = query.filter_by(status=status)
    if module_scope:
        query = query.filter_by(module_scope=module_scope)

    query = query.order_by(AgentRequest.created_at.desc())
    page = request.args.get("page", 1, type=int)
    page_size = min(request.args.get("page_size", 20, type=int), 100)
    pagination = query.paginate(page=page, per_page=page_size, error_out=False)

    return jsonify({
        "items": [item.to_dict() for item in pagination.items],
        "total": pagination.total,
        "page": pagination.page,
        "page_size": pagination.per_page,
        "pages": pagination.pages,
    })


@agent_bp.get("/agent-requests/<int:request_id>")
@require_role("viewer")
def get_agent_request(request_id):
    error = check_feature_enabled()
    if error:
        return error

    actor = request.current_user
    agent_request = AgentRequest.query.get_or_404(request_id)

    if not _can_view_request(actor, agent_request):
        return jsonify({"error": "Insufficient permissions", "code": "INSUFFICIENT_PERMISSIONS"}), 403

    approvals = (
        ApprovalRequest.query
        .filter_by(target_type="agent_request", target_id=agent_request.id)
        .order_by(ApprovalRequest.created_at.desc())
        .all()
    )

    return jsonify({
        "request": agent_request.to_dict(),
        "artifacts": [artifact.to_dict() for artifact in sorted(agent_request.artifacts, key=lambda x: x.id, reverse=True)],
        "approvals": [approval.to_dict() for approval in approvals],
    })


@agent_bp.post("/agent-requests")
@require_role("viewer")
def create_agent_request():
    error = check_feature_enabled()
    if error:
        return error

    actor = request.current_user
    ok, reason = ensure_permission(actor, "agent:run")
    if not ok:
        return jsonify({"error": reason, "code": "INSUFFICIENT_PERMISSIONS"}), 403
    ok, reason = ensure_permission(actor, "agent:export")
    if not ok:
        return jsonify({"error": reason, "code": "INSUFFICIENT_PERMISSIONS"}), 403

    payload = request.get_json() or {}
    module_scope = payload.get("module_scope")
    output_type = payload.get("output_type")
    template_id = payload.get("template_id")
    filters_json = payload.get("filters_json") or {}
    destination_type = payload.get("destination_type", "download")
    destination_ref = payload.get("destination_ref")

    errors = []
    if module_scope not in SUPPORTED_MODULE_SCOPES:
        errors.append(f"module_scope must be one of: {', '.join(sorted(SUPPORTED_MODULE_SCOPES))}")
    if output_type not in SUPPORTED_OUTPUT_TYPES:
        errors.append(f"output_type must be one of: {', '.join(sorted(SUPPORTED_OUTPUT_TYPES))}")
    if not isinstance(template_id, str) or not template_id:
        errors.append("template_id is required")
    if filters_json is not None and not isinstance(filters_json, dict):
        errors.append("filters_json must be an object")

    template = get_template(template_id, module_scope=module_scope)
    if not template:
        errors.append("template_id is invalid for module_scope")

    destination, destination_error = None, None
    if not errors:
        destination_error, destination = _validate_destination(destination_type, destination_ref, template_id)
        if destination_error:
            errors.append(destination_error)

    if errors:
        return _validation_error(errors)

    if destination_type != "download":
        ok, reason = ensure_permission(actor, "agent:write_external")
        if not ok:
            return jsonify({"error": reason, "code": "INSUFFICIENT_PERMISSIONS"}), 403

    rows = query_module_rows(actor=actor, module_scope=module_scope, filters=filters_json)
    try:
        selected_fields = resolve_requested_fields(filters_json, template.allowed_fields or [])
    except ValueError as exc:
        return _validation_error([str(exc)])
    rows = enforce_template_fields(rows, template.allowed_fields or [], selected_fields=selected_fields)
    rows = apply_masking(rows, template.masking_rules or {})
    row_count = len(rows)

    threshold = int(current_app.config.get("AGENT_EXPORT_APPROVAL_ROW_THRESHOLD", APPROVAL_ROW_THRESHOLD_DEFAULT))
    approval_eval = evaluate_approval_requirements(
        template=template,
        row_count=row_count,
        destination_type=destination_type,
        row_threshold=threshold,
    )

    agent_request = AgentRequest(
        requester_user_id=actor.id,
        org_id=payload.get("org_id"),
        module_scope=module_scope,
        filters_json=filters_json,
        output_type=output_type,
        template_id=template_id,
        destination_type=destination_type,
        destination_ref=str(destination.id) if destination else None,
        status="pending",
        approval_required=approval_eval["requires_approval"],
    )
    db.session.add(agent_request)
    db.session.commit()

    log_action(
        action="agent.request.created",
        actor=actor,
        target_type="agent_request",
        target_id=agent_request.id,
        target_label=f"{module_scope}:{template_id}",
        details={
            "module_scope": module_scope,
            "template_id": template_id,
            "output_type": output_type,
            "destination_type": destination_type,
            "destination_ref": agent_request.destination_ref,
            "filters": filters_json,
            "row_count": row_count,
            "approval_evaluation": approval_eval,
        },
    )

    if approval_eval["requires_approval"]:
        from app.routes.governance import check_policy

        policy_action = "agent.write_external" if approval_eval["external_write"] else "agent.export"
        _ensure_governed_policy(
            action=policy_action,
            name="Agent External Write Approval" if policy_action == "agent.write_external" else "Agent Export Approval",
        )

        requires_approval, _policy, approval_request = check_policy(
            action=policy_action,
            actor=actor,
            target_type="agent_request",
            target_id=agent_request.id,
            target_label=f"{module_scope}:{template_id}",
            request_data={
                "agent_request_id": agent_request.id,
                "module_scope": module_scope,
                "template_id": template_id,
                "output_type": output_type,
                "destination_type": destination_type,
                "destination_ref": agent_request.destination_ref,
            },
        )

        if requires_approval and approval_request:
            agent_request.status = "pending_approval"
            db.session.commit()
            return jsonify({
                "message": "Approval required before execution",
                "code": "APPROVAL_REQUIRED",
                "request": agent_request.to_dict(),
                "approval_request": approval_request.to_dict(),
            }), 202

    result = process_agent_request(agent_request, executor=actor)
    return jsonify({
        "message": "Agent request completed",
        "request": result["request"],
        "artifact": result["artifact"],
        "publish_result": result.get("publish_result"),
    }), 201


@agent_bp.post("/agent-requests/<int:request_id>/run")
@require_role("viewer")
def run_agent_request(request_id):
    error = check_feature_enabled()
    if error:
        return error

    actor = request.current_user
    ok, reason = ensure_permission(actor, "agent:run")
    if not ok:
        return jsonify({"error": reason, "code": "INSUFFICIENT_PERMISSIONS"}), 403
    ok, reason = ensure_permission(actor, "agent:export")
    if not ok:
        return jsonify({"error": reason, "code": "INSUFFICIENT_PERMISSIONS"}), 403

    agent_request = AgentRequest.query.get_or_404(request_id)
    if not _can_view_request(actor, agent_request):
        return jsonify({"error": "Insufficient permissions", "code": "INSUFFICIENT_PERMISSIONS"}), 403

    approval_error = _ensure_agent_request_approved(agent_request)
    if approval_error:
        return approval_error

    result = process_agent_request(agent_request, executor=actor)
    return jsonify({
        "message": "Agent request executed",
        "request": result["request"],
        "artifact": result["artifact"],
        "publish_result": result.get("publish_result"),
    })


@agent_bp.post("/generated-artifacts/<int:artifact_id>/presign")
@require_role("viewer")
def presign_generated_artifact(artifact_id):
    error = check_feature_enabled()
    if error:
        return error

    actor = request.current_user
    ok, reason = ensure_permission(actor, "agent:export")
    if not ok:
        return jsonify({"error": reason, "code": "INSUFFICIENT_PERMISSIONS"}), 403

    artifact = GeneratedArtifact.query.get_or_404(artifact_id)
    agent_request = artifact.request
    if not agent_request or not _can_view_request(actor, agent_request):
        return jsonify({"error": "Insufficient permissions", "code": "INSUFFICIENT_PERMISSIONS"}), 403

    approval_error = _ensure_agent_request_approved(agent_request)
    if approval_error:
        return approval_error

    payload = request.get_json(silent=True) or {}
    try:
        ttl_minutes = _requested_ttl_minutes(payload)
    except ValueError as exc:
        return _validation_error([str(exc)])

    approval_result = _require_policy_approval(
        action="agent.export",
        actor=actor,
        target_type="generated_artifact",
        target_id=artifact.id,
        target_label=artifact.filename,
        request_data={
            "artifact_id": artifact.id,
            "agent_request_id": artifact.agent_request_id,
            "ttl_minutes": ttl_minutes,
            "purpose": "presign_download",
        },
        approval_request_id=payload.get("approval_request_id"),
    )
    if approval_result:
        return approval_result

    expires_seconds = ttl_minutes * 60
    artifact.expires_at = datetime.utcnow() + timedelta(seconds=expires_seconds)
    db.session.commit()

    presigned_url = generate_presigned_download(
        artifact.s3_bucket,
        artifact.s3_key,
        artifact.filename,
        expires_seconds,
    )
    if not presigned_url:
        presigned_url = f"/admin/generated-artifacts/{artifact.id}/download"

    log_action(
        action="agent.artifact.presign_requested",
        actor=actor,
        target_type="generated_artifact",
        target_id=artifact.id,
        target_label=artifact.filename,
        details={
            "agent_request_id": artifact.agent_request_id,
            "s3_bucket": artifact.s3_bucket,
            "s3_key": artifact.s3_key,
            "ttl_minutes": ttl_minutes,
            "classification": artifact.classification,
            "pii_flag": artifact.pii_flag,
        },
    )

    return jsonify({
        "artifact_id": artifact.id,
        "download_url": presigned_url,
        "expires_in_seconds": expires_seconds,
        "expires_at": artifact.expires_at.isoformat(),
    })


@agent_bp.get("/generated-artifacts/<int:artifact_id>/download")
@require_role("viewer")
def download_generated_artifact(artifact_id):
    error = check_feature_enabled()
    if error:
        return error

    actor = request.current_user
    artifact = GeneratedArtifact.query.get_or_404(artifact_id)
    agent_request = artifact.request

    if not agent_request or not _can_view_request(actor, agent_request):
        return jsonify({"error": "Insufficient permissions", "code": "INSUFFICIENT_PERMISSIONS"}), 403

    approval_error = _ensure_agent_request_approved(agent_request)
    if approval_error:
        return approval_error

    if artifact.expires_at and artifact.expires_at <= datetime.utcnow():
        return jsonify({"error": "Artifact link expired", "code": "LINK_EXPIRED"}), 410

    try:
        payload = read_artifact_bytes(artifact.s3_bucket, artifact.s3_key)
    except FileNotFoundError:
        return jsonify({"error": "Artifact file not found"}), 404

    log_action(
        action="agent.artifact.downloaded",
        actor=actor,
        target_type="generated_artifact",
        target_id=artifact.id,
        target_label=artifact.filename,
        details={
            "agent_request_id": artifact.agent_request_id,
            "row_count": artifact.row_count,
            "sha256": artifact.sha256,
            "classification": artifact.classification,
            "pii_flag": artifact.pii_flag,
            "storage_backend": "local" if artifact.s3_bucket == LOCAL_ARTIFACT_BUCKET else "s3",
        },
    )

    return send_file(
        io.BytesIO(payload),
        as_attachment=True,
        download_name=artifact.filename,
        mimetype=artifact.mime_type,
    )


def _publish_artifact(artifact_id, destination_type, mode="overwrite"):
    actor = request.current_user
    ok, reason = ensure_permission(actor, "agent:write_external")
    if not ok:
        return jsonify({"error": reason, "code": "INSUFFICIENT_PERMISSIONS"}), 403

    artifact = GeneratedArtifact.query.get_or_404(artifact_id)
    agent_request = artifact.request

    if not agent_request or not _can_view_request(actor, agent_request):
        return jsonify({"error": "Insufficient permissions", "code": "INSUFFICIENT_PERMISSIONS"}), 403

    approval_error = _ensure_agent_request_approved(agent_request)
    if approval_error:
        return approval_error

    payload = request.get_json(silent=True) or {}
    try:
        destination_id = int(payload.get("destination_id"))
    except (TypeError, ValueError):
        return _validation_error(["destination_id is required and must be an integer"])

    destination = ExternalDestination.query.filter_by(id=destination_id, is_active=True).first()
    if not destination:
        return _validation_error(["destination_id must reference an active destination"])
    if destination.destination_type != destination_type:
        return _validation_error([f"destination must be of type {destination_type}"])

    if agent_request.template_id not in (destination.allowed_template_ids or []):
        return _validation_error(["selected template is not allowed for destination"])

    _ensure_governed_policy("agent.write_external", "Agent External Write Approval")
    approval_result = _require_policy_approval(
        action="agent.write_external",
        actor=actor,
        target_type="generated_artifact",
        target_id=artifact.id,
        target_label=artifact.filename,
        request_data={
            "artifact_id": artifact.id,
            "agent_request_id": artifact.agent_request_id,
            "destination_id": destination.id,
            "destination_type": destination.destination_type,
            "mode": mode,
            "publish_action": "publish_artifact",
        },
        approval_request_id=payload.get("approval_request_id"),
    )
    if approval_result:
        return approval_result

    try:
        result = publish_generated_artifact(artifact, destination, actor=actor, mode=mode)
    except ValueError as exc:
        return _validation_error([str(exc)])

    return jsonify({
        "message": "Artifact published",
        "artifact": artifact.to_dict(),
        "destination": destination.to_dict(),
        "result": result,
    })


@agent_bp.post("/generated-artifacts/<int:artifact_id>/publish/drive")
@require_role("viewer")
def publish_artifact_to_drive(artifact_id):
    error = check_feature_enabled()
    if error:
        return error
    return _publish_artifact(artifact_id, "google_drive_folder")


@agent_bp.post("/generated-artifacts/<int:artifact_id>/publish/sheet")
@require_role("viewer")
def publish_artifact_to_sheet(artifact_id):
    error = check_feature_enabled()
    if error:
        return error

    payload = request.get_json(silent=True) or {}
    mode = payload.get("mode", "overwrite")
    if mode not in {"overwrite", "append"}:
        return _validation_error(["mode must be overwrite or append"])

    return _publish_artifact(artifact_id, "google_sheet_range", mode=mode)


@agent_bp.get("/agent/status")
@require_role("viewer")
def agent_status():
    error = check_feature_enabled()
    if error:
        return error

    actor = request.current_user
    can_write_external, _ = ensure_permission(actor, "agent:write_external")

    destinations = []
    if can_write_external:
        destinations = [d.to_dict() for d in ExternalDestination.query.filter_by(is_active=True).all()]

    return jsonify({
        "permissions": {
            permission: ensure_permission(actor, permission)[0] for permission in AGENT_PERMISSIONS
        },
        "approval_row_threshold": int(current_app.config.get("AGENT_EXPORT_APPROVAL_ROW_THRESHOLD", APPROVAL_ROW_THRESHOLD_DEFAULT)),
        "presign_ttl_bounds": {
            "min_minutes": MIN_PRESIGN_MINUTES,
            "max_minutes": MAX_PRESIGN_MINUTES,
            "default_minutes": 10,
        },
        "destinations": destinations,
    })
