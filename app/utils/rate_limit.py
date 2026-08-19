"""
Rate-limit key selection.

The default `get_remote_address` key is the wrong bucket for authenticated,
expensive operations. It is simultaneously too coarse and too loose:

* Too coarse — every operator behind one office egress IP shares a bucket, so a
  normal admin can rate-limit their colleagues out of an export.
* Too loose — bulk extraction and AI-agent invocation are billed per call and
  authorized per principal, and a caller with a pool of source addresses gets a
  fresh quota with every hop.

Keying on the authenticated principal, falling back to the source address for
anonymous traffic, gives each identity its own quota and keeps a stolen session
from spending more than that identity's share.
"""
import hashlib

from flask import request
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request

try:
    from flask_limiter.util import get_remote_address
except ImportError:  # pragma: no cover - limiter is optional at import time
    def get_remote_address():
        return request.remote_addr or "0.0.0.0"


def identity_rate_key() -> str:
    """
    Return a rate-limit bucket key for the current request.

    Resolution order: service-account API key, then JWT subject, then source IP.
    The identity is resolved from the credential itself rather than from
    `request.current_user`, because flask-limiter evaluates limits before the
    view's auth decorator has run.

    The API key is hashed: limiter keys live in Redis and appear in slow-log and
    keyspace output, so the raw credential must never become one.
    """
    api_key = request.headers.get("X-API-Key")
    if api_key:
        return "svc:" + hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:32]

    try:
        verify_jwt_in_request(optional=True)
        identity = get_jwt_identity()
        if identity:
            return f"user:{identity}"
    except Exception:
        # An invalid, expired or revoked token is anonymous for quota purposes;
        # authentication itself is enforced by the route's own decorator.
        pass

    return f"ip:{get_remote_address()}"
