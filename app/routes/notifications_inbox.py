"""
Personal notification inbox endpoints (the in-app bell).

Distinct from app/routes/notifications.py, which manages the ops-facing
NotificationChannel/AlertRule/AlertEvent system. Every endpoint here is
scoped to the calling user's own notifications only.
"""
from flask import Blueprint, jsonify, request

from app.extensions import db
from app.models import Notification
from app.utils.rbac import require_active_user

notifications_inbox_bp = Blueprint("notifications_inbox", __name__)


@notifications_inbox_bp.get("/notifications/inbox")
@require_active_user
def list_inbox():
    actor = request.current_user
    unread_only = request.args.get("unread_only", "false").lower() == "true"
    page = request.args.get("page", 1, type=int)
    page_size = min(request.args.get("page_size", 20, type=int), 100)

    query = Notification.query.filter_by(user_id=actor.id)
    if unread_only:
        query = query.filter_by(is_read=False)
    query = query.order_by(Notification.created_at.desc())

    pagination = query.paginate(page=page, per_page=page_size, error_out=False)
    unread_count = Notification.query.filter_by(user_id=actor.id, is_read=False).count()

    return jsonify({
        "items": [n.to_dict() for n in pagination.items],
        "total": pagination.total,
        "page": pagination.page,
        "page_size": pagination.per_page,
        "pages": pagination.pages,
        "unread_count": unread_count,
    })


@notifications_inbox_bp.post("/notifications/inbox/<int:notification_id>/read")
@require_active_user
def mark_read(notification_id):
    actor = request.current_user
    notification = Notification.query.filter_by(id=notification_id, user_id=actor.id).first_or_404()
    notification.is_read = True
    db.session.commit()
    return jsonify({"message": "Marked as read", "notification": notification.to_dict()})


@notifications_inbox_bp.post("/notifications/inbox/read-all")
@require_active_user
def mark_all_read():
    actor = request.current_user
    Notification.query.filter_by(user_id=actor.id, is_read=False).update({"is_read": True})
    db.session.commit()
    return jsonify({"message": "All notifications marked as read"})


@notifications_inbox_bp.delete("/notifications/inbox/<int:notification_id>")
@require_active_user
def delete_notification(notification_id):
    actor = request.current_user
    notification = Notification.query.filter_by(id=notification_id, user_id=actor.id).first_or_404()
    db.session.delete(notification)
    db.session.commit()
    return jsonify({"message": "Notification deleted"})
