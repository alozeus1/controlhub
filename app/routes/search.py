"""
Global search across key entities (feature 6).

Returns results grouped by category with a quick-jump link. Sensitive
categories (secrets, certificates) are only included for users whose role holds
the matching permission, so search never leaks entities a user can't manage.
"""
from flask import Blueprint, jsonify, request

from app.extensions import db, limiter
from app.utils.rbac import require_active_user
from app.permissions import has_permission

search_bp = Blueprint("search", __name__)

MAX_PER_CATEGORY = 6


def _like(term):
    return f"%{term.strip()}%"


@search_bp.get("/search")
@limiter.limit("60 per minute")
@require_active_user
def global_search():
    q = (request.args.get("q") or "").strip()
    if len(q) < 2:
        return jsonify({"query": q, "groups": []})
    user = request.current_user
    like = _like(q)
    groups = []

    # Users
    try:
        from app.models import User
        if has_permission(user, "manage_users"):
            rows = User.query.filter(User.email.ilike(like)).limit(MAX_PER_CATEGORY).all()
            if rows:
                groups.append({"category": "Users", "icon": "users", "items": [
                    {"label": u.email, "sublabel": u.role, "link": "/ui/users"} for u in rows]})
    except Exception:
        pass

    # Assets
    try:
        from app.models import Asset
        rows = Asset.query.filter(
            db.or_(Asset.name.ilike(like), Asset.asset_tag.ilike(like))
        ).limit(MAX_PER_CATEGORY).all()
        if rows:
            groups.append({"category": "Assets", "icon": "monitor", "items": [
                {"label": a.name, "sublabel": getattr(a, "asset_tag", None),
                 "link": f"/ui/assets/{a.id}"} for a in rows]})
    except Exception:
        pass

    # Secrets (permission-gated)
    try:
        from app.models import Secret
        if has_permission(user, "manage_secrets"):
            rows = Secret.query.filter(Secret.name.ilike(like)).limit(MAX_PER_CATEGORY).all()
            if rows:
                groups.append({"category": "Secrets", "icon": "lock", "items": [
                    {"label": s.name, "sublabel": getattr(s, "environment", None),
                     "link": "/ui/secrets"} for s in rows]})
    except Exception:
        pass

    # Certificates (permission-gated)
    try:
        from app.models import Certificate
        if has_permission(user, "manage_certificates"):
            rows = Certificate.query.filter(
                db.or_(Certificate.name.ilike(like), Certificate.domain.ilike(like))
            ).limit(MAX_PER_CATEGORY).all()
            if rows:
                groups.append({"category": "Certificates", "icon": "shield", "items": [
                    {"label": c.name, "sublabel": getattr(c, "domain", None),
                     "link": "/ui/certificates"} for c in rows]})
    except Exception:
        pass

    # Deployments
    try:
        from app.models import Deployment
        rows = Deployment.query.filter(
            db.or_(Deployment.service.ilike(like), Deployment.version.ilike(like))
        ).limit(MAX_PER_CATEGORY).all()
        if rows:
            groups.append({"category": "Deployments", "icon": "cloud", "items": [
                {"label": getattr(d, "service", f"Deployment #{d.id}"),
                 "sublabel": getattr(d, "version", None), "link": "/ui/deployments"} for d in rows]})
    except Exception:
        pass

    # Runbooks
    try:
        from app.models import Runbook
        rows = Runbook.query.filter(Runbook.title.ilike(like)).limit(MAX_PER_CATEGORY).all()
        if rows:
            groups.append({"category": "Runbooks", "icon": "document", "items": [
                {"label": r.title, "sublabel": getattr(r, "category", None),
                 "link": f"/ui/runbooks/{r.id}"} for r in rows]})
    except Exception:
        pass

    total = sum(len(g["items"]) for g in groups)
    return jsonify({"query": q, "total": total, "groups": groups})
