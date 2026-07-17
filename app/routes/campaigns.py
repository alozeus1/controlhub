"""
Email Campaigns routes.

Feature-flagged: FEATURE_EMAIL_CAMPAIGNS.
Auth: uses require_scope — humans authorize by role (viewer/admin), and
service-account API keys authorize by scope (email:read / email:write /
email:send). API keys are NEVER granted human roles. Two endpoints are
intentionally PUBLIC:
  - POST /email/webhooks/ses   (SNS-signed; verified in-handler)
  - GET  /email/unsubscribe/<token>  (one-click unsubscribe compliance)
"""
import json
import logging
from datetime import datetime

from flask import Blueprint, jsonify, request, current_app

from app.extensions import db, limiter
from app.utils.rbac import require_scope
from app.models import (
    Subscriber, EmailList, ListMembership,
    Campaign, CampaignSend, Suppression, EmailEvent, EmailSettings,
)
from app.services.campaigns import (
    SubscriberService, ListService, SuppressionService, CampaignService,
    is_valid_email, send_transactional,
)
from app.services import email_ses
from app.services.html_sanitizer import sanitize_email_html
from app.utils.audit import log_action

logger = logging.getLogger(__name__)

campaigns_bp = Blueprint("campaigns", __name__)
public_email_bp = Blueprint("public_email", __name__)


def _feature_guard():
    if not current_app.config.get("FEATURE_EMAIL_CAMPAIGNS", False):
        return jsonify({"error": "Email campaigns feature is not enabled",
                        "code": "FEATURE_DISABLED"}), 403
    return None


def _paginate(query, default_size=25):
    page = request.args.get("page", 1, type=int)
    size = min(request.args.get("page_size", default_size, type=int), 200)
    total = query.count()
    items = query.limit(size).offset((page - 1) * size).all()
    return items, {"page": page, "page_size": size, "total": total}


# ══════════════════════════════════════════════════════════════════════════════
# SUBSCRIBERS
# ══════════════════════════════════════════════════════════════════════════════

@campaigns_bp.get("/email/subscribers")
@require_scope("email:read", also_role="viewer")
def list_subscribers():
    guard = _feature_guard()
    if guard:
        return guard
    q = Subscriber.query
    search = request.args.get("search")
    status = request.args.get("status")
    if search:
        like = f"%{search.strip()}%"
        q = q.filter(db.or_(Subscriber.email.ilike(like), Subscriber.name.ilike(like)))
    if status:
        q = q.filter(Subscriber.status == status)
    q = q.order_by(Subscriber.created_at.desc())
    items, meta = _paginate(q)
    return jsonify({"subscribers": [s.to_dict(include_lists=True) for s in items], **meta})


@campaigns_bp.post("/email/subscribers")
@require_scope("email:write", also_role="admin")
def create_subscriber():
    guard = _feature_guard()
    if guard:
        return guard
    data = request.get_json() or {}
    try:
        sub, created = SubscriberService.upsert(
            email=data.get("email"),
            name=data.get("name"),
            attributes=data.get("attributes"),
            status=data.get("status", "subscribed"),
            consent_source=data.get("consent_source", "manual"),
            consent_ip=request.remote_addr,
            actor=getattr(request, "current_user", None),
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    for list_id in data.get("list_ids", []):
        ListService.add_member(list_id, sub.id)
    return jsonify(sub.to_dict(include_lists=True)), (201 if created else 200)


@campaigns_bp.patch("/email/subscribers/<int:sub_id>")
@require_scope("email:write", also_role="admin")
def update_subscriber(sub_id):
    guard = _feature_guard()
    if guard:
        return guard
    sub = Subscriber.query.get(sub_id)
    if not sub:
        return jsonify({"error": "Subscriber not found"}), 404
    data = request.get_json() or {}
    if "name" in data:
        sub.name = data["name"]
    if "attributes" in data:
        sub.attributes = data["attributes"]
    if "status" in data and data["status"] in ("subscribed", "unsubscribed", "pending"):
        sub.status = data["status"]
    db.session.commit()
    return jsonify(sub.to_dict(include_lists=True))


@campaigns_bp.delete("/email/subscribers/<int:sub_id>")
@require_scope("email:write", also_role="admin")
def delete_subscriber(sub_id):
    guard = _feature_guard()
    if guard:
        return guard
    sub = Subscriber.query.get(sub_id)
    if not sub:
        return jsonify({"error": "Subscriber not found"}), 404
    ListMembership.query.filter_by(subscriber_id=sub_id).delete()
    email = sub.email
    db.session.delete(sub)
    db.session.commit()
    log_action("email.subscriber.deleted", actor=getattr(request, "current_user", None),
               target_type="subscriber", target_id=sub_id, target_label=email)
    return jsonify({"deleted": True})


@campaigns_bp.post("/email/subscribers/import")
@require_scope("email:write", also_role="admin")
def import_subscribers():
    guard = _feature_guard()
    if guard:
        return guard
    data = request.get_json() or {}
    rows = data.get("rows")
    if not isinstance(rows, list) or not rows:
        return jsonify({"error": "Provide 'rows': a non-empty list of {email, name, ...}"}), 400
    summary = SubscriberService.bulk_import(rows, actor=getattr(request, "current_user", None))
    list_id = data.get("list_id")
    if list_id:
        for row in rows:
            email = (row.get("email") or "").strip().lower()
            sub = Subscriber.query.filter_by(email=email).first()
            if sub:
                ListService.add_member(list_id, sub.id)
    return jsonify(summary)


# ══════════════════════════════════════════════════════════════════════════════
# LISTS
# ══════════════════════════════════════════════════════════════════════════════

@campaigns_bp.get("/email/lists")
@require_scope("email:read", also_role="viewer")
def list_lists():
    guard = _feature_guard()
    if guard:
        return guard
    lists = EmailList.query.order_by(EmailList.created_at.desc()).all()
    return jsonify({"lists": [lst.to_dict() for lst in lists]})


@campaigns_bp.post("/email/lists")
@require_scope("email:write", also_role="admin")
def create_list():
    guard = _feature_guard()
    if guard:
        return guard
    data = request.get_json() or {}
    if not data.get("name"):
        return jsonify({"error": "name is required"}), 400
    lst = EmailList(
        name=data["name"],
        description=data.get("description"),
        created_by_id=getattr(getattr(request, "current_user", None), "id", None),
    )
    db.session.add(lst)
    db.session.commit()
    log_action("email.list.created", actor=getattr(request, "current_user", None),
               target_type="email_list", target_id=lst.id, target_label=lst.name)
    return jsonify(lst.to_dict()), 201


@campaigns_bp.patch("/email/lists/<int:list_id>")
@require_scope("email:write", also_role="admin")
def update_list(list_id):
    guard = _feature_guard()
    if guard:
        return guard
    lst = EmailList.query.get(list_id)
    if not lst:
        return jsonify({"error": "List not found"}), 404
    data = request.get_json() or {}
    if "name" in data and str(data["name"]).strip():
        lst.name = str(data["name"]).strip()
    if "description" in data:
        lst.description = data["description"]
    db.session.commit()
    return jsonify(lst.to_dict())


@campaigns_bp.delete("/email/lists/<int:list_id>")
@require_scope("email:write", also_role="admin")
def delete_list(list_id):
    guard = _feature_guard()
    if guard:
        return guard
    lst = EmailList.query.get(list_id)
    if not lst:
        return jsonify({"error": "List not found"}), 404
    name = lst.name
    db.session.delete(lst)  # cascade removes memberships
    db.session.commit()
    log_action("email.list.deleted", actor=getattr(request, "current_user", None),
               target_type="email_list", target_id=list_id, target_label=name)
    return jsonify({"deleted": True})


@campaigns_bp.get("/email/lists/<int:list_id>/members")
@require_scope("email:read", also_role="viewer")
def list_members(list_id):
    guard = _feature_guard()
    if guard:
        return guard
    q = (db.session.query(Subscriber)
         .join(ListMembership, ListMembership.subscriber_id == Subscriber.id)
         .filter(ListMembership.list_id == list_id)
         .order_by(Subscriber.created_at.desc()))
    items, meta = _paginate(q)
    return jsonify({"members": [s.to_dict() for s in items], **meta})


@campaigns_bp.post("/email/lists/<int:list_id>/members")
@require_scope("email:write", also_role="admin")
def add_list_members(list_id):
    guard = _feature_guard()
    if guard:
        return guard
    if not EmailList.query.get(list_id):
        return jsonify({"error": "List not found"}), 404
    data = request.get_json() or {}
    ids = data.get("subscriber_ids", [])
    added = 0
    for sid in ids:
        _, created = ListService.add_member(list_id, sid)
        if created:
            added += 1
    return jsonify({"added": added, "requested": len(ids)})


@campaigns_bp.delete("/email/lists/<int:list_id>/members/<int:sub_id>")
@require_scope("email:write", also_role="admin")
def remove_list_member(list_id, sub_id):
    guard = _feature_guard()
    if guard:
        return guard
    ListService.remove_member(list_id, sub_id)
    return jsonify({"removed": True})


# ══════════════════════════════════════════════════════════════════════════════
# CAMPAIGNS
# ══════════════════════════════════════════════════════════════════════════════

@campaigns_bp.get("/email/campaigns")
@require_scope("email:read", also_role="viewer")
def list_campaigns():
    guard = _feature_guard()
    if guard:
        return guard
    q = Campaign.query.order_by(Campaign.created_at.desc())
    items, meta = _paginate(q)
    return jsonify({"campaigns": [c.to_dict() for c in items], **meta})


@campaigns_bp.get("/email/campaigns/<int:cid>")
@require_scope("email:read", also_role="viewer")
def get_campaign(cid):
    guard = _feature_guard()
    if guard:
        return guard
    c = Campaign.query.get(cid)
    if not c:
        return jsonify({"error": "Campaign not found"}), 404
    return jsonify(c.to_dict())


@campaigns_bp.post("/email/campaigns")
@require_scope("email:write", also_role="admin")
def create_campaign():
    guard = _feature_guard()
    if guard:
        return guard
    data = request.get_json() or {}
    if not data.get("name") or not data.get("subject"):
        return jsonify({"error": "name and subject are required"}), 400
    c = Campaign(
        name=data["name"],
        subject=data["subject"],
        from_name=data.get("from_name"),
        from_address=data.get("from_address"),
        reply_to=data.get("reply_to"),
        html=sanitize_email_html(data.get("html")),
        template_id=data.get("template_id"),
        target_list_id=data.get("target_list_id"),
        created_by_id=getattr(getattr(request, "current_user", None), "id", None),
    )
    db.session.add(c)
    db.session.commit()
    log_action("email.campaign.created", actor=getattr(request, "current_user", None),
               target_type="campaign", target_id=c.id, target_label=c.name)
    return jsonify(c.to_dict()), 201


@campaigns_bp.patch("/email/campaigns/<int:cid>")
@require_scope("email:write", also_role="admin")
def update_campaign(cid):
    guard = _feature_guard()
    if guard:
        return guard
    c = Campaign.query.get(cid)
    if not c:
        return jsonify({"error": "Campaign not found"}), 404
    if c.status not in ("draft", "scheduled"):
        return jsonify({"error": f"Cannot edit a campaign in status '{c.status}'"}), 409
    data = request.get_json() or {}
    for field in ("name", "subject", "from_name", "from_address", "reply_to",
                  "html", "template_id", "target_list_id"):
        if field in data:
            setattr(c, field, sanitize_email_html(data[field]) if field == "html" else data[field])
    db.session.commit()
    return jsonify(c.to_dict())


@campaigns_bp.post("/email/campaigns/<int:cid>/test")
@limiter.limit("10 per minute")
@require_scope("email:send", also_role="admin")
def send_test(cid):
    """Send a one-off test to a supplied address (does not touch counters)."""
    guard = _feature_guard()
    if guard:
        return guard
    c = Campaign.query.get(cid)
    if not c:
        return jsonify({"error": "Campaign not found"}), 404
    data = request.get_json() or {}
    to = (data.get("email") or "").strip().lower()
    if not is_valid_email(to):
        return jsonify({"error": "Valid 'email' required"}), 400
    result = email_ses.send_email(
        to_address=to,
        subject=f"[TEST] {c.subject}",
        html_body=(c.html or "<p>(empty)</p>"),
        from_address=c.from_address or email_ses.get_ses_config()["from_address"],
        from_name=c.from_name,
        reply_to=c.reply_to,
    )
    if result.ok:
        return jsonify({"sent": True, "message_id": result.message_id})
    return jsonify({"sent": False, "error": result.error}), 502


@campaigns_bp.post("/email/campaigns/<int:cid>/send")
@limiter.limit("30 per hour")
@require_scope("email:send", also_role="admin")
def send_campaign(cid):
    guard = _feature_guard()
    if guard:
        return guard
    c = Campaign.query.get(cid)
    if not c:
        return jsonify({"error": "Campaign not found"}), 404
    try:
        result = CampaignService.enqueue_send(c, actor=getattr(request, "current_user", None))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 409
    return jsonify({"status": c.status, **result})


@campaigns_bp.post("/email/campaigns/<int:cid>/schedule")
@require_scope("email:send", also_role="admin")
def schedule_campaign(cid):
    """
    Records a schedule time and marks 'scheduled'. Actual firing is owned by
    n8n (which calls /send at the scheduled time) — keeps orchestration external.
    """
    guard = _feature_guard()
    if guard:
        return guard
    c = Campaign.query.get(cid)
    if not c:
        return jsonify({"error": "Campaign not found"}), 404
    data = request.get_json() or {}
    when = data.get("scheduled_at")
    if not when:
        return jsonify({"error": "scheduled_at (ISO8601) required"}), 400
    try:
        c.scheduled_at = datetime.fromisoformat(when.replace("Z", "+00:00"))
    except ValueError:
        return jsonify({"error": "Invalid scheduled_at format"}), 400
    c.status = "scheduled"
    db.session.commit()
    return jsonify(c.to_dict())


@campaigns_bp.get("/email/campaigns/<int:cid>/sends")
@require_scope("email:read", also_role="viewer")
def campaign_sends(cid):
    guard = _feature_guard()
    if guard:
        return guard
    q = CampaignSend.query.filter_by(campaign_id=cid).order_by(CampaignSend.id.desc())
    items, meta = _paginate(q)
    return jsonify({"sends": [s.to_dict() for s in items], **meta})


# ══════════════════════════════════════════════════════════════════════════════
# SUPPRESSION + SETTINGS
# ══════════════════════════════════════════════════════════════════════════════

@campaigns_bp.get("/email/suppressions")
@require_scope("email:read", also_role="viewer")
def list_suppressions():
    guard = _feature_guard()
    if guard:
        return guard
    q = Suppression.query.order_by(Suppression.created_at.desc())
    items, meta = _paginate(q)
    return jsonify({"suppressions": [s.to_dict() for s in items], **meta})


@campaigns_bp.post("/email/suppressions")
@require_scope("email:write", also_role="admin")
def add_suppression():
    guard = _feature_guard()
    if guard:
        return guard
    data = request.get_json() or {}
    email = (data.get("email") or "").strip().lower()
    if not is_valid_email(email):
        return jsonify({"error": "Valid email required"}), 400
    s = SuppressionService.add(email, reason=data.get("reason", "manual"),
                               detail=data.get("detail", "Manually added"))
    return jsonify(s.to_dict()), 201


@campaigns_bp.delete("/email/suppressions/<int:sid>")
@require_scope("email:write", also_role="admin")
def remove_suppression(sid):
    guard = _feature_guard()
    if guard:
        return guard
    s = Suppression.query.get(sid)
    if not s:
        return jsonify({"error": "Not found"}), 404
    SuppressionService.remove(s.email)
    return jsonify({"removed": True})


@campaigns_bp.post("/email/transactional")
@require_scope("email:send", also_role="admin")
def transactional_send():
    """
    Send a single suppression-aware email. Intended for n8n drip orchestration
    (n8n authenticates with an X-API-Key service-account key).
    Body: { email, subject, html, from_name?, from_address?, reply_to? }
    """
    guard = _feature_guard()
    if guard:
        return guard
    data = request.get_json() or {}
    if not data.get("email") or not data.get("subject"):
        return jsonify({"error": "email and subject are required"}), 400
    result = send_transactional(
        email=data["email"],
        subject=data["subject"],
        html=sanitize_email_html(data.get("html", "")),
        from_name=data.get("from_name"),
        from_address=data.get("from_address"),
        reply_to=data.get("reply_to"),
    )
    log_action("email.transactional.sent", actor=getattr(request, "current_user", None),
               target_type="subscriber", target_label=data["email"],
               details={"sent": result.get("sent"), "reason": result.get("reason")})
    status = 200 if result.get("sent") else 202  # 202: accepted-but-skipped (suppressed/unsub)
    return jsonify(result), status


@campaigns_bp.get("/email/settings")
@require_scope("email:read", also_role="viewer")
def get_email_settings():
    guard = _feature_guard()
    if guard:
        return guard
    s = EmailSettings.get()
    cfg = email_ses.get_ses_config()
    out = s.to_dict()
    out["ses_provider"] = cfg["provider"]
    out["ses_from_address"] = cfg["from_address"]
    out["ses_configuration_set"] = cfg["configuration_set"]
    return jsonify(out)


@campaigns_bp.put("/email/settings")
@require_scope("email:write", also_role="admin")
def update_email_settings():
    guard = _feature_guard()
    if guard:
        return guard
    s = EmailSettings.get()
    data = request.get_json() or {}
    for f in ("from_name", "from_address", "reply_to", "footer_org_name",
              "footer_address", "footer_html"):
        if f in data:
            setattr(s, f, data[f])
    db.session.commit()
    log_action("email.settings.updated", actor=getattr(request, "current_user", None),
               target_type="email_settings", target_id=1)
    return jsonify(s.to_dict())


@campaigns_bp.get("/email/identities")
@require_scope("email:read", also_role="viewer")
def email_identities():
    """SES sender identity verification + DKIM status (SPF/DKIM/DMARC awareness)."""
    guard = _feature_guard()
    if guard:
        return guard
    result = {"available": True, "identities": []}
    try:
        client = email_ses.build_ses_v1_client()
        ids = client.list_identities().get("Identities", [])
        verify = client.get_identity_verification_attributes(Identities=ids).get(
            "VerificationAttributes", {}) if ids else {}
        try:
            dkim = client.get_identity_dkim_attributes(Identities=ids).get(
                "DkimAttributes", {}) if ids else {}
        except Exception:
            dkim = {}
        for ident in ids:
            v = verify.get(ident, {})
            d = dkim.get(ident, {})
            result["identities"].append({
                "identity": ident,
                "verification_status": v.get("VerificationStatus", "Unknown"),
                "dkim_enabled": bool(d.get("DkimEnabled")),
                "dkim_status": d.get("DkimVerificationStatus", "NotConfigured"),
            })
    except Exception as exc:
        result = {"available": False, "detail": str(exc)}
    return jsonify(result)


@campaigns_bp.get("/email/stats")
@require_scope("email:read", also_role="viewer")
def email_stats():
    guard = _feature_guard()
    if guard:
        return guard
    total_subs = Subscriber.query.filter_by(status="subscribed").count()
    campaigns_sent = Campaign.query.filter_by(status="sent").count()
    agg = db.session.query(
        db.func.coalesce(db.func.sum(Campaign.sent_count), 0),
        db.func.coalesce(db.func.sum(Campaign.open_count), 0),
        db.func.coalesce(db.func.sum(Campaign.click_count), 0),
        db.func.coalesce(db.func.sum(Campaign.bounce_count), 0),
        db.func.coalesce(db.func.sum(Campaign.complaint_count), 0),
    ).first()
    sent, opens, clicks, bounces, complaints = [int(x) for x in agg]
    return jsonify({
        "subscribers": total_subs,
        "suppressed": Suppression.query.count(),
        "campaigns_sent": campaigns_sent,
        "total_sent": sent,
        "open_rate": round(100.0 * opens / sent, 1) if sent else 0.0,
        "click_rate": round(100.0 * clicks / sent, 1) if sent else 0.0,
        "bounce_rate": round(100.0 * bounces / sent, 2) if sent else 0.0,
        "complaint_rate": round(100.0 * complaints / sent, 3) if sent else 0.0,
        "ses": email_ses.get_send_quota(),
    })


# ══════════════════════════════════════════════════════════════════════════════
# PUBLIC — SES event webhook (SNS) + one-click unsubscribe
# ══════════════════════════════════════════════════════════════════════════════

@public_email_bp.post("/email/webhooks/ses")
def ses_webhook():
    """
    Inbound SNS endpoint for SES events. Handles SubscriptionConfirmation and
    Notification. Verified via email_ses.verify_sns_message before acting.
    """
    if not current_app.config.get("FEATURE_EMAIL_CAMPAIGNS", False):
        return jsonify({"error": "disabled"}), 403
    try:
        payload = request.get_json(force=True, silent=True) or json.loads(request.data or "{}")
    except Exception:
        return jsonify({"error": "invalid payload"}), 400

    if not email_ses.verify_sns_message(payload):
        return jsonify({"error": "signature verification failed"}), 403

    msg_type = payload.get("Type")
    if msg_type == "SubscriptionConfirmation":
        # Confirm by fetching SubscribeURL (SNS handshake).
        sub_url = payload.get("SubscribeURL")
        logger.info("SNS SubscriptionConfirmation received: %s", sub_url)
        try:
            if sub_url and not email_ses._is_localstack():
                from urllib.request import urlopen
                urlopen(sub_url, timeout=5)  # nosec - AWS SNS confirmation URL
        except Exception as exc:
            logger.warning("SNS confirm fetch failed: %s", exc)
        return jsonify({"confirmed": True})

    # Notification: the SES event JSON is a string in payload["Message"].
    try:
        message = payload.get("Message")
        ses_event = json.loads(message) if isinstance(message, str) else (message or {})
    except Exception:
        return jsonify({"error": "invalid SES message"}), 400

    event_type = (ses_event.get("eventType") or ses_event.get("notificationType") or "").strip()
    mail = ses_event.get("mail", {})
    ses_message_id = mail.get("messageId")

    # Recipient resolution differs by event kind.
    email = None
    if event_type.lower() == "bounce":
        recips = ses_event.get("bounce", {}).get("bouncedRecipients", [])
        email = recips[0].get("emailAddress") if recips else None
        # Only hard bounces suppress.
        if ses_event.get("bounce", {}).get("bounceType") != "Permanent":
            event_type = "Bounce-Transient"
    elif event_type.lower() == "complaint":
        recips = ses_event.get("complaint", {}).get("complainedRecipients", [])
        email = recips[0].get("emailAddress") if recips else None
    else:
        dests = mail.get("destination", [])
        email = dests[0] if dests else None

    if event_type == "Bounce-Transient":
        # Log but don't suppress transient bounces.
        db.session.add(EmailEvent(ses_message_id=ses_message_id, event_type="Bounce-Transient",
                                  email=email, raw=ses_event))
        db.session.commit()
        return jsonify({"processed": "transient"})

    result = CampaignService.process_ses_event(event_type, ses_message_id, email, ses_event)
    return jsonify(result)


@public_email_bp.get("/email/unsubscribe/<token>")
def unsubscribe(token):
    """One-click unsubscribe landing (also satisfies List-Unsubscribe GET)."""
    sub = SubscriberService.unsubscribe_by_token(token)
    html = """<!doctype html><html><head><meta charset="utf-8">
    <meta name="viewport" content="width=device-width,initial-scale=1">
    <title>Unsubscribed</title>
    <style>body{{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;
    background:#0b1120;color:#e5e7eb;display:flex;align-items:center;justify-content:center;
    height:100vh;margin:0}}.card{{background:#111827;border:1px solid #1f2937;border-radius:16px;
    padding:40px;max-width:420px;text-align:center}}h1{{font-size:20px;margin:0 0 8px}}
    p{{color:#9ca3af;font-size:14px}}</style></head>
    <body><div class="card"><h1>{title}</h1><p>{body}</p></div></body></html>"""
    if sub:
        return html.format(title="You've been unsubscribed",
                           body="You will no longer receive marketing emails from us."), 200
    return html.format(title="Link not recognized",
                       body="This unsubscribe link is invalid or already used."), 404


@public_email_bp.post("/email/unsubscribe/<token>")
def unsubscribe_post(token):
    """RFC 8058 one-click POST target."""
    sub = SubscriberService.unsubscribe_by_token(token)
    return jsonify({"unsubscribed": bool(sub)}), (200 if sub else 404)
