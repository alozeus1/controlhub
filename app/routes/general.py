from flask import Blueprint, render_template, jsonify, current_app
from app.auth.token_verifier import get_cognito_verifier

general_bp = Blueprint("general", __name__)

@general_bp.route("/")
def home():
    return render_template("index.html")

@general_bp.route("/healthz")
def healthz():
    auth_mode = current_app.config.get("AUTH_MODE", "hybrid")
    cognito_status = {
        "auth_mode": auth_mode,
    }

    if auth_mode == "local":
        cognito_status["readiness"] = "not_required"
    else:
        issuer = current_app.config.get("COGNITO_ISSUER")
        client_id = current_app.config.get("COGNITO_APP_CLIENT_ID")
        jwks_url = current_app.config.get("COGNITO_JWKS_URL")
        cognito_status.update({
            "issuer_configured": bool(issuer),
            "client_id_configured": bool(client_id),
            "jwks_url_configured": bool(jwks_url),
        })
        ready = bool(issuer and client_id and jwks_url)
        cognito_status["readiness"] = "ready" if ready else "misconfigured"

        if ready and current_app.config.get("COGNITO_HEALTHCHECK_JWKS", False):
            try:
                verifier = get_cognito_verifier()
                verifier._jwks_data()
                cognito_status["jwks_reachable"] = True
            except Exception:
                cognito_status["jwks_reachable"] = False
                cognito_status["readiness"] = "degraded"

    return jsonify({"status": "ok", "auth": cognito_status}), 200


@general_bp.route("/features")
def get_features():
    """Return enabled feature flags for the frontend."""
    return jsonify({
        "service_accounts": current_app.config.get("FEATURE_SERVICE_ACCOUNTS", False),
        "notifications": current_app.config.get("FEATURE_NOTIFICATIONS", False),
        "integrations": current_app.config.get("FEATURE_INTEGRATIONS", False),
        "assets": current_app.config.get("FEATURE_ASSETS", False),
    })
