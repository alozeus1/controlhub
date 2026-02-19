from flask import Blueprint, request, jsonify
from app.extensions import db
from app.models import CostEntry, BudgetRequest
from app.utils.rbac import require_role, require_active_user
from datetime import datetime

costs_bp = Blueprint("costs", __name__)

@costs_bp.get("/costs")
@require_active_user
def list_costs():
    period = request.args.get("period")
    team = request.args.get("team")
    q = CostEntry.query
    if period:
        q = q.filter_by(period=period)
    if team:
        q = q.filter_by(team=team)
    entries = q.order_by(CostEntry.period.desc(), CostEntry.amount.desc()).all()
    return jsonify({"items": [e.to_dict() for e in entries], "total": len(entries)})

@costs_bp.get("/costs/summary")
@require_active_user
def cost_summary():
    from sqlalchemy import func
    by_period = db.session.query(CostEntry.period, func.sum(CostEntry.amount)).group_by(CostEntry.period).order_by(CostEntry.period.desc()).limit(12).all()
    by_team = db.session.query(CostEntry.team, func.sum(CostEntry.amount)).group_by(CostEntry.team).all()
    by_provider = db.session.query(CostEntry.cloud_provider, func.sum(CostEntry.amount)).group_by(CostEntry.cloud_provider).all()
    return jsonify({
        "by_period": [{"period": p, "total": float(t)} for p, t in by_period],
        "by_team": [{"team": t or "Unassigned", "total": float(a)} for t, a in by_team],
        "by_provider": [{"provider": p, "total": float(a)} for p, a in by_provider],
    })

@costs_bp.post("/costs")
@require_role("admin")
def create_cost_entry():
    data = request.get_json() or {}
    for f in ("cloud_provider","service_name","amount","period"):
        if not data.get(f) and data.get(f) != 0:
            return jsonify({"error": f"{f} is required"}), 400
    e = CostEntry(cloud_provider=data["cloud_provider"], service_name=data["service_name"],
                  team=data.get("team"), project=data.get("project"),
                  amount=data["amount"], currency=data.get("currency","USD"),
                  period=data["period"], notes=data.get("notes"),
                  created_by_id=request.current_user.id)
    db.session.add(e)
    db.session.commit()
    return jsonify(e.to_dict()), 201

@costs_bp.delete("/costs/<int:entry_id>")
@require_role("admin")
def delete_cost_entry(entry_id):
    e = CostEntry.query.get_or_404(entry_id)
    db.session.delete(e)
    db.session.commit()
    return jsonify({"message": "Deleted"})

@costs_bp.get("/costs/budget-requests")
@require_active_user
def list_budget_requests():
    status = request.args.get("status")
    q = BudgetRequest.query
    if status:
        q = q.filter_by(status=status)
    reqs = q.order_by(BudgetRequest.created_at.desc()).all()
    return jsonify({"items": [r.to_dict() for r in reqs], "total": len(reqs)})

@costs_bp.post("/costs/budget-requests")
@require_active_user
def create_budget_request():
    data = request.get_json() or {}
    if not data.get("title") or not data.get("amount_requested"):
        return jsonify({"error": "title and amount_requested are required"}), 400
    r = BudgetRequest(title=data["title"], team=data.get("team"), project=data.get("project"),
                      amount_requested=data["amount_requested"],
                      currency=data.get("currency","USD"),
                      justification=data.get("justification"),
                      requested_by_id=request.current_user.id)
    db.session.add(r)
    db.session.commit()
    return jsonify(r.to_dict()), 201

@costs_bp.patch("/costs/budget-requests/<int:req_id>")
@require_role("admin")
def review_budget_request(req_id):
    r = BudgetRequest.query.get_or_404(req_id)
    data = request.get_json() or {}
    status = data.get("status")
    if status not in ("approved","rejected"):
        return jsonify({"error": "status must be approved or rejected"}), 400
    r.status = status
    r.reviewed_by_id = request.current_user.id
    r.review_notes = data.get("review_notes")
    r.reviewed_at = datetime.utcnow()
    db.session.commit()
    return jsonify(r.to_dict())
