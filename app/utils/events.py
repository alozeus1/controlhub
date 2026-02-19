"""
Event Hook Utilities

Provides functions to emit events that can trigger alerts.
Integrates with the notification system when enabled.
"""
import logging
from typing import Optional, Dict, Any

from flask import current_app

logger = logging.getLogger(__name__)


def emit_event(
    event_type: str,
    title: str,
    payload: Optional[Dict[str, Any]] = None,
    severity: Optional[str] = None,
) -> None:
    """
    Emit an event that may trigger alerts if notification feature is enabled.
    
    This function is safe to call even when notifications are disabled.
    
    Args:
        event_type: Type of event (e.g., 'job.failed', 'user.disabled')
        title: Human-readable title for the alert
        payload: Additional event data
        severity: Override severity (otherwise uses rule's default)
    """
    # Check if notifications feature is enabled
    if not current_app.config.get("FEATURE_NOTIFICATIONS", False):
        logger.debug(f"Notifications disabled, skipping event: {event_type}")
        return

    try:
        from app.services.notifications import AlertTriggerService
        AlertTriggerService.trigger_alert(
            event_type=event_type,
            title=title,
            payload=payload,
            severity_override=severity,
        )
    except Exception as e:
        # Never let alert failures break the main flow
        logger.error(f"Failed to trigger alert for {event_type}: {e}")


# =============================================================================
# CONVENIENCE FUNCTIONS FOR COMMON EVENTS
# =============================================================================

def emit_job_failed(job, error_message: str = None):
    """Emit event when a job fails."""
    emit_event(
        event_type="job.failed",
        title=f"Job failed: {job.name}",
        payload={
            "job_id": job.id,
            "job_name": job.name,
            "job_type": job.type,
            "error": error_message,
            "message": f"Job '{job.name}' (ID: {job.id}) has failed.",
        },
        severity="high",
    )


def emit_job_completed(job):
    """Emit event when a job completes successfully."""
    emit_event(
        event_type="job.completed",
        title=f"Job completed: {job.name}",
        payload={
            "job_id": job.id,
            "job_name": job.name,
            "job_type": job.type,
            "message": f"Job '{job.name}' (ID: {job.id}) has completed successfully.",
        },
        severity="low",
    )


def emit_user_created(user, actor):
    """Emit event when a user is created."""
    emit_event(
        event_type="user.created",
        title=f"User created: {user.email}",
        payload={
            "user_id": user.id,
            "user_email": user.email,
            "role": user.role,
            "created_by": actor.email if actor else None,
            "message": f"User '{user.email}' was created with role '{user.role}'.",
        },
    )


def emit_user_disabled(user, actor):
    """Emit event when a user is disabled."""
    emit_event(
        event_type="user.disabled",
        title=f"User disabled: {user.email}",
        payload={
            "user_id": user.id,
            "user_email": user.email,
            "disabled_by": actor.email if actor else None,
            "message": f"User '{user.email}' was disabled by '{actor.email if actor else 'system'}'.",
        },
        severity="medium",
    )


def emit_user_role_changed(user, actor, old_role: str, new_role: str):
    """Emit event when a user's role changes."""
    emit_event(
        event_type="user.role_changed",
        title=f"Role changed: {user.email}",
        payload={
            "user_id": user.id,
            "user_email": user.email,
            "old_role": old_role,
            "new_role": new_role,
            "changed_by": actor.email if actor else None,
            "message": f"User '{user.email}' role changed from '{old_role}' to '{new_role}'.",
        },
        severity="medium" if new_role == "admin" else "low",
    )


def emit_upload_created(upload, actor):
    """Emit event when a file is uploaded."""
    emit_event(
        event_type="upload.created",
        title=f"File uploaded: {upload.original_filename}",
        payload={
            "upload_id": upload.id,
            "filename": upload.original_filename,
            "content_type": upload.content_type,
            "size_bytes": upload.size_bytes,
            "uploaded_by": actor.email if actor else None,
            "message": f"File '{upload.original_filename}' was uploaded.",
        },
    )


def emit_upload_deleted(upload, actor):
    """Emit event when a file is deleted."""
    emit_event(
        event_type="upload.deleted",
        title=f"File deleted: {upload.original_filename}",
        payload={
            "upload_id": upload.id,
            "filename": upload.original_filename,
            "deleted_by": actor.email if actor else None,
            "message": f"File '{upload.original_filename}' was deleted.",
        },
    )


def emit_approval_requested(approval_request, actor):
    """Emit event when an approval is requested."""
    emit_event(
        event_type="approval.requested",
        title=f"Approval requested: {approval_request.action}",
        payload={
            "request_id": approval_request.id,
            "action": approval_request.action,
            "target_type": approval_request.target_type,
            "target_id": approval_request.target_id,
            "target_label": approval_request.target_label,
            "requested_by": actor.email if actor else None,
            "message": f"Approval requested for action '{approval_request.action}' on '{approval_request.target_label}'.",
        },
    )


def emit_approval_approved(approval_request, approver):
    """Emit event when an approval is granted."""
    emit_event(
        event_type="approval.approved",
        title=f"Approval granted: {approval_request.action}",
        payload={
            "request_id": approval_request.id,
            "action": approval_request.action,
            "target_label": approval_request.target_label,
            "approved_by": approver.email if approver else None,
            "message": f"Approval granted for '{approval_request.action}' on '{approval_request.target_label}'.",
        },
    )


def emit_approval_rejected(approval_request, approver, reason: str = None):
    """Emit event when an approval is rejected."""
    emit_event(
        event_type="approval.rejected",
        title=f"Approval rejected: {approval_request.action}",
        payload={
            "request_id": approval_request.id,
            "action": approval_request.action,
            "target_label": approval_request.target_label,
            "rejected_by": approver.email if approver else None,
            "reason": reason,
            "message": f"Approval rejected for '{approval_request.action}' on '{approval_request.target_label}'.",
        },
    )


def emit_service_account_created(service_account, actor):
    """Emit event when a service account is created."""
    emit_event(
        event_type="service_account.created",
        title=f"Service account created: {service_account.name}",
        payload={
            "service_account_id": service_account.id,
            "name": service_account.name,
            "created_by": actor.email if actor else None,
            "message": f"Service account '{service_account.name}' was created.",
        },
    )


def emit_api_key_created(api_key, actor):
    """Emit event when an API key is created."""
    emit_event(
        event_type="api_key.created",
        title=f"API key created: {api_key.name}",
        payload={
            "api_key_id": api_key.id,
            "key_name": api_key.name,
            "service_account_id": api_key.service_account_id,
            "service_account_name": api_key.service_account.name if api_key.service_account else None,
            "created_by": actor.email if actor else None,
            "message": f"API key '{api_key.name}' was created for service account '{api_key.service_account.name if api_key.service_account else 'unknown'}'.",
        },
    )


def emit_api_key_revoked(api_key, actor):
    """Emit event when an API key is revoked."""
    emit_event(
        event_type="api_key.revoked",
        title=f"API key revoked: {api_key.name}",
        payload={
            "api_key_id": api_key.id,
            "key_name": api_key.name,
            "service_account_name": api_key.service_account.name if api_key.service_account else None,
            "revoked_by": actor.email if actor else None,
            "message": f"API key '{api_key.name}' was revoked.",
        },
        severity="medium",
    )


def emit_policy_violated(policy, actor, target_label: str, details: dict = None):
    """Emit event when a policy violation occurs."""
    emit_event(
        event_type="policy.violated",
        title=f"Policy violation: {policy.name}",
        payload={
            "policy_id": policy.id,
            "policy_name": policy.name,
            "action": policy.action,
            "target_label": target_label,
            "actor_email": actor.email if actor else None,
            "details": details,
            "message": f"Policy '{policy.name}' was violated by '{actor.email if actor else 'unknown'}' on '{target_label}'.",
        },
        severity="high",
    )
