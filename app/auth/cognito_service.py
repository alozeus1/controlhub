from datetime import datetime

from flask import request, current_app

from app.extensions import db
from app.models import User
from app.utils.audit import log_action


class CognitoAuthError(Exception):
    pass


def _update_login_metadata(user: User):
    user.last_login_at = datetime.utcnow()
    user.last_login_ip = request.headers.get("X-Forwarded-For", request.remote_addr)
    user.last_login_user_agent = (request.headers.get("User-Agent", "") or "")[:255]


def link_or_provision_user(identity):
    # 1) find by sub
    user = None
    if identity.sub:
        user = User.query.filter_by(cognito_sub=identity.sub).first()

    # 2) fallback to verified email
    if not user and identity.email and identity.claims.get("email_verified"):
        user = User.query.filter_by(email=identity.email.lower()).first()
        if user and not user.cognito_sub:
            user.cognito_sub = identity.sub
            log_action("auth.user_linked_to_cognito", actor=user, target_type="user", target_id=user.id, target_label=user.email)

    # 3) optional provisioning
    if not user:
        if not current_app.config.get("COGNITO_AUTO_PROVISION", False):
            raise CognitoAuthError("User not provisioned")
        if not identity.email:
            raise CognitoAuthError("Email is required for provisioning")
        user = User(
            email=identity.email.lower(),
            role="user",
            auth_provider="cognito",
            cognito_sub=identity.sub,
            email_verified=bool(identity.claims.get("email_verified", False)),
            password_hash="!",
        )
        db.session.add(user)

    user.auth_provider = "cognito"
    user.email_verified = bool(identity.claims.get("email_verified", user.email_verified))
    user.phone_number = identity.claims.get("phone_number") or user.phone_number
    user.phone_verified = bool(identity.claims.get("phone_number_verified", user.phone_verified))
    user.mfa_enabled = bool(identity.claims.get("cognito:preferred_mfa_setting") or identity.claims.get("amr"))
    _update_login_metadata(user)
    user.failed_login_count = 0
    user.locked_until = None

    db.session.commit()
    return user
