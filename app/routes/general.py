from flask import Blueprint, render_template, jsonify, current_app

general_bp = Blueprint("general", __name__)

@general_bp.route("/")
def home():
    return render_template("index.html")

@general_bp.route("/healthz")
def healthz():
    # Liveness: the process is up and serving. No dependency checks.
    return jsonify({"status": "ok"}), 200


@general_bp.route("/readyz")
def readyz():
    # Readiness: verify critical dependencies (DB, Redis) before taking traffic.
    from app.extensions import db
    from sqlalchemy import text
    checks = {}
    ok = True
    try:
        db.session.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:
        checks["database"] = "error"
        current_app.logger.error("readyz DB check failed: %s", exc)
        ok = False
    redis_client = getattr(current_app, "_redis", None)
    if redis_client is not None:
        try:
            redis_client.ping()
            checks["redis"] = "ok"
        except Exception as exc:
            checks["redis"] = "error"
            current_app.logger.error("readyz Redis check failed: %s", exc)
            ok = False
    else:
        checks["redis"] = "not_configured"
    return jsonify({"status": "ok" if ok else "degraded", "checks": checks}), (200 if ok else 503)


@general_bp.route("/features")
def get_features():
    """Return enabled feature flags for the frontend."""
    return jsonify({
        "service_accounts": current_app.config.get("FEATURE_SERVICE_ACCOUNTS", False),
        "notifications": current_app.config.get("FEATURE_NOTIFICATIONS", False),
        "integrations": current_app.config.get("FEATURE_INTEGRATIONS", False),
        "assets": current_app.config.get("FEATURE_ASSETS", False),
        "people": current_app.config.get("FEATURE_PEOPLE", False),
        "internship_program": current_app.config.get("FEATURE_INTERNSHIP_PROGRAM", False),
        "agent_service": current_app.config.get("FEATURE_AGENT_SERVICE", False),
        "email_campaigns": current_app.config.get("FEATURE_EMAIL_CAMPAIGNS", False),
    })
