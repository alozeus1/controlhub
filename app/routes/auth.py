from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    jwt_required,
    get_jwt_identity,
    get_jwt,
)
from app.models import User, PasswordResetToken
from app.extensions import db, limiter, mail
from app.utils.rbac import require_active_user
from app.utils.audit import log_login, log_logout

try:
    from flask_mail import Message as MailMessage
    _mail_available = True
except ImportError:
    _mail_available = False

auth_bp = Blueprint("auth", __name__)


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

    access_token = create_access_token(identity=str(user.id))
    refresh_token = create_refresh_token(identity=str(user.id))
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

    new_access = create_access_token(identity=identity)
    return jsonify({"access_token": new_access}), 200


# ---------------------------------------------------------------------------
# CURRENT USER
# ---------------------------------------------------------------------------
@auth_bp.get("/me")
@require_active_user
def me():
    user = request.current_user
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

        reset_url = f"{request.host_url.rstrip('/')}/ui/reset-password?token={raw_token}"

        if _mail_available and current_app.config.get("MAIL_SERVER") not in (None, "localhost"):
            try:
                msg = MailMessage(
                    subject="ControlHub — Password Reset",
                    recipients=[email],
                    body=(
                        f"Hello,\n\nClick the link below to reset your password:\n\n"
                        f"{reset_url}\n\n"
                        f"This link expires in {expires} minutes.\n\n"
                        "If you did not request a password reset, ignore this email."
                    ),
                )
                mail.send(msg)
            except Exception as e:
                current_app.logger.error(f"Failed to send reset email to {email}: {e}")
        else:
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

    return jsonify({"message": "Password changed successfully"}), 200
