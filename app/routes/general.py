from flask import Blueprint, render_template, jsonify, current_app

general_bp = Blueprint("general", __name__)

@general_bp.route("/")
def home():
    return render_template("index.html")

@general_bp.route("/healthz")
def healthz():
    return jsonify({"status": "ok"}), 200


@general_bp.route("/features")
def get_features():
    """Return enabled feature flags for the frontend."""
    return jsonify({
        "service_accounts": current_app.config.get("FEATURE_SERVICE_ACCOUNTS", False),
        "notifications": current_app.config.get("FEATURE_NOTIFICATIONS", False),
        "integrations": current_app.config.get("FEATURE_INTEGRATIONS", False),
        "assets": current_app.config.get("FEATURE_ASSETS", False),
    })
