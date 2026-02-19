from flask import Blueprint, request, jsonify
from app.extensions import db
from app.models import Runbook
from app.utils.rbac import require_role, require_active_user
import re

runbooks_bp = Blueprint("runbooks", __name__)

def _slugify(text):
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_-]+', '-', text)
    return text[:100]

def _unique_slug(base):
    slug = base
    i = 1
    while Runbook.query.filter_by(slug=slug).first():
        slug = f"{base}-{i}"
        i += 1
    return slug

@runbooks_bp.get("/runbooks")
@require_active_user
def list_runbooks():
    category = request.args.get("category")
    q_str = request.args.get("q", "")
    q = Runbook.query.filter_by(is_published=True)
    if category:
        q = q.filter_by(category=category)
    if q_str:
        q = q.filter(Runbook.title.ilike(f"%{q_str}%"))
    runbooks = q.order_by(Runbook.updated_at.desc()).all()
    # Return without full content for list view
    items = []
    for r in runbooks:
        d = r.to_dict()
        d["content_md"] = (d["content_md"] or "")[:200]  # preview only
        items.append(d)
    return jsonify({"items": items, "total": len(items)})

@runbooks_bp.get("/runbooks/categories")
@require_active_user
def list_categories():
    from sqlalchemy import func
    cats = db.session.query(Runbook.category, func.count(Runbook.id)).filter(
        Runbook.is_published==True, Runbook.category != None
    ).group_by(Runbook.category).all()
    return jsonify({"categories": [{"name": c, "count": n} for c, n in cats]})

@runbooks_bp.get("/runbooks/<int:runbook_id>")
@require_active_user
def get_runbook(runbook_id):
    r = Runbook.query.get_or_404(runbook_id)
    return jsonify(r.to_dict())

@runbooks_bp.post("/runbooks")
@require_active_user
def create_runbook():
    data = request.get_json() or {}
    if not data.get("title"):
        return jsonify({"error": "title is required"}), 400
    slug = _unique_slug(_slugify(data["title"]))
    r = Runbook(title=data["title"], slug=slug,
                content_md=data.get("content_md", ""),
                category=data.get("category"),
                tags=data.get("tags"),
                is_published=data.get("is_published", True),
                created_by_id=request.current_user.id,
                updated_by_id=request.current_user.id)
    db.session.add(r)
    db.session.commit()
    return jsonify(r.to_dict()), 201

@runbooks_bp.put("/runbooks/<int:runbook_id>")
@require_active_user
def update_runbook(runbook_id):
    r = Runbook.query.get_or_404(runbook_id)
    data = request.get_json() or {}
    for field in ("title","content_md","category","tags","is_published"):
        if field in data:
            setattr(r, field, data[field])
    r.updated_by_id = request.current_user.id
    db.session.commit()
    return jsonify(r.to_dict())

@runbooks_bp.delete("/runbooks/<int:runbook_id>")
@require_role("admin")
def delete_runbook(runbook_id):
    r = Runbook.query.get_or_404(runbook_id)
    db.session.delete(r)
    db.session.commit()
    return jsonify({"message": "Deleted"})
