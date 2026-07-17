"""
Multi-factor authentication — TOTP + backup codes (feature 3).

Self-service enrollment lives under /auth/mfa/*. The login challenge is
completed via /auth/mfa/login-verify. Enforcement (org-level "require MFA")
is surfaced by the login endpoint via mfa_enrollment_required.

Foundational note: this covers TOTP enrollment, verification, backup codes, and
a login second-factor step. A production hardening pass should add rate-limiting
on verify attempts and encrypted backup-code display auditing.
"""
import hashlib
import secrets
from datetime import datetime, timedelta

import pyotp
import qrcode
import qrcode.image.svg
from io import BytesIO

from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token, create_refresh_token, decode_token

from app.extensions import db, limiter
from app.models import User, UserMfa, OrgSettings
from app.utils.rbac import require_active_user
from app.services.secret_crypto import encrypt_secret, decrypt_secret
from app.utils.audit import log_action

mfa_bp = Blueprint("mfa", __name__)
ISSUER = "Web Forx ControlHub"

# Lockout policy: after MAX_FAILED bad codes, lock for LOCK_MINUTES.
MAX_FAILED = 5
LOCK_MINUTES = 15


def _is_locked(row):
    return bool(row and row.locked_until and row.locked_until > datetime.utcnow())


def _register_failure(row):
    row.failed_attempts = (row.failed_attempts or 0) + 1
    if row.failed_attempts >= MAX_FAILED:
        row.locked_until = datetime.utcnow() + timedelta(minutes=LOCK_MINUTES)
        row.failed_attempts = 0
    db.session.commit()


def _reset_failures(row):
    if row.failed_attempts or row.locked_until:
        row.failed_attempts = 0
        row.locked_until = None
        db.session.commit()


# ─── helpers ──────────────────────────────────────────────────────────────────

def _get_or_create(user_id):
    row = UserMfa.query.filter_by(user_id=user_id).first()
    if not row:
        row = UserMfa(user_id=user_id)
        db.session.add(row)
        db.session.commit()
    return row


def _hash_code(code):
    return hashlib.sha256(code.strip().replace("-", "").lower().encode()).hexdigest()


def _new_backup_codes(n=10):
    codes = [f"{secrets.token_hex(2)}-{secrets.token_hex(2)}" for _ in range(n)]
    return codes, [_hash_code(c) for c in codes]


def mfa_enabled_for(user):
    row = UserMfa.query.filter_by(user_id=user.id).first()
    return bool(row and row.enabled)


def mfa_required_for(user):
    """Org policy: is MFA mandatory for this user's role?"""
    s = OrgSettings.get()
    if not s.mfa_required:
        return False
    roles = s.mfa_required_roles or []
    return (not roles) or (user.role in roles)


def issue_mfa_challenge_token(user):
    """Short-lived token proving password was verified, pending the 2nd factor."""
    return create_access_token(
        identity=str(user.id),
        additional_claims={"purpose": "mfa_challenge"},
        expires_delta=timedelta(minutes=5),
    )


def _verify_totp(row, code):
    if not row.secret_enc:
        return False
    try:
        secret = decrypt_secret(row.secret_enc)
    except Exception:
        return False
    return pyotp.TOTP(secret).verify((code or "").strip(), valid_window=1)


def _consume_backup_code(row, code):
    h = _hash_code(code)
    codes = row.backup_codes or []
    if h in codes:
        codes.remove(h)
        row.backup_codes = codes
        return True
    return False


def verify_second_factor(user, code):
    """
    True if `code` is a valid TOTP or an unused backup code (consumes it).
    Tracks failed attempts and enforces lockout. Returns False while locked.
    """
    row = UserMfa.query.filter_by(user_id=user.id).first()
    if not row or not row.enabled:
        return False
    if _is_locked(row):
        return False
    if _verify_totp(row, code):
        _reset_failures(row)
        return True
    if _consume_backup_code(row, code):
        _reset_failures(row)
        db.session.commit()
        return True
    _register_failure(row)
    return False


# ─── self-service enrollment ──────────────────────────────────────────────────

@mfa_bp.get("/mfa/status")
@require_active_user
def mfa_status():
    user = request.current_user
    row = UserMfa.query.filter_by(user_id=user.id).first()
    data = row.to_dict() if row else {"enabled": False, "pending": False, "backup_codes_remaining": 0}
    data["required_by_policy"] = mfa_required_for(user)
    return jsonify(data)


@mfa_bp.post("/mfa/setup")
@require_active_user
def mfa_setup():
    user = request.current_user
    row = _get_or_create(user.id)
    if row.enabled:
        return jsonify({"error": "MFA is already enabled. Disable it first to re-enroll."}), 409

    secret = pyotp.random_base32()
    row.secret_enc = encrypt_secret(secret)
    row.pending = True
    db.session.commit()

    otpauth = pyotp.TOTP(secret).provisioning_uri(name=user.email, issuer_name=ISSUER)
    # Render QR as SVG (no PIL dependency).
    buf = BytesIO()
    qrcode.make(otpauth, image_factory=qrcode.image.svg.SvgImage).save(buf)
    qr_svg = buf.getvalue().decode("utf-8")

    return jsonify({
        "secret": secret,          # for manual entry
        "otpauth_url": otpauth,
        "qr_svg": qr_svg,
        "issuer": ISSUER,
    })


@mfa_bp.post("/mfa/verify")
@limiter.limit("10 per minute")
@require_active_user
def mfa_verify():
    user = request.current_user
    row = UserMfa.query.filter_by(user_id=user.id).first()
    if not row or not row.secret_enc:
        return jsonify({"error": "Start MFA setup first"}), 400
    if _is_locked(row):
        return jsonify({"error": "Too many attempts. Try again later.", "code": "MFA_LOCKED"}), 429
    code = (request.get_json() or {}).get("code", "")
    if not _verify_totp(row, code):
        _register_failure(row)
        return jsonify({"error": "Invalid code. Check your authenticator and try again."}), 400
    _reset_failures(row)

    plaintext_codes, hashes = _new_backup_codes()
    row.enabled = True
    row.pending = False
    row.backup_codes = hashes
    row.confirmed_at = datetime.utcnow()
    db.session.commit()
    log_action("mfa.enabled", actor=user, target_type="user", target_id=user.id,
               target_label=user.email)
    return jsonify({"enabled": True, "backup_codes": plaintext_codes})


@mfa_bp.post("/mfa/disable")
@require_active_user
def mfa_disable():
    user = request.current_user
    row = UserMfa.query.filter_by(user_id=user.id).first()
    if not row or not row.enabled:
        return jsonify({"error": "MFA is not enabled"}), 400
    if mfa_required_for(user):
        return jsonify({"error": "MFA is required by your organization and cannot be disabled"}), 403
    code = (request.get_json() or {}).get("code", "")
    if not verify_second_factor(user, code):
        return jsonify({"error": "Enter a valid code to disable MFA"}), 400
    row.enabled = False
    row.pending = False
    row.secret_enc = None
    row.backup_codes = []
    db.session.commit()
    log_action("mfa.disabled", actor=user, target_type="user", target_id=user.id,
               target_label=user.email)
    return jsonify({"enabled": False})


@mfa_bp.post("/mfa/backup-codes")
@require_active_user
def mfa_regenerate_backup_codes():
    user = request.current_user
    row = UserMfa.query.filter_by(user_id=user.id).first()
    if not row or not row.enabled:
        return jsonify({"error": "MFA is not enabled"}), 400
    code = (request.get_json() or {}).get("code", "")
    if not _verify_totp(row, code):
        return jsonify({"error": "Enter a valid authenticator code"}), 400
    plaintext_codes, hashes = _new_backup_codes()
    row.backup_codes = hashes
    db.session.commit()
    return jsonify({"backup_codes": plaintext_codes})


# ─── login second factor ──────────────────────────────────────────────────────

@mfa_bp.post("/mfa/login-verify")
@limiter.limit("10 per minute")
def mfa_login_verify():
    data = request.get_json() or {}
    token = data.get("mfa_token", "")
    code = data.get("code", "")
    try:
        decoded = decode_token(token)
    except Exception:
        return jsonify({"error": "Invalid or expired challenge. Please log in again."}), 401
    if decoded.get("purpose") != "mfa_challenge":
        return jsonify({"error": "Invalid challenge token"}), 401

    user = User.query.get(int(decoded.get("sub")))
    if not user or not user.is_active:
        return jsonify({"error": "Invalid user"}), 401

    row = UserMfa.query.filter_by(user_id=user.id).first()
    if _is_locked(row):
        return jsonify({"error": "Too many attempts. Try again later.", "code": "MFA_LOCKED"}), 429

    if not verify_second_factor(user, code):
        log_action("mfa.login_failed", actor=user, target_type="user", target_id=user.id,
                   target_label=user.email)
        # If that failure just triggered a lock, signal it distinctly.
        db.session.refresh(row) if row else None
        if _is_locked(row):
            return jsonify({"error": "Too many attempts. Account temporarily locked.",
                            "code": "MFA_LOCKED"}), 429
        return jsonify({"error": "Invalid authentication code"}), 401

    access_token = create_access_token(identity=str(user.id))
    refresh_token = create_refresh_token(identity=str(user.id))
    log_action("mfa.login_verified", actor=user, target_type="user", target_id=user.id,
               target_label=user.email)
    return jsonify({"access_token": access_token, "refresh_token": refresh_token,
                    "user": user.to_dict()}), 200
