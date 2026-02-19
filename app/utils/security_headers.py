from flask import request


def add_security_headers(response):
    """Add security headers to all responses."""
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), camera=()"

    # No-store cache control for API routes
    if request.path.startswith("/auth") or request.path.startswith("/admin"):
        response.headers["Cache-Control"] = "no-store"

    return response


def init_security_headers(app):
    app.after_request(add_security_headers)
