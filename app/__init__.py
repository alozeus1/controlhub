from flask import Flask
from flask_cors import CORS
from config import get_config
from app.routes.ui import ui_bp
from app.extensions import db, migrate, jwt, mail, limiter
from app.middleware import init_request_logging
from app.utils.security_headers import init_security_headers
import redis as redis_lib


def create_app():
    app = Flask(__name__)
    cfg = get_config()
    app.config.from_object(cfg)

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

    # JWT token blocklist (Redis-backed)
    _redis = None
    try:
        _redis = redis_lib.from_url(app.config.get("REDIS_URL", "redis://localhost:6379/0"))
    except Exception:
        pass

    @jwt.token_in_blocklist_loader
    def check_if_token_revoked(jwt_header, jwt_payload):
        if _redis is None:
            return False
        jti = jwt_payload.get("jti")
        return _redis.get(f"blocklist:{jti}") is not None

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
    app.register_blueprint(ui_bp, url_prefix="/ui")

    return app
