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

    app.register_blueprint(general_bp)
    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(ui_bp, url_prefix="/ui")

    return app
