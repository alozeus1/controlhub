from datetime import datetime, timedelta
import hashlib
import secrets

from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    jwt_required,
    get_jwt_identity,
    get_jwt,
)

from app.auth.cognito_service import CognitoAuthError, link_or_provision_user
from app.auth.password_policy import validate_password_strength
from app.auth.token_verifier import TokenVerificationError, get_cognito_verifier
from app.models import User, PasswordResetToken
from app.extensions import db, limiter, mail
from app.utils.rbac import require_active_user
from app.utils.audit import log_login, log_logout, log_action

try:
    from flask_mail import Message as MailMessage
    _mail_available = True
except ImportError:
    _mail_available = False

auth_bp = Blueprint("auth", __name__)


def _create_email_token(user_id: int, purpose: str = "verify_email"):
    raw = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw.encode()).hexdigest()
    token_obj = PasswordResetToken(
        user_id=user_id,
        token_hash=token_hash,
        expires_at=datetime.utcnow() + timedelta(minutes=60),
    )
    db.session.add(token_obj)
    db.session.commit()
    return raw


def _send_email_if_configured(email: str, subject: str, body: str):
    if _mail_available and current_app.config.get("MAIL_SERVER") not in (None, "localhost"):
        try:
            msg = MailMessage(subject=subject, recipients=[email], body=body)
            mail.send(msg)
        except Exception as e:
            current_app.logger.error(f"Failed to send email to {email}: {e}")
    else:
        current_app.logger.info(f"[DEV] Email to {email}: {body}")


@auth_bp.post("/login")
@limiter.limit("10 per minute")
def login():
    if current_app.config.get("AUTH_MODE") == "cognito":
        return jsonify({"error": "Local login disabled"}), 403

    data = request.get_json() or {}
    email = data.get("email", "").strip().lower()
    password = data.get("password", "")

    if not email or not password:
        return jsonify({"error": "Email and password are required"}), 400

    user = User.query.filter_by(email=email).first()
    if not user:
        log_login(email, success=False)
        return jsonify({"error": "Invalid email or password"}), 401

    now = datetime.utcnow()
    if user.locked_until and user.locked_until > now:
        log_action("auth.account_locked", actor=user, target_type="user", target_id=user.id, target_label=user.email)
        return jsonify({"error": "Account locked. Try again later.", "code": "ACCOUNT_LOCKED"}), 423

    if not user.check_password(password):
        user.failed_login_count = (user.failed_login_count or 0) + 1
        max_attempts = current_app.config.get("MAX_FAILED_LOGIN_ATTEMPTS", 5)
        if user.failed_login_count >= max_attempts:
            user.locked_until = now + timedelta(minutes=current_app.config.get("ACCOUNT_LOCKOUT_MINUTES", 15))
            log_action("auth.account_locked", actor=user, target_type="user", target_id=user.id, target_label=user.email)
        db.session.commit()
        log_action("auth.login_failure", actor=None, target_type="user", target_label=email, details={"reason": "invalid_credentials"})
        return jsonify({"error": "Invalid email or password"}), 401

    if not user.is_active:
        log_action("auth.login_failure", actor=user, target_type="user", target_id=user.id, target_label=user.email, details={"reason": "inactive"})
        return jsonify({"error": "Account is disabled. Contact an administrator.", "code": "ACCOUNT_DISABLED"}), 403

    if current_app.config.get("REQUIRE_EMAIL_VERIFICATION", False) and not user.email_verified:
        return jsonify({"error": "Email verification required", "code": "EMAIL_NOT_VERIFIED"}), 403

    access_token = create_access_token(identity=str(user.id), additional_claims={"provider": "local"})
    refresh_token = create_refresh_token(identity=str(user.id), additional_claims={"provider": "local"})
    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now
    user.last_login_ip = request.headers.get("X-Forwarded-For", request.remote_addr)
    user.last_login_user_agent = (request.headers.get("User-Agent", "") or "")[:255]
    db.session.commit()

    log_login(user, success=True)
    log_action("auth.login_success", actor=user, target_type="user", target_id=user.id, target_label=user.email)

    return jsonify({"access_token": access_token, "refresh_token": refresh_token, "user": user.to_dict()}), 200


@auth_bp.post("/cognito/login")
@limiter.limit("10 per minute")
def cognito_login():
    mode = current_app.config.get("AUTH_MODE")
    if mode == "local":
        return jsonify({"error": "Cognito auth disabled"}), 403

    token = (request.get_json() or {}).get("id_token") or (request.get_json() or {}).get("token")
    if not token:
        return jsonify({"error": "Token is required"}), 400

    try:
        identity = get_cognito_verifier().verify(token)
        user = link_or_provision_user(identity)
    except (TokenVerificationError, CognitoAuthError, Exception):
        log_action("auth.cognito_login_failure", actor=None, target_type="user", details={"reason": "verification_or_link_failed"})
        return jsonify({"error": "Authentication failed"}), 401

    access_token = create_access_token(identity=str(user.id), additional_claims={"provider": "cognito"})
    refresh_token = create_refresh_token(identity=str(user.id), additional_claims={"provider": "cognito"})

    log_action("auth.cognito_login_success", actor=user, target_type="user", target_id=user.id, target_label=user.email)
    return jsonify({"access_token": access_token, "refresh_token": refresh_token, "user": user.to_dict(), "auth_provider": "cognito"}), 200


@auth_bp.post("/refresh")
@jwt_required(refresh=True)
def refresh():
    identity = get_jwt_identity()
    user = User.query.get(int(identity))
    if not user or not user.is_active:
        return jsonify({"error": "User not found or disabled"}), 401

    provider = get_jwt().get("provider", "local")
    new_access = create_access_token(identity=identity, additional_claims={"provider": provider})
    return jsonify({"access_token": new_access}), 200


@auth_bp.get("/me")
@require_active_user
def me():
    user = request.current_user
    return jsonify(user.to_dict())


@auth_bp.post("/logout")
@require_active_user
def logout():
    user = request.current_user
    jti = get_jwt().get("jti")
    _redis = current_app._redis

    if _redis and jti:
        ttl = int(current_app.config.get("JWT_ACCESS_TOKEN_EXPIRES", 3600)) + 60
        _redis.setex(f"blocklist:{jti}", ttl, "1")

    log_logout(user)
    log_action("auth.logout", actor=user, target_type="user", target_id=user.id, target_label=user.email)
    return jsonify({"message": "Logged out successfully"}), 200


@auth_bp.post("/forgot-password")
@limiter.limit("5 per minute")
def forgot_password():
    data = request.get_json() or {}
    email = data.get("email", "").strip().lower()

    if not email:
        return jsonify({"error": "Email is required"}), 400

    user = User.query.filter_by(email=email).first()
    if user and user.is_active:
        expires = current_app.config.get("PASSWORD_RESET_EXPIRES_MINUTES", 60)
        raw_token, token_obj = PasswordResetToken.generate(user.id, expires_minutes=expires)
        db.session.add(token_obj)
        db.session.commit()
        reset_url = f"{request.host_url.rstrip('/')}/ui/reset-password?token={raw_token}"
        _send_email_if_configured(
            email,
            "ControlHub — Password Reset",
            (
                f"Hello,\n\nClick the link below to reset your password:\n\n{reset_url}\n\n"
                f"This link expires in {expires} minutes.\n\n"
                "If you did not request a password reset, ignore this email."
            ),
        )
        log_action("auth.password_reset_requested", actor=user, target_type="user", target_id=user.id, target_label=user.email)

    return jsonify({"message": "If this email exists, a reset link has been sent"}), 200


@auth_bp.post("/reset-password")
@limiter.limit("5 per minute")
def reset_password():
    data = request.get_json() or {}
    raw_token = data.get("token", "").strip()
    new_password = data.get("new_password", "")

    if not raw_token or not new_password:
        return jsonify({"error": "Token and new password are required"}), 400

    ok, reason = validate_password_strength(new_password)
    if not ok:
        return jsonify({"error": reason}), 400

    token_hash = PasswordResetToken.hash_token(raw_token)
    token_obj = PasswordResetToken.query.filter_by(token_hash=token_hash).first()

    if not token_obj or not token_obj.is_valid:
        return jsonify({"error": "Invalid or expired reset token"}), 400

    user = token_obj.user
    if not user or not user.is_active:
        return jsonify({"error": "User not found or disabled"}), 400

    user.set_password(new_password)
    token_obj.used_at = datetime.utcnow()
    db.session.commit()
    log_action("auth.password_reset_completed", actor=user, target_type="user", target_id=user.id, target_label=user.email)

    return jsonify({"message": "Password reset successfully"}), 200


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

    ok, reason = validate_password_strength(new_password)
    if not ok:
        return jsonify({"error": reason}), 400

    if current_password == new_password:
        return jsonify({"error": "New password must differ from current password"}), 400

    user.set_password(new_password)
    db.session.commit()

    return jsonify({"message": "Password changed successfully"}), 200


@auth_bp.post("/verify-email")
@limiter.limit("10 per hour")
def verify_email():
    token = (request.get_json() or {}).get("token", "").strip()
    if not token:
        return jsonify({"error": "Token is required"}), 400

    token_hash = PasswordResetToken.hash_token(token)
    token_obj = PasswordResetToken.query.filter_by(token_hash=token_hash).first()
    if not token_obj or not token_obj.is_valid:
        return jsonify({"error": "Invalid or expired token"}), 400

    user = token_obj.user
    user.email_verified = True
    token_obj.used_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"message": "Email verified"}), 200


@auth_bp.post("/resend-verification")
@limiter.limit("3 per hour")
def resend_verification():
    email = (request.get_json() or {}).get("email", "").strip().lower()
    if not email:
        return jsonify({"error": "Email is required"}), 400

    user = User.query.filter_by(email=email).first()
    if user and not user.email_verified:
        token = _create_email_token(user.id)
        verify_url = f"{request.host_url.rstrip('/')}/ui/verify-email?token={token}"
        _send_email_if_configured(email, "ControlHub — Verify Email", f"Verify your email: {verify_url}")

    return jsonify({"message": "If this email exists, verification email sent"}), 200
