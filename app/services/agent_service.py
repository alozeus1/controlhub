"""Worker/orchestration service for governed Agent Requests."""

from datetime import datetime

from app.extensions import db
from app.models import AgentRequest, ExternalDestination, GeneratedArtifact
from app.services.agent_templates import get_template
from app.services.agent_tools import (
    apply_masking,
    enforce_template_fields,
    generate_csv,
    generate_doc,
    generate_markdown,
    generate_xlsx,
    query_module_rows,
    resolve_requested_fields,
    sha256_hex,
    store_artifact,
)
from app.utils.audit import log_action


APPROVAL_ROW_THRESHOLD_DEFAULT = 200


def _redact_filters(filters):
    safe = {}
    for key, value in (filters or {}).items():
        key_lower = str(key).lower()
        if any(token in key_lower for token in ("secret", "password", "token", "key")):
            safe[key] = "***redacted***"
        else:
            safe[key] = value
    return safe


DAILY_EXPORT_ROW_BUDGET_DEFAULT = 5000


def rows_exported_last_24h(actor_id):
    """Rows this actor has already queued for export in the trailing 24 hours."""
    from datetime import datetime, timedelta
    from sqlalchemy import func
    from app.extensions import db
    from app.models import AgentRequest

    since = datetime.utcnow() - timedelta(hours=24)
    total = (db.session.query(func.coalesce(func.sum(AgentRequest.row_count), 0))
             .filter(AgentRequest.requester_user_id == actor_id,
                     AgentRequest.created_at >= since,
                     AgentRequest.status != "failed")
             .scalar())
    return int(total or 0)


def check_daily_export_budget(actor_id, row_count, budget):
    """
    Hard stop on cumulative export volume per actor per day.

    Approval thresholds are per-request, so on their own they let an attacker
    slice one large exfiltration into many small compliant ones. This caps the
    total. Returns (allowed, detail).
    """
    if budget <= 0:  # 0 or negative disables the cap
        return True, None

    already = rows_exported_last_24h(actor_id)
    if already + row_count > budget:
        return False, {
            "code": "EXPORT_BUDGET_EXCEEDED",
            "rows_last_24h": already,
            "requested_rows": row_count,
            "daily_budget": budget,
        }
    return True, {"rows_last_24h": already, "daily_budget": budget}


def evaluate_approval_requirements(template, row_count, destination_type, row_threshold):
    has_pii = bool(getattr(template, "pii_flag", False))
    over_threshold = row_count > row_threshold
    external_write = destination_type in {"google_drive_folder", "google_sheet_range"}

    return {
        "requires_approval": bool(has_pii or over_threshold or external_write),
        "has_pii": has_pii,
        "over_threshold": over_threshold,
        "external_write": external_write,
    }


def _select_output(rows, output_type, template_id):
    if output_type == "csv":
        return generate_csv(rows, template_id), "text/csv", "csv"
    if output_type == "xlsx":
        return (
            generate_xlsx(rows, template_id),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "xlsx",
        )
    if output_type == "docx":
        document = generate_doc(
            template_id=template_id,
            variables={
                "title": f"ControlHub Report: {template_id}",
                "generated_at": datetime.utcnow().isoformat(),
                "row_count": len(rows),
            },
            tables=[{"title": "Records", "rows": rows}],
        )
        return document, "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "docx"
    if output_type == "md":
        return generate_markdown(rows, template_id), "text/markdown", "md"
    raise ValueError("Unsupported output_type")


def _filename(request_id, module_scope, template_id, extension):
    now_str = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    return f"agent_{module_scope}_{template_id}_{request_id}_{now_str}.{extension}"


def _load_destination(destination_type, destination_ref):
    if destination_type == "download":
        return None

    try:
        destination_id = int(destination_ref)
    except (TypeError, ValueError) as exc:
        raise ValueError("destination_ref must reference a valid destination id") from exc

    destination = ExternalDestination.query.filter_by(id=destination_id, is_active=True).first()
    if not destination:
        raise ValueError("Destination not found or inactive")
    if destination.destination_type != destination_type:
        raise ValueError("destination_type does not match destination_ref")
    return destination


def publish_generated_artifact(artifact, destination, actor=None, mode="overwrite"):
    """
    Publish an already-generated artifact to an allow-listed destination.

    Thin wrapper over the egress chokepoint — every validation, the deployment
    allowlist, the TOCTOU fingerprint check, and the audit event all live in
    app/services/agent_egress.py so there is exactly one way data leaves.
    """
    from app.services.agent_egress import deliver

    return deliver(artifact, destination, actor=actor, mode=mode)


def process_agent_request(agent_request, executor=None):
    """Execute a queued/approved request and generate artifact output."""
    if not isinstance(agent_request, AgentRequest):
        raise ValueError("agent_request must be an AgentRequest model")

    template = get_template(agent_request.template_id, module_scope=agent_request.module_scope)
    if not template:
        raise ValueError("Unknown template_id for module_scope")

    destination = _load_destination(agent_request.destination_type, agent_request.destination_ref)
    if destination and agent_request.template_id not in (destination.allowed_template_ids or []):
        raise ValueError("template_id is not allowed for selected destination")

    requester = agent_request.requester
    actor_for_logs = executor or requester

    agent_request.status = "processing"
    if executor:
        agent_request.approved_by = executor.id
    db.session.commit()

    try:
        filters = agent_request.filters_json or {}
        rows = query_module_rows(
            actor=requester,
            module_scope=agent_request.module_scope,
            filters=filters,
        )

        selected_fields = resolve_requested_fields(filters, template.allowed_fields or [])
        rows = enforce_template_fields(rows, template.allowed_fields or [], selected_fields=selected_fields)
        rows = apply_masking(rows, template.masking_rules or {})

        # Re-check the projection immediately before it becomes bytes. Field
        # scope is the line between an approved report and a data leak; it
        # should not rest on one upstream call staying correct forever.
        from app.services.agent_egress import assert_scope_integrity
        assert_scope_integrity(rows, template)

        row_count = len(rows)

        payload, mime_type, extension = _select_output(rows, agent_request.output_type, agent_request.template_id)
        artifact_hash = sha256_hex(payload)

        artifact = GeneratedArtifact(
            agent_request_id=agent_request.id,
            filename=_filename(agent_request.id, agent_request.module_scope, agent_request.template_id, extension),
            mime_type=mime_type,
            row_count=row_count,
            sha256=artifact_hash,
            s3_bucket="pending",
            s3_key="pending",
            classification=template.classification,
            pii_flag=bool(template.pii_flag),
            expires_at=datetime.utcnow(),
        )
        db.session.add(artifact)
        db.session.flush()

        storage_meta = store_artifact(
            file_bytes=payload,
            artifact_id=artifact.id,
            filename=artifact.filename,
            mime_type=artifact.mime_type,
        )
        artifact.s3_bucket = storage_meta["s3_bucket"]
        artifact.s3_key = storage_meta["s3_key"]
        artifact.expires_at = storage_meta["expires_at"]

        publish_result = None
        if destination:
            mode = filters.get("publish_mode", "overwrite")
            publish_result = publish_generated_artifact(artifact, destination, actor=actor_for_logs, mode=mode)

        agent_request.status = "completed"
        agent_request.completed_at = datetime.utcnow()
        db.session.commit()

        log_action(
            action="agent.request.completed",
            actor=actor_for_logs,
            target_type="agent_request",
            target_id=agent_request.id,
            target_label=f"{agent_request.module_scope}:{agent_request.template_id}",
            details={
                "module_scope": agent_request.module_scope,
                "template_id": agent_request.template_id,
                "output_type": agent_request.output_type,
                "destination_type": agent_request.destination_type,
                "destination_ref": agent_request.destination_ref,
                "filters": _redact_filters(filters),
                "row_count": row_count,
                "artifact_id": artifact.id,
                "artifact_hash": artifact.sha256,
                "classification": artifact.classification,
                "pii_flag": artifact.pii_flag,
                "publish_result": publish_result,
            },
        )

        return {
            "request": agent_request.to_dict(),
            "artifact": artifact.to_dict(),
            "publish_result": publish_result,
        }

    except Exception as exc:
        agent_request.status = "failed"
        agent_request.completed_at = datetime.utcnow()
        db.session.commit()

        log_action(
            action="agent.request.failed",
            actor=actor_for_logs,
            target_type="agent_request",
            target_id=agent_request.id,
            target_label=f"{agent_request.module_scope}:{agent_request.template_id}",
            details={
                "module_scope": agent_request.module_scope,
                "template_id": agent_request.template_id,
                "output_type": agent_request.output_type,
                "destination_type": agent_request.destination_type,
                "filters": _redact_filters(agent_request.filters_json or {}),
                "error": str(exc),
            },
        )
        raise
