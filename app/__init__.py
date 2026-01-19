from flask import Flask
from config import get_config
from app.routes.ui import ui_bp
from app.extensions import db, migrate
from flask_jwt_extended import JWTManager

jwt = JWTManager()

def create_app():
    app = Flask(__name__)
    app.config.from_object(get_config())

    app.secret_key = "supersecret"  # add this for session login token

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
