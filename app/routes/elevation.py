"""
Just-in-time privilege elevation endpoints.

Flow: a user who is *eligible* for a permission (by role) activates it here with
a reason and a fresh second factor. The grant is short-lived, bound to the
requesting session, and audited on creation, use, and revocation.

See app/services/privilege.py for the model and rationale.
"""
from flask import Blueprint, request, jsonify

from app.extensions import db, limiter
from app.models import PrivilegeGrant
from app.permissions import has_permission, require_permission
from app.services import privilege
from app.utils.audit import log_action
from app.utils.rbac import require_active_user

elevation_bp = Blueprint("elevation", __name__)


@elevation_bp.get("/elevation/config")
@require_active_user
def elevation_config():
    """What is gated, for how long, and what the caller is eligible to request."""
    actor = request.current_user
    gated = sorted(privilege.elevated_permissions())
    return jsonify({
        "enabled": bool(gated),
        "ttl_minutes": privilege.ttl_minutes(),
        "elevated_permissions": gated,
        "dual_approval_permissions": sorted(privilege.dual_approval_permissions()),
        "eligible": [key for key in gated if has_permission(actor, key)],
    })


@elevation_bp.get("/elevation/active")
@require_active_user
def list_active_grants():
    """The caller's own live grants."""
    from datetime import datetime

    grants = (PrivilegeGrant.query
              .filter(PrivilegeGrant.user_id == request.current_user.id,
                      PrivilegeGrant.revoked_at.is_(None),
                      PrivilegeGrant.expires_at > datetime.utcnow())
              .order_by(PrivilegeGrant.expires_at.desc())
              .all())
    return jsonify([g.to_dict() for g in grants])


@elevation_bp.post("/elevation/request")
@limiter.limit("10 per minute")
@require_active_user
def request_elevation():
    """
    Activate a permission the caller is eligible for.

    Requires a reason and fresh re-authentication. Rate-limited because this is
    the one endpoint where an attacker with a stolen session can brute-force a
    second factor.
    """
    actor = request.current_user
    data = request.get_json() or {}
    permission_key = (data.get("permission_key") or "").strip()
    reason = (data.get("reason") or "").strip()

    if not permission_key:
        return jsonify({"error": "permission_key is required",
                        "code": "VALIDATION_ERROR"}), 400
    if len(reason) < 10:
        return jsonify({
            "error": "A reason of at least 10 characters is required.",
            "code": "REASON_REQUIRED",
        }), 400

    if not privilege.elevation_required(permission_key):
        return jsonify({
            "error": f"'{permission_key}' does not require elevation.",
            "code": "ELEVATION_NOT_APPLICABLE",
        }), 400

    # Eligibility first: elevation activates a permission, it never grants one.
    if not has_permission(actor, permission_key):
        log_action(action="privilege.denied", actor=actor,
                   target_type="privilege_grant", target_label=permission_key,
                   details={"reason": "not_eligible"})
        return jsonify({
            "error": f"Your role does not include '{permission_key}'.",
            "code": "INSUFFICIENT_PERMISSIONS",
        }), 403

    ok, err = privilege.verify_reauth(
        actor, mfa_code=data.get("mfa_code"), password=data.get("password"),  # secret-scan:allow - test fixture / parameter name, not a credential
    )
    if not ok:
        log_action(action="privilege.reauth_failed", actor=actor,
                   target_type="privilege_grant", target_label=permission_key,
                   details={"code": err})
        status = 503 if err == "MFA_UNAVAILABLE" else 401
        return jsonify({"error": _reauth_message(err), "code": err}), status

    if privilege.requires_second_approver(permission_key):
        return _open_dual_approval(actor, permission_key, reason)

    grant = privilege.grant_elevation(
        actor, permission_key, reason,
        session_family=privilege.current_session_family(),
    )
    return jsonify(grant.to_dict()), 201


@elevation_bp.post("/elevation/<int:grant_id>/revoke")
@require_active_user
def revoke_own_grant(grant_id):
    """Hand a grant back before it expires."""
    actor = request.current_user
    grant = PrivilegeGrant.query.get(grant_id)
    if not grant or grant.user_id != actor.id:
        return jsonify({"error": "Grant not found", "code": "NOT_FOUND"}), 404
    privilege.revoke_grant(grant, "revoked_by_user", actor=actor)
    return jsonify(grant.to_dict())


@elevation_bp.get("/elevation/grants")
@require_permission("view_audit_logs")
def list_all_grants():
    """Oversight view: who elevated, why, when, and how much they used it."""
    query = PrivilegeGrant.query
    user_id = request.args.get("user_id", type=int)
    if user_id:
        query = query.filter(PrivilegeGrant.user_id == user_id)
    if request.args.get("active") == "true":
        from datetime import datetime
        query = query.filter(PrivilegeGrant.revoked_at.is_(None),
                             PrivilegeGrant.expires_at > datetime.utcnow())
    grants = query.order_by(PrivilegeGrant.granted_at.desc()).limit(200).all()
    return jsonify([g.to_dict() for g in grants])


@elevation_bp.post("/elevation/<int:grant_id>/approve")
@require_active_user
def approve_grant(grant_id):
    """
    Second-human approval for dual-approval permissions.

    The approver must hold the same permission and must not be the requester —
    a two-person rule one person can satisfy is not one.
    """
    approver = request.current_user
    grant = PrivilegeGrant.query.get(grant_id)
    if not grant:
        return jsonify({"error": "Grant not found", "code": "NOT_FOUND"}), 404
    if grant.user_id == approver.id:
        return jsonify({"error": "You cannot approve your own elevation request.",
                        "code": "SELF_APPROVAL_FORBIDDEN"}), 403
    if not has_permission(approver, grant.permission_key):
        return jsonify({
            "error": f"Approvers must hold '{grant.permission_key}'.",
            "code": "INSUFFICIENT_PERMISSIONS",
        }), 403
    if grant.approved_by_id is not None:
        return jsonify({"error": "Already approved", "code": "ALREADY_APPROVED"}), 409

    from datetime import datetime, timedelta
    grant.approved_by_id = approver.id
    # The clock starts when the grant becomes usable, not when it was requested.
    grant.expires_at = datetime.utcnow() + timedelta(minutes=privilege.ttl_minutes())
    db.session.commit()

    log_action(action="privilege.approved", actor=approver,
               target_type="privilege_grant", target_id=grant.id,
               target_label=grant.permission_key,
               details={"requester": grant.user.email if grant.user else None})
    return jsonify(grant.to_dict())


# ─── helpers ──────────────────────────────────────────────────────────────────

def _open_dual_approval(actor, permission_key, reason):
    """
    Create a grant that is inert until a second human approves it.

    Modeled as an already-expired row so it cannot be used in the window before
    approval — `active_grant` filters on expires_at, so there is no state where
    the pending grant is briefly live.
    """
    from datetime import datetime
    from app.models import PrivilegeGrant

    pending = PrivilegeGrant(
        user_id=actor.id,
        permission_key=permission_key,
        reason=reason,
        session_family=privilege.current_session_family(),
        granted_at=datetime.utcnow(),
        expires_at=datetime.utcnow(),   # inert until approve() extends it
        ip_address=request.remote_addr,
    )
    db.session.add(pending)
    db.session.commit()

    log_action(action="privilege.approval_requested", actor=actor,
               target_type="privilege_grant", target_id=pending.id,
               target_label=permission_key, details={"reason": reason})

    body = pending.to_dict()
    body["message"] = ("A second approver holding this permission must approve "
                       "before it becomes active.")
    return jsonify(body), 202


def _reauth_message(code):
    return {
        "MFA_CODE_REQUIRED": "Enter your authenticator code to elevate.",
        "INVALID_MFA_CODE": "Invalid authentication code.",
        "MFA_ENROLLMENT_REQUIRED": "Enroll in MFA before requesting elevated access.",
        "MFA_UNAVAILABLE": "Elevation is temporarily unavailable. Try again shortly.",
        "PASSWORD_REQUIRED": "Re-enter your password to elevate.",
        "INVALID_PASSWORD": "Incorrect password.",
    }.get(code, "Re-authentication failed.")
