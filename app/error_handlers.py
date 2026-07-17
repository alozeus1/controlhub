"""
Centralized JSON error handling for the API.

Guarantees every error (including uncaught exceptions and Flask's own
404/405/429) returns a consistent, production-safe JSON body:

    {"error": "<safe message>", "code": "<STABLE_CODE>", "request_id": "<id>"}

Never leaks stack traces, SQL, filesystem paths, or internals to clients.
Server-side logging retains the full exception with the correlation id.
"""
import logging

from flask import jsonify, g, request
from werkzeug.exceptions import HTTPException

logger = logging.getLogger(__name__)

# HTTP status -> stable machine code.
_STATUS_CODE = {
    400: "BAD_REQUEST",
    401: "AUTH_REQUIRED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    413: "PAYLOAD_TOO_LARGE",
    415: "UNSUPPORTED_MEDIA_TYPE",
    422: "UNPROCESSABLE_ENTITY",
    429: "RATE_LIMITED",
    500: "INTERNAL_ERROR",
    502: "BAD_GATEWAY",
    503: "SERVICE_UNAVAILABLE",
}

# Safe, generic client-facing messages (never echo internals).
_SAFE_MESSAGE = {
    400: "The request was invalid.",
    401: "Authentication is required.",
    403: "You do not have permission to perform this action.",
    404: "The requested resource was not found.",
    405: "That method is not allowed on this endpoint.",
    409: "The request conflicts with the current state.",
    413: "The request payload is too large.",
    415: "Unsupported media type.",
    422: "The request could not be processed.",
    429: "Too many requests. Please slow down.",
    500: "An internal server error occurred.",
    502: "Upstream service error.",
    503: "The service is temporarily unavailable.",
}


def _request_id():
    return getattr(g, "request_id", None)


def _wants_json():
    # API routes are JSON; also default to JSON for /admin, /auth, /email, /features.
    p = request.path or ""
    if p.startswith(("/admin", "/auth", "/email", "/features", "/api")):
        return True
    accept = request.headers.get("Accept", "")
    return "application/json" in accept or "*/*" in accept


def _payload(status, message=None, code=None):
    return {
        "error": message or _SAFE_MESSAGE.get(status, "Request failed."),
        "code": code or _STATUS_CODE.get(status, "ERROR"),
        "request_id": _request_id(),
    }


def register_error_handlers(app):
    @app.errorhandler(HTTPException)
    def handle_http_exception(exc):
        status = exc.code or 500
        # werkzeug descriptions are safe (no internals); prefer them for 4xx so
        # intentional aborts keep their message, but fall back to a safe generic.
        message = exc.description if (400 <= status < 500 and exc.description) else _SAFE_MESSAGE.get(status)
        if status >= 500:
            logger.error("HTTP %s on %s %s (request_id=%s): %s",
                         status, request.method, request.path, _request_id(), exc)
        resp = jsonify(_payload(status, message, _STATUS_CODE.get(status)))
        resp.status_code = status
        return resp

    @app.errorhandler(Exception)
    def handle_uncaught_exception(exc):
        # Any non-HTTP exception → 500. Log the full detail server-side only.
        logger.exception("Unhandled exception on %s %s (request_id=%s)",
                         request.method, request.path, _request_id())
        resp = jsonify(_payload(500))
        resp.status_code = 500
        return resp
