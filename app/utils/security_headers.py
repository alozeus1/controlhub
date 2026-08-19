"""
Response security headers, set by the application rather than by a proxy.

nginx.conf sets a full header policy, but nginx is only in the docker-compose
topology. The Procfile — what Railway actually runs — starts gunicorn directly, so
in production nothing upstream of Flask adds Content-Security-Policy or
Strict-Transport-Security. Setting them here means the policy travels with the
application and does not depend on which topology it is deployed into.

Headers are only set when absent, so a fronting proxy that already sent a stricter
value stays authoritative and browsers do not have to intersect two policies.
"""
import os

from flask import request

# Mirrors the policy in nginx.conf so the two origins cannot disagree.
# style-src allows 'unsafe-inline' because React sets inline style attributes;
# script-src does not, because the Vite build ships hashed bundles and the one
# server-rendered template (app/templates/index.html) has no inline script.
DEFAULT_CSP = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: https:; "
    "font-src 'self' data:; "
    "connect-src 'self'; "
    "frame-src 'self'; "
    "object-src 'none'; "
    "base-uri 'self'; "
    "form-action 'self'; "
    "frame-ancestors 'none'"
)

DEFAULT_HSTS = "max-age=31536000; includeSubDomains"

# Paths whose responses must never be cached: everything that can carry
# per-principal or restricted data.
NO_STORE_PREFIXES = ("/auth", "/admin", "/email", "/features")


def _wants_hsts() -> bool:
    """
    Only assert HSTS over a connection the client reached by TLS.

    `request.is_secure` reflects X-Forwarded-Proto once ProxyFix is configured, so
    this is true behind Railway's TLS edge and behind nginx, and false in plain
    local development where a year-long pin would be a nuisance.
    HSTS_ALWAYS forces it on for a deployment that terminates TLS somewhere this
    process cannot observe.
    """
    if os.environ.get("HSTS_ALWAYS", "").lower() in ("1", "true", "yes", "on"):
        return True
    return bool(request.is_secure)


def add_security_headers(response):
    """Add security headers to all responses, without overriding a proxy's values."""
    defaults = {
        "X-Frame-Options": "DENY",
        "X-Content-Type-Options": "nosniff",
        "X-XSS-Protection": "1; mode=block",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "Permissions-Policy": "geolocation=(), camera=()",
        "Content-Security-Policy": os.environ.get("CONTENT_SECURITY_POLICY") or DEFAULT_CSP,
        # Isolates this origin's browsing context group from a cross-origin opener.
        "Cross-Origin-Opener-Policy": "same-origin",
        # Blocks the legacy Adobe cross-domain policy vector.
        "X-Permitted-Cross-Domain-Policies": "none",
    }
    for header, value in defaults.items():
        if header not in response.headers:
            response.headers[header] = value

    if _wants_hsts() and "Strict-Transport-Security" not in response.headers:
        response.headers["Strict-Transport-Security"] = (
            os.environ.get("STRICT_TRANSPORT_SECURITY") or DEFAULT_HSTS
        )

    if request.path.startswith(NO_STORE_PREFIXES):
        response.headers["Cache-Control"] = "no-store"

    return response


def init_security_headers(app):
    app.after_request(add_security_headers)
