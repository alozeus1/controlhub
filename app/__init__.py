from flask import Flask, jsonify
from flask_cors import CORS
from config import get_config
from app.routes.ui import ui_bp
from app.extensions import db, migrate, jwt, mail, limiter
from app.middleware import init_request_logging, MethodOverrideMiddleware
from app.utils.security_headers import init_security_headers
import redis as redis_lib


def create_app():
    app = Flask(__name__)
    cfg = get_config()
    app.config.from_object(cfg)

    # Restore tunneled PATCH/PUT/DELETE (sent as POST + X-HTTP-Method-Override)
    # before routing — some client-side proxies/extensions drop those verbs.
    app.wsgi_app = MethodOverrideMiddleware(app.wsgi_app)

    # CORS — read allowed origins from config (comma-separated env var)
    origins = [o.strip() for o in app.config.get("CORS_ORIGINS", "").split(",") if o.strip()]
    CORS(app, origins=origins, supports_credentials=True)

    # Extensions
    init_request_logging(app)

    # Limiter — wire storage URI from config
    limiter._storage_uri = app.config.get("RATELIMIT_STORAGE_URL")
    limiter.init_app(app)

    jwt.init_app(app)
    db.init_app(app)
    migrate.init_app(app, db)
    mail.init_app(app)

    # Security headers
    init_security_headers(app)

    # Centralized JSON error handling (consistent, production-safe responses)
    from app.error_handlers import register_error_handlers
    register_error_handlers(app)

    # JWT token blocklist (Redis-backed)
    _redis = None
    try:
        _redis = redis_lib.from_url(app.config.get("REDIS_URL", "redis://localhost:6379/0"))
    except Exception:
        pass

    @jwt.token_in_blocklist_loader
    def check_if_token_revoked(jwt_header, jwt_payload):
        # Read the live redis handle + policy at call time so behavior is
        # testable and operators can flip the policy without a code change.
        from flask import current_app, g
        redis_client = getattr(current_app, "_redis", None)
        fail_open = current_app.config.get("JWT_FAIL_OPEN", False)
        jti = jwt_payload.get("jti")

        if redis_client is None:
            current_app.logger.error(
                "JWT revocation store unavailable (no redis); failing %s",
                "OPEN" if fail_open else "CLOSED")
            return not fail_open  # closed => treat as revoked (deny)
        try:
            return redis_client.get(f"blocklist:{jti}") is not None
        except Exception as exc:
            # Cannot verify revocation state. Fail CLOSED by default so revoked
            # or compromised tokens cannot be used during a Redis outage.
            current_app.logger.error(
                "JWT revocation check failed (request_id=%s): %s; failing %s",
                getattr(g, "request_id", None), exc, "OPEN" if fail_open else "CLOSED")
            return not fail_open

    @jwt.revoked_token_loader
    def _revoked_token_response(jwt_header, jwt_payload):
        from flask import g
        return jsonify({
            "error": "Your session is no longer valid. Please sign in again.",
            "code": "TOKEN_REVOKED",
            "request_id": getattr(g, "request_id", None),
        }), 401

    # Expose redis on app for use in routes
    app._redis = _redis

    from app.routes.general import general_bp
    from app.routes.auth import auth_bp
    from app.routes.admin import admin_bp
    from app.routes.uploads import uploads_bp
    from app.routes.governance import governance_bp
    from app.routes.service_accounts import service_accounts_bp
    from app.routes.notifications import notifications_bp
    from app.routes.integrations import integrations_bp
    from app.routes.assets import assets_bp
    from app.routes.secrets import secrets_bp
    from app.routes.env_configs import env_configs_bp
    from app.routes.incidents import incidents_bp
    from app.routes.runbooks import runbooks_bp
    from app.routes.deployments import deployments_bp
    from app.routes.certificates import certificates_bp
    from app.routes.feature_flags import feature_flags_bp
    from app.routes.licenses import licenses_bp
    from app.routes.workflows import workflows_bp
    from app.routes.costs import costs_bp
    from app.routes.people import people_bp
    from app.routes.internship import internship_bp
    from app.routes.performance import performance_bp
    from app.routes.notifications_inbox import notifications_inbox_bp
    from app.routes.agent_service import agent_bp
    from app.routes.campaigns import campaigns_bp, public_email_bp
    from app.routes.roles import roles_bp
    from app.routes.org_settings import org_settings_bp
    from app.routes.mfa import mfa_bp
    from app.routes.sso import sso_bp, sso_public_bp
    from app.routes.search import search_bp

    app.register_blueprint(general_bp)
    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(uploads_bp, url_prefix="/admin")
    app.register_blueprint(governance_bp, url_prefix="/admin")
    app.register_blueprint(service_accounts_bp, url_prefix="/admin")
    app.register_blueprint(notifications_bp, url_prefix="/admin")
    app.register_blueprint(integrations_bp, url_prefix="/admin")
    app.register_blueprint(assets_bp, url_prefix="/admin")
    app.register_blueprint(secrets_bp, url_prefix="/admin")
    app.register_blueprint(env_configs_bp, url_prefix="/admin")
    app.register_blueprint(incidents_bp, url_prefix="/admin")
    app.register_blueprint(runbooks_bp, url_prefix="/admin")
    app.register_blueprint(deployments_bp, url_prefix="/admin")
    app.register_blueprint(certificates_bp, url_prefix="/admin")
    app.register_blueprint(feature_flags_bp, url_prefix="/admin")
    app.register_blueprint(licenses_bp, url_prefix="/admin")
    app.register_blueprint(workflows_bp, url_prefix="/admin")
    app.register_blueprint(costs_bp, url_prefix="/admin")
    app.register_blueprint(people_bp, url_prefix="/admin")
    app.register_blueprint(internship_bp, url_prefix="/admin")
    app.register_blueprint(performance_bp, url_prefix="/admin")
    app.register_blueprint(notifications_inbox_bp, url_prefix="/admin")
    app.register_blueprint(agent_bp, url_prefix="/admin")
    app.register_blueprint(campaigns_bp, url_prefix="/admin")
    # Public (no /admin prefix, no auth): SNS webhook + one-click unsubscribe
    app.register_blueprint(public_email_bp)
    # Admin platform features
    app.register_blueprint(roles_bp, url_prefix="/admin")
    app.register_blueprint(org_settings_bp, url_prefix="/admin")
    app.register_blueprint(sso_bp, url_prefix="/admin")
    app.register_blueprint(search_bp, url_prefix="/admin")
    app.register_blueprint(mfa_bp, url_prefix="/auth")
    app.register_blueprint(sso_public_bp, url_prefix="/auth")
    app.register_blueprint(ui_bp, url_prefix="/ui")

    return app
