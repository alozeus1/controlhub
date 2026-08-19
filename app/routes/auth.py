import os
from html import escape as html_escape

from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import (
    jwt_required,
    get_jwt_identity,
    get_jwt,
)
from app.models import User, PasswordResetToken
from app.extensions import db, limiter, mail
from app.utils.rbac import require_active_user
from app.utils.audit import log_login, log_logout, log_action
from app.services.session_security import (
    issue_token_pair,
    consume_refresh_token,
    bump_session_epoch,
)

try:
    from flask_mail import Message as MailMessage
    _mail_available = True
except ImportError:
    _mail_available = False

auth_bp = Blueprint("auth", __name__)


def _reset_link_base() -> str:
    """
    Resolve the canonical origin for password-reset links.

    Never derived from the request. `request.host_url` reads the client-supplied
    Host header, and nginx here uses a catch-all `server_name _` while forwarding
    `Host $host`, so an attacker could POST /auth/forgot-password for a victim's
    address with `Host: evil.example.com` and the victim would receive a genuine
    ControlHub email whose reset link — and therefore the single-use token —
    points at the attacker. That is account takeover with one unauthenticated
    request, so the origin comes from configuration only.

    UI_BASE_URL wins when set (the link targets the SPA route /ui/reset-password);
    otherwise PUBLIC_BASE_URL, which config.py always defines.
    """
    base = (os.environ.get("UI_BASE_URL")
            or current_app.config.get("PUBLIC_BASE_URL")
            or os.environ.get("PUBLIC_BASE_URL")
            or "")
    base = base.rstrip("/")
    if not base:
        # Refuse to fall back to the Host header. Better a loud misconfiguration
        # than a silently attacker-controlled reset link.
        current_app.logger.error(
            "Cannot build a password-reset link: set UI_BASE_URL or PUBLIC_BASE_URL."
        )
        return ""
    if "localhost" in base and os.environ.get("FLASK_ENV", "").lower() in ("production", "prod", "staging"):
        current_app.logger.error(
            "Password-reset links point at %s in a deployed environment; "
            "set UI_BASE_URL/PUBLIC_BASE_URL to the real public origin.", base
        )
    return base


def _send_reset_email(email, reset_url, text_body):
    """
    Deliver the password-reset mail. Prefers Amazon SES (transactional identity);
    falls back to SMTP when SES is not configured for this deployment.

    Returns True if a transport accepted the message, False if none was
    configured or every attempt failed (caller then logs the dev fallback).
    """
    subject = "ControlHub — Password Reset"
    # reset_url comes from configuration (see _reset_link_base), not the request.
    # Still escaped before it lands in an href attribute.
    safe_url = html_escape(reset_url, quote=True)
    html_body = (
        "<p>Hello,</p>"
        "<p>Click the link below to reset your password:</p>"
        f'<p><a href="{safe_url}">Reset your password</a></p>'
        f"<p>This link expires in "
        f"{current_app.config.get('PASSWORD_RESET_EXPIRES_MINUTES', 60)} minutes.</p>"
        "<p>If you did not request a password reset, ignore this email.</p>"
    )

    from app.services import email_ses

    if email_ses.transactional_ses_configured():
        result = email_ses.send_transactional_email(
            to_address=email, subject=subject, html_body=html_body, text_body=text_body,
        )
        if result.ok:
            return True
        current_app.logger.error(f"SES reset email failed for {email}: {result.error}")

    if _mail_available and current_app.config.get("MAIL_SERVER") not in (None, "localhost"):
        try:
            mail.send(MailMessage(subject=subject, recipients=[email], body=text_body))
            return True
        except Exception as e:
            current_app.logger.error(f"Failed to send reset email to {email}: {e}")

    return False


# ---------------------------------------------------------------------------
# LOGIN  (rate-limited: 10/minute per IP)
# ---------------------------------------------------------------------------
@auth_bp.post("/login")
@limiter.limit("10 per minute")
def login():
    data = request.get_json() or {}

    email = data.get("email", "").strip().lower()
    password = data.get("password", "")

    if not email or not password:
        return jsonify({"error": "Email and password are required"}), 400

    user = User.query.filter_by(email=email).first()

    if not user or not user.check_password(password):
        log_login(email, success=False)
        return jsonify({"error": "Invalid email or password"}), 401

    if not user.is_active:
        log_login(email, success=False)
        return jsonify({
            "error": "Account is disabled. Contact an administrator.",
            "code": "ACCOUNT_DISABLED"
        }), 403

    # Second factor: if the user has MFA enabled, return a short-lived challenge
    # instead of full tokens. The client completes it via /auth/mfa/login-verify.
    try:
        from app.routes.mfa import mfa_enabled_for, mfa_required_for, issue_mfa_challenge_token
        if mfa_enabled_for(user):
            return jsonify({
                "mfa_required": True,
                "mfa_token": issue_mfa_challenge_token(user),
            }), 200
        # Org policy may require enrollment before full access is granted.
        if mfa_required_for(user):
            access_token, refresh_token, _ = issue_token_pair(user)
            log_login(user, success=True)
            return jsonify({
                "access_token": access_token,
                "refresh_token": refresh_token,
                "user": user.to_dict(),
                "mfa_enrollment_required": True,
            }), 200
    except Exception as exc:
        # FAIL CLOSED. An error here previously fell through to issuing full
        # tokens, silently downgrading every MFA-protected account to
        # password-only for the duration of the fault. Refusing the login is the
        # correct trade for an internal tool, and matches the deliberate
        # fail-closed choice already made for JWT revocation (app/__init__.py).
        current_app.logger.error(
            "MFA evaluation failed for user_id=%s; denying login: %s", user.id, exc
        )
        return jsonify({
            "error": "Sign-in is temporarily unavailable. Please try again shortly.",
            "code": "MFA_UNAVAILABLE",
        }), 503

    access_token, refresh_token, _ = issue_token_pair(user)
    log_login(user, success=True)

    return jsonify({
        "access_token": access_token,
        "refresh_token": refresh_token,
        "user": user.to_dict()
    }), 200


# ---------------------------------------------------------------------------
# REFRESH
# ---------------------------------------------------------------------------
@auth_bp.post("/refresh")
@jwt_required(refresh=True)
def refresh():
    identity = get_jwt_identity()
    user = User.query.get(int(identity))
    if not user or not user.is_active:
        return jsonify({"error": "User not found or disabled"}), 401

    claims = get_jwt()
    family = claims.get("family")

    # Rotate: this refresh token is spent. If it was already spent, someone is
    # replaying a captured token — kill the family and make both parties
    # re-authenticate rather than letting the attacker ride the session.
    if not consume_refresh_token(claims.get("jti"), family):
        log_action(
            action="auth.refresh_token_reuse",
            actor=user,
            target_type="user",
            target_id=user.id,
            target_label=user.email,
            details={"family": family},
        )
        return jsonify({
            "error": "Your session is no longer valid. Please sign in again.",
            "code": "TOKEN_REUSE_DETECTED",
        }), 401

    new_access, new_refresh, _ = issue_token_pair(user, family=family)
    return jsonify({
        "access_token": new_access,
        "refresh_token": new_refresh,
    }), 200


# ---------------------------------------------------------------------------
# CURRENT USER
# ---------------------------------------------------------------------------
@auth_bp.get("/me")
@require_active_user
def me():
    user = request.current_user
    return jsonify(user.to_dict())


@auth_bp.patch("/me")
@require_active_user
def update_me():
    """Self-service preference updates. Currently limited to the in-app
    notification bell toggle — not a general profile editor."""
    user = request.current_user
    data = request.get_json() or {}

    allowed_fields = {"notifications_enabled"}
    unexpected = sorted(set(data.keys()) - allowed_fields)
    if unexpected:
        return jsonify({
            "error": "Validation failed",
            "code": "VALIDATION_ERROR",
            "details": [f"Unexpected fields: {', '.join(unexpected)}"],
        }), 400

    if "notifications_enabled" in data:
        if not isinstance(data["notifications_enabled"], bool):
            return jsonify({
                "error": "Validation failed",
                "code": "VALIDATION_ERROR",
                "details": ["notifications_enabled must be a boolean"],
            }), 400
        user.notifications_enabled = data["notifications_enabled"]

    db.session.commit()
    return jsonify(user.to_dict())


# ---------------------------------------------------------------------------
# LOGOUT  — blocklist the access token in Redis
# ---------------------------------------------------------------------------
@auth_bp.post("/logout")
@require_active_user
def logout():
    user = request.current_user
    jti = get_jwt().get("jti")
    _redis = current_app._redis

    if _redis and jti:
        # Store jti until token expiry (default: access token TTL + buffer)
        ttl = int(current_app.config.get("JWT_ACCESS_TOKEN_EXPIRES", 3600)) + 60
        _redis.setex(f"blocklist:{jti}", ttl, "1")

    log_logout(user)
    return jsonify({"message": "Logged out successfully"}), 200


# ---------------------------------------------------------------------------
# FORGOT PASSWORD
# ---------------------------------------------------------------------------
@auth_bp.post("/forgot-password")
@limiter.limit("5 per minute")
def forgot_password():
    data = request.get_json() or {}
    email = data.get("email", "").strip().lower()

    if not email:
        return jsonify({"error": "Email is required"}), 400

    # Always return the same message to prevent user enumeration
    user = User.query.filter_by(email=email).first()
    if user and user.is_active:
        expires = current_app.config.get("PASSWORD_RESET_EXPIRES_MINUTES", 60)
        raw_token, token_obj = PasswordResetToken.generate(user.id, expires_minutes=expires)
        db.session.add(token_obj)
        db.session.commit()

        base = _reset_link_base()
        if not base:
            # Do not leak whether the address exists, and do not mail a link we
            # cannot build safely.
            return jsonify({"message": "If this email exists, a reset link has been sent"}), 200
        reset_url = f"{base}/ui/reset-password?token={raw_token}"
        text_body = (
            f"Hello,\n\nClick the link below to reset your password:\n\n"
            f"{reset_url}\n\n"
            f"This link expires in {expires} minutes.\n\n"
            "If you did not request a password reset, ignore this email."
        )

        if not _send_reset_email(email, reset_url, text_body):
            # Log the reset URL for development environments
            current_app.logger.info(f"[DEV] Password reset URL for {email}: {reset_url}")

    return jsonify({"message": "If this email exists, a reset link has been sent"}), 200


# ---------------------------------------------------------------------------
# RESET PASSWORD
# ---------------------------------------------------------------------------
@auth_bp.post("/reset-password")
@limiter.limit("5 per minute")
def reset_password():
    data = request.get_json() or {}
    raw_token = data.get("token", "").strip()
    new_password = data.get("new_password", "")

    if not raw_token or not new_password:
        return jsonify({"error": "Token and new password are required"}), 400

    if len(new_password) < 8:
        return jsonify({"error": "Password must be at least 8 characters"}), 400

    token_hash = PasswordResetToken.hash_token(raw_token)
    token_obj = PasswordResetToken.query.filter_by(token_hash=token_hash).first()

    if not token_obj or not token_obj.is_valid:
        return jsonify({"error": "Invalid or expired reset token"}), 400

    user = token_obj.user
    if not user or not user.is_active:
        return jsonify({"error": "User not found or disabled"}), 400

    from datetime import datetime
    user.set_password(new_password)
    token_obj.used_at = datetime.utcnow()
    db.session.commit()

    # A reset is how an account is recovered after compromise, so every session
    # that existed before it must die — including the attacker's.
    bump_session_epoch(user, "password_reset")

    return jsonify({"message": "Password reset successfully"}), 200


# ---------------------------------------------------------------------------
# CHANGE PASSWORD  (authenticated)
# ---------------------------------------------------------------------------
@auth_bp.post("/change-password")
@require_active_user
def change_password():
    user = request.current_user
    data = request.get_json() or {}

    current_password = data.get("current_password", "")
    new_password = data.get("new_password", "")

    if not current_password or not new_password:
        return jsonify({"error": "Current and new password are required"}), 400

    if not user.check_password(current_password):
        return jsonify({"error": "Current password is incorrect"}), 400

    if len(new_password) < 8:
        return jsonify({"error": "New password must be at least 8 characters"}), 400

    if current_password == new_password:
        return jsonify({"error": "New password must differ from current password"}), 400

    user.set_password(new_password)
    db.session.commit()

    # Retire every session that predates the new password — a stolen token must
    # not survive the change made to lock the attacker out. The caller gets a
    # fresh pair back so the tab they are sitting in stays signed in.
    bump_session_epoch(user, "password_change")
    access_token, refresh_token, _ = issue_token_pair(user)

    return jsonify({
        "message": "Password changed successfully",
        "access_token": access_token,
        "refresh_token": refresh_token,
    }), 200
