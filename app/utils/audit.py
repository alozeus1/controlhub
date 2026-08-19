"""
Audit logging utilities.

Provides helper functions to log actions to the audit_log table.
"""
from flask import request
from app.extensions import db
from app.models import AuditLog, User


def get_client_ip():
    """
    Client IP for audit attribution.

    Deliberately reads only `remote_addr`, never X-Forwarded-For directly: the
    header is set by anyone who can reach the app, so parsing it here would let
    an attacker forge the source IP in the very record you would investigate
    with. ProxyFix (see app/__init__.py) rewrites remote_addr from the number of
    proxy hops we actually trust, which is the safe way to get the real client.
    """
    try:
        return request.remote_addr
    except RuntimeError:
        return "127.0.0.1"


def get_user_agent():
    """Get user agent string, truncated to 255 chars."""
    try:
        ua = request.headers.get("User-Agent", "")
        return ua[:255] if ua else None
    except RuntimeError:
        return None


def log_action(
    action: str,
    actor: User = None,
    target_type: str = None,
    target_id: int = None,
    target_label: str = None,
    details: dict = None,
):
    """
    Log an action to the audit log.

    Args:
        action: Action code (e.g., 'user.created', 'user.login')
        actor: User performing the action (None for anonymous actions)
        target_type: Type of entity affected (e.g., 'user', 'upload')
        target_id: ID of affected entity
        target_label: Human-readable label (e.g., email address)
        details: Additional context as dict
    """
    # Attribute to a service account when an API key is acting (no human user).
    actor_id = actor.id if actor else None
    actor_email = actor.email if actor else None
    if actor is None:
        try:
            from flask import g
            sa = getattr(g, "service_account", None)
            key = getattr(g, "api_key", None)
            if sa is not None:
                prefix = getattr(key, "key_prefix", "?")
                actor_email = f"service-account:{sa.name}#{prefix}"
        except Exception:
            pass

    audit_entry = AuditLog(
        actor_id=actor_id,
        actor_email=actor_email,
        action=action,
        target_type=target_type,
        target_id=target_id,
        target_label=target_label,
        details=details,
        ip_address=get_client_ip(),
        user_agent=get_user_agent(),
    )

    # Chain this row to the previous one so a later deletion or edit is
    # detectable. created_at is part of the digest, so set it before sealing
    # rather than letting the column default fill it in after.
    from datetime import datetime
    from app.services.audit_chain import seal
    if audit_entry.created_at is None:
        audit_entry.created_at = datetime.utcnow()
    seal(audit_entry)

    db.session.add(audit_entry)
    db.session.commit()

    return audit_entry


def log_user_action(action: str, actor: User, target_user: User, details: dict = None):
    """
    Convenience function for logging user-related actions.

    Args:
        action: Action code (e.g., 'user.created', 'user.role_changed')
        actor: User performing the action
        target_user: User being affected
        details: Additional context
    """
    return log_action(
        action=action,
        actor=actor,
        target_type="user",
        target_id=target_user.id,
        target_label=target_user.email,
        details=details,
    )


def log_login(user: User, success: bool = True):
    """Log a login attempt."""
    if success:
        return log_action(
            action="user.login",
            actor=user,
            target_type="user",
            target_id=user.id,
            target_label=user.email,
        )
    else:
        # For failed logins, we don't have a user object
        return log_action(
            action="user.login_failed",
            actor=None,
            target_type="user",
            target_label=user.email if isinstance(user, User) else user,
            details={"email": user.email if isinstance(user, User) else user},
        )


def log_logout(user: User):
    """Log a logout action."""
    return log_action(
        action="user.logout",
        actor=user,
        target_type="user",
        target_id=user.id,
        target_label=user.email,
    )


def log_user_created(actor: User, new_user: User):
    """Log user creation."""
    return log_user_action(
        action="user.created",
        actor=actor,
        target_user=new_user,
        details={"role": new_user.role},
    )


def log_user_updated(actor: User, target_user: User, changes: dict):
    """Log user update."""
    return log_user_action(
        action="user.updated",
        actor=actor,
        target_user=target_user,
        details={"changes": changes},
    )


def log_role_changed(actor: User, target_user: User, old_role: str, new_role: str):
    """Log role change."""
    return log_user_action(
        action="user.role_changed",
        actor=actor,
        target_user=target_user,
        details={"from": old_role, "to": new_role},
    )


def log_user_disabled(actor: User, target_user: User):
    """Log user deactivation."""
    return log_user_action(
        action="user.disabled",
        actor=actor,
        target_user=target_user,
    )


def log_user_enabled(actor: User, target_user: User):
    """Log user reactivation."""
    return log_user_action(
        action="user.enabled",
        actor=actor,
        target_user=target_user,
    )


def log_password_changed(actor: User, target_user: User = None):
    """Log password change. If target_user is None, user changed their own password."""
    target = target_user or actor
    return log_user_action(
        action="user.password_changed",
        actor=actor,
        target_user=target,
        details={"self_service": target_user is None},
    )


# =============================================================================
# UPLOAD AUDIT FUNCTIONS
# =============================================================================

def log_upload_action(action: str, actor: User, upload, details: dict = None):
    """
    Convenience function for logging upload-related actions.

    Args:
        action: Action code (e.g., 'upload.created', 'upload.deleted')
        actor: User performing the action
        upload: FileUpload object
        details: Additional context
    """
    return log_action(
        action=action,
        actor=actor,
        target_type="upload",
        target_id=upload.id,
        target_label=upload.original_filename,
        details=details,
    )


def log_upload_created(actor: User, upload):
    """Log file upload."""
    return log_upload_action(
        action="upload.created",
        actor=actor,
        upload=upload,
        details={
            "filename": upload.original_filename,
            "content_type": upload.content_type,
            "size_bytes": upload.size_bytes,
            "s3_key": upload.s3_key,
        },
    )


def log_upload_downloaded(actor: User, upload):
    """Log file download (presigned URL generation)."""
    return log_upload_action(
        action="upload.downloaded",
        actor=actor,
        upload=upload,
        details={
            "filename": upload.original_filename,
        },
    )


def log_upload_deleted(actor: User, upload):
    """Log file deletion."""
    return log_upload_action(
        action="upload.deleted",
        actor=actor,
        upload=upload,
        details={
            "filename": upload.original_filename,
            "s3_key": upload.s3_key,
        },
    )
