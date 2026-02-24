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


def _deny_sub_mismatch(user: User, incoming_sub: str | None):
    log_action(
        "auth.cognito_sub_mismatch_denied",
        actor=user,
        target_type="user",
        target_id=user.id,
        target_label=user.email,
        details={"incoming_sub_present": bool(incoming_sub)},
    )
    raise CognitoAuthError("Authentication failed")


def link_or_provision_user(identity):
    if not identity.sub:
        raise CognitoAuthError("Authentication failed")

    user = User.query.filter_by(cognito_sub=identity.sub).first()

    if not user and identity.email:
        candidate = User.query.filter_by(email=identity.email.lower()).first()
        if candidate and candidate.cognito_sub:
            _deny_sub_mismatch(candidate, identity.sub)

        allow_linking = current_app.config.get("COGNITO_ALLOW_EMAIL_LINKING", True)
        email_verified = bool(identity.claims.get("email_verified"))
        if candidate and not candidate.cognito_sub and email_verified and allow_linking:
            candidate.cognito_sub = identity.sub
            log_action(
                "auth.user_linked_to_cognito",
                actor=candidate,
                target_type="user",
                target_id=candidate.id,
                target_label=candidate.email,
            )
            user = candidate

    if not user:
        if not current_app.config.get("COGNITO_AUTO_PROVISION", False):
            raise CognitoAuthError("Authentication failed")
        if not identity.email:
            raise CognitoAuthError("Authentication failed")
        user = User(
            email=identity.email.lower(),
            role="user",
            auth_provider="cognito",
            cognito_sub=identity.sub,
            email_verified=bool(identity.claims.get("email_verified", False)),
            password_hash="!",
        )
        db.session.add(user)

    if user.cognito_sub and user.cognito_sub != identity.sub:
        _deny_sub_mismatch(user, identity.sub)

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
