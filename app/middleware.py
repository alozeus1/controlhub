import logging
import json
import time
import uuid
from flask import request, g


class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_record = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if hasattr(record, "request_id"):
            log_record["request_id"] = record.request_id
        if hasattr(record, "method"):
            log_record["method"] = record.method
        if hasattr(record, "path"):
            log_record["path"] = record.path
        if hasattr(record, "status_code"):
            log_record["status_code"] = record.status_code
        if hasattr(record, "duration_ms"):
            log_record["duration_ms"] = record.duration_ms
        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_record)


def setup_logging(app):
    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())

    app.logger.handlers = []
    app.logger.addHandler(handler)
    app.logger.setLevel(logging.INFO)

    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    logging.getLogger("gunicorn.error").handlers = []
    logging.getLogger("gunicorn.error").addHandler(handler)


def init_request_logging(app):
    setup_logging(app)

    @app.before_request
    def before_request():
        g.request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        g.start_time = time.time()

    @app.after_request
    def after_request(response):
        duration_ms = round((time.time() - g.start_time) * 1000, 2)
        response.headers["X-Request-ID"] = g.request_id

        if request.path != "/healthz":
            app.logger.info(
                "Request completed",
                extra={
                    "request_id": g.request_id,
                    "method": request.method,
                    "path": request.path,
                    "status_code": response.status_code,
                    "duration_ms": duration_ms,
                }
            )
        return response


class MethodOverrideMiddleware:
    """Unwrap POST requests carrying X-HTTP-Method-Override into their real
    method before routing.

    Some proxies, security tools, and browser extensions silently drop
    non-standard HTTP verbs (PATCH in particular) while passing GET/POST.
    The admin UI therefore tunnels PATCH/PUT as POST + override header; this
    middleware restores the intended method server-side. Native PATCH/PUT
    requests are unaffected.
    """

    ALLOWED_OVERRIDES = {"PATCH", "PUT", "DELETE"}

    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        if environ.get("REQUEST_METHOD") == "POST":
            override = environ.get("HTTP_X_HTTP_METHOD_OVERRIDE", "").upper()
            if override in self.ALLOWED_OVERRIDES:
                environ["controlhub.original_method"] = "POST"
                environ["REQUEST_METHOD"] = override
        return self.wsgi_app(environ, start_response)
