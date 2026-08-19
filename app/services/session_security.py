"""
Continuous session verification.

Two controls, both aimed at the same adversary: someone who already holds a
valid token.

1. Refresh-token rotation with reuse detection. Every refresh consumes the old
   token and issues a new one carrying the same `family` id. Replaying a
   consumed refresh token is a near-unambiguous theft signal, so it revokes the
   whole family — the attacker and the legitimate user are both logged out, and
   the event is audited.

2. A per-user revocation epoch embedded in every token. Bumping the user's epoch
   invalidates all of their outstanding tokens on the next request, instead of
   waiting out the access-token TTL.

State lives in Redis alongside the existing jti blocklist. Redis being
unavailable is treated the same way `app/__init__.py` already treats it for
revocation: fail CLOSED unless JWT_FAIL_OPEN is explicitly set.
"""
import logging
import uuid

from flask import current_app

logger = logging.getLogger(__name__)

# Refresh-family keys outlive the refresh token itself so a replay well after
# rotation is still caught. Matches JWT_REFRESH_TOKEN_EXPIRES (7 days) + slack.
FAMILY_TTL_SECONDS = 8 * 24 * 3600


def _redis():
    return getattr(current_app, "_redis", None)


def _fail_open():
    return bool(current_app.config.get("JWT_FAIL_OPEN", False))


def new_family_id() -> str:
    """Mint a refresh-token family id, issued at login and carried across rotations."""
    return uuid.uuid4().hex


def session_epoch_for(user) -> int:
    return int(getattr(user, "session_epoch", 0) or 0)


def bump_session_epoch(user, reason: str):
    """
    Invalidate every outstanding token for this user.

    Call on disable, role change, password change, and any other event after
    which an already-issued token should no longer be honored.
    """
    from app.extensions import db

    user.session_epoch = session_epoch_for(user) + 1
    db.session.commit()
    logger.info("session_epoch bumped for user_id=%s (%s) -> %s",
                user.id, reason, user.session_epoch)
    return user.session_epoch


def epoch_is_current(jwt_payload) -> bool:
    """
    True when the token's epoch still matches the user's.

    Tokens minted before this feature shipped carry no epoch claim; those are
    accepted only while the user's epoch is still 0, so the first bump
    invalidates legacy tokens too rather than leaving a permanent bypass.
    """
    from app.models import User

    identity = jwt_payload.get("sub")
    if identity is None:
        return True
    try:
        user = User.query.get(int(identity))
    except (TypeError, ValueError):
        return True
    if user is None:
        return False
    return int(jwt_payload.get("session_epoch", 0) or 0) == session_epoch_for(user)


# ─── Token issuance ───────────────────────────────────────────────────────────

def issue_token_pair(user, family=None):
    """
    Mint an access/refresh pair bound to one refresh family.

    Single entry point for every login path (password, MFA, SSO) so the family
    claim cannot be forgotten on one of them. `session_epoch` is attached
    globally by the JWT additional-claims loader.
    """
    from flask_jwt_extended import create_access_token, create_refresh_token

    family = family or new_family_id()
    claims = {"family": family}
    return (
        create_access_token(identity=str(user.id), additional_claims=claims),
        create_refresh_token(identity=str(user.id), additional_claims=claims),
        family,
    )


# ─── Refresh-token families ───────────────────────────────────────────────────

def _family_key(family):
    return f"refresh_family_revoked:{family}"


def _used_key(jti):
    return f"refresh_used:{jti}"


def family_revoked(family) -> bool:
    """True if this refresh family was killed by a reuse detection."""
    if not family:
        return False
    client = _redis()
    if client is None:
        return not _fail_open()
    try:
        return client.get(_family_key(family)) is not None
    except Exception as exc:
        logger.error("refresh family check failed: %s; failing %s",
                     exc, "OPEN" if _fail_open() else "CLOSED")
        return not _fail_open()


def revoke_family(family, reason: str):
    """Kill every token in a refresh family."""
    if not family:
        return
    client = _redis()
    if client is None:
        logger.error("cannot revoke refresh family %s: no redis", family)
        return
    try:
        client.setex(_family_key(family), FAMILY_TTL_SECONDS, reason)
    except Exception as exc:
        logger.error("failed to revoke refresh family %s: %s", family, exc)


def consume_refresh_token(jti, family) -> bool:
    """
    Mark a refresh token as spent.

    Returns True if this was its first use. Returns False if it had already been
    consumed — a replay — and revokes the family as a side effect.

    Fails CLOSED when Redis is unavailable: without the store we cannot tell a
    first use from a replay, and honoring it would hand an attacker exactly the
    control this function exists to remove.
    """
    client = _redis()
    if client is None:
        logger.error("refresh reuse check unavailable (no redis); failing %s",
                     "OPEN" if _fail_open() else "CLOSED")
        return bool(_fail_open())

    try:
        # SET NX is atomic, so two concurrent replays cannot both win.
        first_use = client.set(_used_key(jti), family or "1",
                               nx=True, ex=FAMILY_TTL_SECONDS)
        if first_use:
            return True
        logger.warning("refresh token reuse detected (jti=%s family=%s)", jti, family)
        revoke_family(family, "refresh_token_reuse")
        return False
    except Exception as exc:
        logger.error("refresh reuse check failed: %s; failing %s",
                     exc, "OPEN" if _fail_open() else "CLOSED")
        return bool(_fail_open())
