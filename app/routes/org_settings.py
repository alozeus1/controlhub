"""
Organization-wide settings (feature 5).

GET is available to any authenticated user (branding, timezone, locale).
PUT requires the `manage_org_settings` permission.
"""
from flask import Blueprint, jsonify, request

from app.extensions import db
from app.models import OrgSettings
from app.utils.rbac import require_active_user
from app.permissions import require_elevated_permission
from app.utils.audit import log_action

org_settings_bp = Blueprint("org_settings", __name__)

VALID_LOCALES = None  # accept any well-formed short locale


@org_settings_bp.get("/org-settings")
@require_active_user
def get_org_settings():
    return jsonify(OrgSettings.get().to_dict())


@org_settings_bp.put("/org-settings")
@require_elevated_permission("manage_org_settings")
def update_org_settings():
    data = request.get_json() or {}
    s = OrgSettings.get()

    if "org_name" in data and str(data["org_name"]).strip():
        s.org_name = str(data["org_name"]).strip()[:150]
    if "logo_url" in data:
        s.logo_url = (data["logo_url"] or None)
    if "timezone" in data and str(data["timezone"]).strip():
        s.timezone = str(data["timezone"]).strip()[:64]
    if "locale" in data and str(data["locale"]).strip():
        s.locale = str(data["locale"]).strip()[:16]
    if "allowed_signup_domains" in data:
        domains = data["allowed_signup_domains"] or []
        if isinstance(domains, str):
            domains = [d.strip() for d in domains.split(",")]
        s.allowed_signup_domains = [d.lower().lstrip("@").strip() for d in domains if d and str(d).strip()]
    if "mfa_required" in data:
        s.mfa_required = bool(data["mfa_required"])
    if "mfa_required_roles" in data:
        roles = data["mfa_required_roles"] or []
        s.mfa_required_roles = [str(r) for r in roles]

    db.session.commit()
    log_action("org.settings.updated", actor=getattr(request, "current_user", None),
               target_type="org_settings", target_id=1,
               details={"fields": list(data.keys())})
    return jsonify(s.to_dict())
