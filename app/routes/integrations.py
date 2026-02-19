"""
Integration Routes

Endpoints for managing webhook integrations and audit log exports.
Feature-flagged: FEATURE_INTEGRATIONS
"""
from flask import Blueprint, jsonify, request, current_app, Response

from app.utils.rbac import require_role
from app.services.integrations import (
    IntegrationService,
    AuditExportService,
    INTEGRATION_TYPES,
    INTEGRATION_EVENTS,
    EXPORT_FORMATS,
    DESTINATION_TYPES,
)

integrations_bp = Blueprint("integrations", __name__)


def check_feature_enabled():
    """Check if integrations feature is enabled."""
    if not current_app.config.get("FEATURE_INTEGRATIONS", False):
        return jsonify({
            "error": "Integrations feature is not enabled",
            "code": "FEATURE_DISABLED"
        }), 403
    return None


# =============================================================================
# INTEGRATION ENDPOINTS
# =============================================================================

@integrations_bp.get("/integrations")
@require_role("admin")
def list_integrations():
    """List all integrations."""
    error = check_feature_enabled()
    if error:
        return error

    page = request.args.get("page", 1, type=int)
    page_size = min(request.args.get("page_size", 20, type=int), 100)
    integration_type = request.args.get("type")
    is_enabled = request.args.get("is_enabled")

    is_enabled_bool = None
    if is_enabled is not None:
        is_enabled_bool = is_enabled.lower() == "true"

    result = IntegrationService.list_integrations(
        page=page,
        page_size=page_size,
        integration_type=integration_type,
        is_enabled=is_enabled_bool,
    )
    return jsonify(result)


@integrations_bp.get("/integrations/<int:integration_id>")
@require_role("admin")
def get_integration(integration_id):
    """Get a single integration."""
    error = check_feature_enabled()
    if error:
        return error

    integration = IntegrationService.get_integration(integration_id)
    if not integration:
        return jsonify({"error": "Integration not found"}), 404

    return jsonify(integration.to_dict())


@integrations_bp.post("/integrations")
@require_role("admin")
def create_integration():
    """Create a new integration."""
    error = check_feature_enabled()
    if error:
        return error

    actor = request.current_user
    data = request.get_json()

    integration_type = data.get("type", "").strip()
    name = data.get("name", "").strip()
    config = data.get("config", {})

    if not integration_type:
        return jsonify({"error": "Integration type is required"}), 400
    if not name:
        return jsonify({"error": "Integration name is required"}), 400
    if not config:
        return jsonify({"error": "Integration config is required"}), 400

    try:
        integration = IntegrationService.create_integration(
            integration_type=integration_type,
            name=name,
            config=config,
            actor=actor,
            description=data.get("description"),
            events=data.get("events"),
        )
        return jsonify({
            "message": "Integration created",
            "integration": integration.to_dict(),
        }), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@integrations_bp.patch("/integrations/<int:integration_id>")
@require_role("admin")
def update_integration(integration_id):
    """Update an integration."""
    error = check_feature_enabled()
    if error:
        return error

    integration = IntegrationService.get_integration(integration_id)
    if not integration:
        return jsonify({"error": "Integration not found"}), 404

    actor = request.current_user
    data = request.get_json()

    try:
        integration = IntegrationService.update_integration(
            integration=integration,
            actor=actor,
            name=data.get("name"),
            description=data.get("description"),
            config=data.get("config"),
            events=data.get("events"),
            is_enabled=data.get("is_enabled"),
        )
        return jsonify({
            "message": "Integration updated",
            "integration": integration.to_dict(),
        })
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@integrations_bp.delete("/integrations/<int:integration_id>")
@require_role("admin")
def delete_integration(integration_id):
    """Delete an integration."""
    error = check_feature_enabled()
    if error:
        return error

    integration = IntegrationService.get_integration(integration_id)
    if not integration:
        return jsonify({"error": "Integration not found"}), 404

    actor = request.current_user
    IntegrationService.delete_integration(integration, actor)

    return jsonify({"message": "Integration deleted"})


@integrations_bp.post("/integrations/<int:integration_id>/test")
@require_role("admin")
def test_integration(integration_id):
    """Send a test event to verify integration configuration."""
    error = check_feature_enabled()
    if error:
        return error

    integration = IntegrationService.get_integration(integration_id)
    if not integration:
        return jsonify({"error": "Integration not found"}), 404

    result = IntegrationService.test_integration(integration)

    if result.get("success"):
        return jsonify({"message": "Test event sent", "details": result})
    else:
        return jsonify({"error": "Test failed", "details": result}), 400


@integrations_bp.get("/integrations/<int:integration_id>/logs")
@require_role("admin")
def get_integration_logs(integration_id):
    """Get delivery logs for an integration."""
    error = check_feature_enabled()
    if error:
        return error

    integration = IntegrationService.get_integration(integration_id)
    if not integration:
        return jsonify({"error": "Integration not found"}), 404

    page = request.args.get("page", 1, type=int)
    page_size = min(request.args.get("page_size", 50, type=int), 100)
    status = request.args.get("status")

    result = IntegrationService.get_logs(
        integration_id=integration_id,
        page=page,
        page_size=page_size,
        status=status,
    )
    return jsonify(result)


# =============================================================================
# AUDIT EXPORT ENDPOINTS
# =============================================================================

@integrations_bp.get("/audit-exports")
@require_role("admin")
def list_audit_exports():
    """List audit export jobs."""
    error = check_feature_enabled()
    if error:
        return error

    page = request.args.get("page", 1, type=int)
    page_size = min(request.args.get("page_size", 20, type=int), 100)

    result = AuditExportService.list_export_jobs(page=page, page_size=page_size)
    return jsonify(result)


@integrations_bp.get("/audit-exports/<int:job_id>")
@require_role("admin")
def get_audit_export(job_id):
    """Get an audit export job."""
    error = check_feature_enabled()
    if error:
        return error

    job = AuditExportService.get_export_job(job_id)
    if not job:
        return jsonify({"error": "Export job not found"}), 404

    return jsonify(job.to_dict())


@integrations_bp.post("/audit-exports")
@require_role("admin")
def create_audit_export():
    """Create an audit export job."""
    error = check_feature_enabled()
    if error:
        return error

    actor = request.current_user
    data = request.get_json()

    name = data.get("name", "").strip()
    export_format = data.get("format", "").strip()
    destination_type = data.get("destination_type", "download").strip()

    if not name:
        return jsonify({"error": "Export name is required"}), 400
    if not export_format:
        return jsonify({"error": "Export format is required"}), 400

    try:
        job = AuditExportService.create_export_job(
            name=name,
            export_format=export_format,
            destination_type=destination_type,
            actor=actor,
            destination_config=data.get("destination_config"),
            filters=data.get("filters"),
            schedule=data.get("schedule"),
        )
        return jsonify({
            "message": "Export job created",
            "job": job.to_dict(),
        }), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@integrations_bp.post("/audit-exports/<int:job_id>/run")
@require_role("admin")
def run_audit_export(job_id):
    """Run an audit export job and download the result."""
    error = check_feature_enabled()
    if error:
        return error

    job = AuditExportService.get_export_job(job_id)
    if not job:
        return jsonify({"error": "Export job not found"}), 404

    actor = request.current_user

    try:
        result = AuditExportService.run_export(job, actor)
        
        response = Response(
            result["data"],
            mimetype=result["content_type"],
        )
        response.headers["Content-Disposition"] = f"attachment; filename={result['filename']}"
        response.headers["X-Record-Count"] = str(result["record_count"])
        return response
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@integrations_bp.delete("/audit-exports/<int:job_id>")
@require_role("admin")
def delete_audit_export(job_id):
    """Delete an audit export job."""
    error = check_feature_enabled()
    if error:
        return error

    job = AuditExportService.get_export_job(job_id)
    if not job:
        return jsonify({"error": "Export job not found"}), 404

    actor = request.current_user
    AuditExportService.delete_export_job(job, actor)

    return jsonify({"message": "Export job deleted"})


@integrations_bp.post("/audit-exports/now")
@require_role("admin")
def export_audit_now():
    """Run an immediate one-time audit export."""
    error = check_feature_enabled()
    if error:
        return error

    actor = request.current_user
    data = request.get_json()

    export_format = data.get("format", "csv").strip()
    filters = data.get("filters")

    try:
        result = AuditExportService.export_now(
            export_format=export_format,
            filters=filters,
            actor=actor,
        )

        response = Response(
            result["data"],
            mimetype=result["content_type"],
        )
        response.headers["Content-Disposition"] = f"attachment; filename={result['filename']}"
        response.headers["X-Record-Count"] = str(result["record_count"])
        return response
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# =============================================================================
# METADATA ENDPOINTS
# =============================================================================

@integrations_bp.get("/integrations/metadata")
@require_role("admin")
def get_metadata():
    """Get integration system metadata."""
    error = check_feature_enabled()
    if error:
        return error

    return jsonify({
        "integration_types": INTEGRATION_TYPES,
        "events": INTEGRATION_EVENTS,
        "export_formats": EXPORT_FORMATS,
        "destination_types": DESTINATION_TYPES,
    })


@integrations_bp.get("/integrations/status")
@require_role("admin")
def get_status():
    """Get integration system status."""
    error = check_feature_enabled()
    if error:
        return error

    from app.models import Integration, IntegrationLog, AuditExportJob

    total_integrations = Integration.query.count()
    enabled_integrations = Integration.query.filter_by(is_enabled=True).count()
    failed_integrations = Integration.query.filter(Integration.failure_count > 0).count()
    total_exports = AuditExportJob.query.count()

    return jsonify({
        "integrations": {
            "total": total_integrations,
            "enabled": enabled_integrations,
            "with_failures": failed_integrations,
        },
        "export_jobs": {
            "total": total_exports,
        },
    })
