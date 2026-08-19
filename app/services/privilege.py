"""
Just-in-time privilege elevation.

The premise of the rest of this design is that the attacker already holds a valid
session. Standing privilege makes that session immediately equal to everything
the user's role can do. JIT splits the two:

* **Eligibility** stays on the role (`app/permissions.py`) — who *may* elevate.
* **Activation** is this module — a time-boxed grant that costs a fresh second
  factor and a written reason, and expires on its own.

Three properties make the grant hard to inherit:

1. **Fresh re-authentication.** The proof is re-checked at elevation time, not
   read off the login session — because the stolen artifact *is* the session.
2. **Session binding.** The grant is tied to the refresh-token family that
   requested it, so a different stolen token for the same user cannot ride an
   elevation the real operator just activated.
3. **Automatic expiry**, with no renewal path that skips the reason.

Disabled by default: with `JIT_ELEVATED_PERMISSIONS` empty, nothing is gated and
behavior is unchanged. Turn it on per permission.
"""
import logging
from datetime import datetime, timedelta

from flask import current_app, request

logger = logging.getLogger(__name__)

DEFAULT_TTL_MINUTES = 15


def _csv_config(name, default=""):
    raw = current_app.config.get(name, default) or ""
    return {item.strip() for item in raw.split(",") if item.strip()}


def elevated_permissions() -> set:
    """Permission keys that require an active grant. Empty = feature off."""
    return _csv_config("JIT_ELEVATED_PERMISSIONS")


def dual_approval_permissions() -> set:
    """Subset that additionally needs a second human to approve."""
    return _csv_config("JIT_DUAL_APPROVAL_PERMISSIONS")


def elevation_required(permission_key: str) -> bool:
    return permission_key in elevated_permissions()


def requires_second_approver(permission_key: str) -> bool:
    return permission_key in dual_approval_permissions()


def ttl_minutes() -> int:
    try:
        return max(1, int(current_app.config.get("JIT_ELEVATION_TTL_MINUTES",
                                                 DEFAULT_TTL_MINUTES)))
    except (TypeError, ValueError):
        return DEFAULT_TTL_MINUTES


# ─── Re-authentication ────────────────────────────────────────────────────────

def verify_reauth(user, mfa_code=None, password=None):  # secret-scan:allow - test fixture / parameter name, not a credential
    """
    Prove the elevation request comes from the human, not just their session.

    Prefers the second factor. Falls back to the password only when the user has
    no MFA enrolled — weaker, but still something a token thief does not
    automatically hold. Set JIT_REQUIRE_MFA=true to remove the fallback and force
    enrollment before anyone can elevate.

    Returns (ok, error_code).
    """
    from app.routes.mfa import mfa_enabled_for, verify_second_factor

    try:
        has_mfa = mfa_enabled_for(user)
    except Exception as exc:
        # Same reasoning as the login path: an MFA fault must not silently
        # downgrade the check to password-only.
        logger.error("elevation MFA lookup failed for user_id=%s: %s", user.id, exc)
        return False, "MFA_UNAVAILABLE"

    if has_mfa:
        if not mfa_code:
            return False, "MFA_CODE_REQUIRED"
        return (True, None) if verify_second_factor(user, mfa_code) else (False, "INVALID_MFA_CODE")

    if current_app.config.get("JIT_REQUIRE_MFA", False):
        return False, "MFA_ENROLLMENT_REQUIRED"

    if not password:
        return False, "PASSWORD_REQUIRED"
    return (True, None) if user.check_password(password) else (False, "INVALID_PASSWORD")


# ─── Grants ───────────────────────────────────────────────────────────────────

def current_session_family():
    """Refresh-token family of the calling session, if the token carries one."""
    try:
        from flask_jwt_extended import get_jwt
        return (get_jwt() or {}).get("family")
    except Exception:
        return None


def active_grant(user_id, permission_key, session_family=None):
    """
    The live grant for this user+permission, or None.

    When the grant records a session family, only that session may use it.
    """
    from app.models import PrivilegeGrant

    grant = (PrivilegeGrant.query
             .filter(PrivilegeGrant.user_id == user_id,
                     PrivilegeGrant.permission_key == permission_key,
                     PrivilegeGrant.revoked_at.is_(None),
                     PrivilegeGrant.expires_at > datetime.utcnow())
             .order_by(PrivilegeGrant.expires_at.desc())
             .first())
    if grant is None:
        return None
    if grant.session_family and grant.session_family != session_family:
        logger.warning("elevation grant %s not usable from session family %s",
                       grant.id, session_family)
        return None
    return grant


def grant_elevation(user, permission_key, reason, approved_by=None, session_family=None):
    """Create a grant. Callers must have verified eligibility and re-auth first."""
    from app.extensions import db
    from app.models import PrivilegeGrant
    from app.utils.audit import log_action

    grant = PrivilegeGrant(
        user_id=user.id,
        permission_key=permission_key,
        reason=reason,
        session_family=session_family,
        granted_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(minutes=ttl_minutes()),
        approved_by_id=approved_by.id if approved_by else None,
        ip_address=(request.remote_addr if request else None),
    )
    db.session.add(grant)
    db.session.commit()

    log_action(
        action="privilege.elevated",
        actor=user,
        target_type="privilege_grant",
        target_id=grant.id,
        target_label=permission_key,
        details={"reason": reason, "ttl_minutes": ttl_minutes(),
                 "approved_by": approved_by.email if approved_by else None},
    )
    return grant


def record_use(grant):
    """Count a privileged action against its grant (best effort)."""
    from app.extensions import db

    try:
        grant.used_count = (grant.used_count or 0) + 1
        grant.last_used_at = datetime.utcnow()
        db.session.commit()
    except Exception as exc:  # pragma: no cover - must never block the action
        logger.error("failed to record elevation use for grant %s: %s", grant.id, exc)
        db.session.rollback()


def revoke_grant(grant, reason, actor=None):
    from app.extensions import db
    from app.utils.audit import log_action

    if grant.revoked_at is not None:
        return grant
    grant.revoked_at = datetime.utcnow()
    grant.revoked_reason = reason[:255]
    db.session.commit()

    log_action(
        action="privilege.revoked",
        actor=actor,
        target_type="privilege_grant",
        target_id=grant.id,
        target_label=grant.permission_key,
        details={"reason": reason},
    )
    return grant


def revoke_all_for_user(user, reason, actor=None):
    """
    Drop every live grant for a user.

    Called when the account is disabled or its role changes — otherwise a
    demoted admin keeps an activated privilege they are no longer eligible for
    until it happens to expire.
    """
    from app.models import PrivilegeGrant

    live = (PrivilegeGrant.query
            .filter(PrivilegeGrant.user_id == user.id,
                    PrivilegeGrant.revoked_at.is_(None),
                    PrivilegeGrant.expires_at > datetime.utcnow())
            .all())
    for grant in live:
        revoke_grant(grant, reason, actor=actor)
    return len(live)
