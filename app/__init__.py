from flask import Flask
from flask_cors import CORS
from config import get_config
from app.routes.ui import ui_bp
from app.extensions import db, migrate
from app.middleware import init_request_logging
from flask_jwt_extended import JWTManager

jwt = JWTManager()

def create_app():
    app = Flask(__name__)
    app.config.from_object(get_config())

    app.secret_key = "supersecret"  # add this for session login token

    # CORS for local development (UI on :3001, API on :9000)
    CORS(app, origins=["http://localhost:3001", "http://127.0.0.1:3001"])

    init_request_logging(app)
    jwt.init_app(app)
    db.init_app(app)
    migrate.init_app(app, db)

    from app.routes.general import general_bp
    from app.routes.auth import auth_bp
    from app.routes.admin import admin_bp
    from app.routes.uploads import uploads_bp
    from app.routes.governance import governance_bp
    from app.routes.service_accounts import service_accounts_bp
    from app.routes.notifications import notifications_bp
    from app.routes.integrations import integrations_bp
    from app.routes.assets import assets_bp

    app.register_blueprint(general_bp)
    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(uploads_bp, url_prefix="/admin")  # Upload routes under /admin
    app.register_blueprint(governance_bp, url_prefix="/admin")  # Governance routes under /admin
    app.register_blueprint(service_accounts_bp, url_prefix="/admin")  # Service accounts under /admin
    app.register_blueprint(notifications_bp, url_prefix="/admin")  # Notifications under /admin
    app.register_blueprint(integrations_bp, url_prefix="/admin")  # Integrations under /admin
    app.register_blueprint(assets_bp, url_prefix="/admin")  # Assets under /admin
    app.register_blueprint(ui_bp, url_prefix="/ui")

    return app
