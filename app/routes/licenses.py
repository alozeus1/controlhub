from flask import Blueprint, request, jsonify
from app.extensions import db
from app.models import License
from app.utils.rbac import require_role, require_active_user
from datetime import date

licenses_bp = Blueprint("licenses", __name__)

@licenses_bp.get("/licenses")
@require_active_user
def list_licenses():
    status = request.args.get("status")
    q = License.query
    if status:
        q = q.filter_by(status=status)
    licenses = q.order_by(License.renewal_date.asc()).all()
    return jsonify({"items": [l.to_dict() for l in licenses], "total": len(licenses)})

@licenses_bp.get("/licenses/stats")
@require_active_user
def license_stats():
    licenses = License.query.filter_by(status="active").all()
    total_monthly = sum(float(l.cost_monthly or 0) for l in licenses)
    expiring_soon = [l for l in licenses if l.days_until_renewal is not None and 0 <= l.days_until_renewal <= 30]
    return jsonify({
        "total": len(licenses),
        "total_monthly_cost": total_monthly,
        "total_annual_cost": total_monthly * 12,
        "expiring_soon": len(expiring_soon),
    })

@licenses_bp.post("/licenses")
@require_role("admin")
def create_license():
    data = request.get_json() or {}
    for f in ("vendor","product"):
        if not data.get(f):
            return jsonify({"error": f"{f} is required"}), 400
    l = License(
        vendor=data["vendor"], product=data["product"],
        license_type=data.get("license_type"),
        seats=data.get("seats"), seats_used=data.get("seats_used"),
        cost_monthly=data.get("cost_monthly"),
        renewal_date=date.fromisoformat(data["renewal_date"]) if data.get("renewal_date") else None,
        owner_id=data.get("owner_id"),
        notes=data.get("notes"), status=data.get("status", "active"),
        created_by_id=request.current_user.id,
    )
    db.session.add(l)
    db.session.commit()
    return jsonify(l.to_dict()), 201

@licenses_bp.put("/licenses/<int:license_id>")
@require_role("admin")
def update_license(license_id):
    l = License.query.get_or_404(license_id)
    data = request.get_json() or {}
    for field in ("vendor","product","license_type","seats","seats_used","cost_monthly","owner_id","notes","status"):
        if field in data:
            setattr(l, field, data[field])
    if "renewal_date" in data:
        l.renewal_date = date.fromisoformat(data["renewal_date"]) if data["renewal_date"] else None
    db.session.commit()
    return jsonify(l.to_dict())

@licenses_bp.delete("/licenses/<int:license_id>")
@require_role("admin")
def delete_license(license_id):
    l = License.query.get_or_404(license_id)
    db.session.delete(l)
    db.session.commit()
    return jsonify({"message": "Deleted"})
