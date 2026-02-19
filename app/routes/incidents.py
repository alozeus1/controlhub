from flask import Blueprint, request, jsonify
from app.extensions import db
from app.models import Incident, IncidentUpdate
from app.utils.rbac import require_role, require_active_user
from datetime import datetime

incidents_bp = Blueprint("incidents", __name__)

@incidents_bp.get("/incidents")
@require_active_user
def list_incidents():
    status = request.args.get("status")
    severity = request.args.get("severity")
    q = Incident.query
    if status:
        q = q.filter_by(status=status)
    if severity:
        q = q.filter_by(severity=severity)
    incidents = q.order_by(Incident.created_at.desc()).all()
    return jsonify({"items": [i.to_dict() for i in incidents], "total": len(incidents)})

@incidents_bp.get("/incidents/<int:incident_id>")
@require_active_user
def get_incident(incident_id):
    inc = Incident.query.get_or_404(incident_id)
    d = inc.to_dict()
    d["updates"] = [u.to_dict() for u in sorted(inc.updates, key=lambda x: x.created_at)]
    return jsonify(d)

@incidents_bp.post("/incidents")
@require_active_user
def create_incident():
    data = request.get_json() or {}
    if not data.get("title"):
        return jsonify({"error": "title is required"}), 400
    inc = Incident(
        title=data["title"], description=data.get("description"),
        severity=data.get("severity", "p3"),
        affected_services=data.get("affected_services", []),
        commander_id=data.get("commander_id"),
        created_by_id=request.current_user.id,
    )
    db.session.add(inc)
    db.session.flush()
    # Auto-post first update
    upd = IncidentUpdate(incident_id=inc.id, message="Incident created.",
                         posted_by_id=request.current_user.id)
    db.session.add(upd)
    db.session.commit()
    return jsonify(inc.to_dict()), 201

@incidents_bp.patch("/incidents/<int:incident_id>")
@require_active_user
def update_incident(incident_id):
    inc = Incident.query.get_or_404(incident_id)
    data = request.get_json() or {}
    old_status = inc.status
    for field in ("title","description","severity","affected_services","commander_id","root_cause"):
        if field in data:
            setattr(inc, field, data[field])
    new_status = data.get("status")
    if new_status and new_status != old_status:
        inc.status = new_status
        if new_status in ("resolved", "closed") and not inc.resolved_at:
            inc.resolved_at = datetime.utcnow()
        upd = IncidentUpdate(incident_id=inc.id,
                             message=f"Status changed to {new_status}.",
                             status_change=new_status,
                             posted_by_id=request.current_user.id)
        db.session.add(upd)
    db.session.commit()
    return jsonify(inc.to_dict())

@incidents_bp.post("/incidents/<int:incident_id>/updates")
@require_active_user
def post_update(incident_id):
    inc = Incident.query.get_or_404(incident_id)
    data = request.get_json() or {}
    if not data.get("message"):
        return jsonify({"error": "message is required"}), 400
    upd = IncidentUpdate(incident_id=inc.id, message=data["message"],
                         posted_by_id=request.current_user.id)
    db.session.add(upd)
    db.session.commit()
    return jsonify(upd.to_dict()), 201

@incidents_bp.get("/incidents/stats")
@require_active_user
def incident_stats():
    from sqlalchemy import func
    total = Incident.query.count()
    open_count = Incident.query.filter_by(status="open").count()
    by_severity = db.session.query(Incident.severity, func.count(Incident.id)).group_by(Incident.severity).all()
    return jsonify({
        "total": total, "open": open_count,
        "by_severity": {s: c for s, c in by_severity}
    })
