"""
Employee quarterly performance reviews.

Applies to non-intern employees (including PoCs/team leads). Distinct from the
intern biweekly/milestone tracks in app/routes/internship.py.

Lifecycle: pending_self -> (employee self-report) -> pending_manager ->
(manager scores + decision) -> completed. Reviews are auto-created per calendar
quarter for every active non-intern employee, company-wide, by an idempotent
ensure step (lazy-triggered on relevant page loads and via an endpoint).
"""
from datetime import date, datetime, timedelta

from flask import Blueprint, current_app, jsonify, request

from app.extensions import db
from app.models import Employment, EmployeeReview, Person, EMPLOYEE_REVIEW_DECISIONS
from app.utils.audit import log_action
from app.utils.people_rbac import can_manage_person, is_hr_admin, get_person_for_user
from app.utils.rbac import require_role, require_active_user


performance_bp = Blueprint("performance", __name__)


def _feature_disabled():
    return jsonify({"error": "People feature is not enabled", "code": "FEATURE_DISABLED"}), 403


def check_feature_enabled():
    if not current_app.config.get("FEATURE_PEOPLE", False):
        return _feature_disabled()
    return None


def _validation_error(details):
    return jsonify({"error": "Validation failed", "code": "VALIDATION_ERROR", "details": details}), 400


def _can_view_person_performance(actor, person):
    """Own record, the manager of record, or HR/admin."""
    if is_hr_admin(actor) or actor.role == "admin":
        return True
    if actor.id == person.user_id:
        return True
    if actor.role == "people_manager":
        can_manage, _ = can_manage_person(actor, person)
        return can_manage
    return False


def current_quarter(today=None):
    """Return (label, period_start, period_end) for the calendar quarter
    containing `today` (defaults to today, UTC)."""
    today = today or datetime.utcnow().date()
    q = (today.month - 1) // 3  # 0..3
    start_month = q * 3 + 1
    period_start = date(today.year, start_month, 1)
    if start_month + 3 > 12:
        period_end = date(today.year, 12, 31)
    else:
        period_end = date(today.year, start_month + 3, 1) - timedelta(days=1)
    return f"{today.year}-Q{q + 1}", period_start, period_end


def ensure_quarterly_reviews(today=None):
    """Idempotently create the current quarter's review for every active
    non-intern employee that doesn't already have one. Returns the count
    created. Safe to call repeatedly and concurrently (unique constraint on
    person_id+quarter is the backstop)."""
    label, p_start, p_end = current_quarter(today)

    # Active, non-intern employees (one row per person via active_employment).
    employments = Employment.query.filter(
        Employment.status.in_(("active", "on_leave")),
        Employment.employment_type != "intern",
    ).all()

    created = 0
    for emp in employments:
        person = emp.person
        if not person or not person.active_employment or person.active_employment.id != emp.id:
            continue
        exists = EmployeeReview.query.filter_by(person_id=person.id, quarter=label).first()
        if exists:
            continue
        db.session.add(EmployeeReview(
            person_id=person.id,
            quarter=label,
            period_start=p_start,
            period_end=p_end,
            status="pending_self",
            self_report={},
        ))
        created += 1
    if created:
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            created = 0
    return created


@performance_bp.post("/performance/reviews/ensure")
@require_role("people_manager")
def ensure_reviews_endpoint():
    error = check_feature_enabled()
    if error:
        return error
    created = ensure_quarterly_reviews()
    if created:
        log_action(
            action="performance.reviews_ensured",
            actor=request.current_user,
            target_type="employee_review",
            target_id=None,
            target_label=current_quarter()[0],
            details={"created": created},
        )
    return jsonify({"message": f"Ensured quarterly reviews ({created} created)", "created": created})


@performance_bp.get("/performance/reviews")
@require_role("mentor")
def list_employee_reviews():
    error = check_feature_enabled()
    if error:
        return error

    actor = request.current_user
    person_id = request.args.get("person_id", type=int)
    query = EmployeeReview.query
    if person_id:
        person = Person.query.get_or_404(person_id)
        if not _can_view_person_performance(actor, person):
            return jsonify({"error": "Insufficient permissions", "code": "INSUFFICIENT_PERMISSIONS"}), 403
        query = query.filter(EmployeeReview.person_id == person_id)

    reviews = query.order_by(EmployeeReview.period_end.desc()).all()
    if not person_id:
        reviews = [r for r in reviews if _can_view_person_performance(actor, r.person)]
    return jsonify({"items": [r.to_dict() for r in reviews]})


@performance_bp.get("/performance/my-reviews")
@require_active_user
def my_employee_reviews():
    """Self-service list for the logged-in employee. Triggers the ensure step
    so a due quarterly review appears without any manual action."""
    error = check_feature_enabled()
    if error:
        return error

    actor = request.current_user
    person = get_person_for_user(actor.id)
    if not person:
        return jsonify({"linked": False, "items": []})

    emp = person.active_employment
    # Only non-intern employees participate in the quarterly workflow.
    if not emp or emp.employment_type == "intern":
        return jsonify({"linked": True, "applicable": False, "items": []})

    ensure_quarterly_reviews()
    reviews = (
        EmployeeReview.query.filter_by(person_id=person.id)
        .order_by(EmployeeReview.period_end.desc())
        .all()
    )
    return jsonify({"linked": True, "applicable": True, "items": [r.to_dict() for r in reviews]})


@performance_bp.post("/performance/reviews/<int:review_id>/self-submit")
@require_active_user
def self_submit_review(review_id):
    error = check_feature_enabled()
    if error:
        return error

    review = EmployeeReview.query.get_or_404(review_id)
    actor = request.current_user
    person = review.person

    if actor.role not in {"admin", "superadmin", "hr_admin"} and person.user_id != actor.id:
        return jsonify({"error": "You can only submit your own self-review", "code": "ACCESS_DENIED"}), 403
    if review.status != "pending_self":
        return _validation_error(["This review has already been submitted and passed to your manager"])

    data = request.get_json() or {}
    responses = data.get("responses")
    if not isinstance(responses, dict):
        return _validation_error(["responses dict is required"])

    review.self_report = responses
    review.status = "pending_manager"
    db.session.commit()

    from app.utils.integrations_mock import send_email_notification
    emp = person.active_employment
    if emp and emp.manager:
        send_email_notification(
            email=emp.manager.email,
            template_type="manager_reminder",
            context={"intern_name": person.full_name},
        )

    log_action(
        action="performance.self_submitted",
        actor=actor,
        target_type="person",
        target_id=person.id,
        target_label=person.full_name,
        details={"review_id": review.id, "quarter": review.quarter},
    )
    return jsonify({"message": "Self-review submitted", "review": review.to_dict()})


def _apply_employee_decision(review, decision, new_title, actor):
    """Apply a completed employee-review decision to the person's employment."""
    person = review.person
    emp = person.active_employment
    if emp:
        if decision == "extend" and emp.end_date:
            from datetime import timedelta
            emp.end_date = emp.end_date + timedelta(days=90)
        elif decision == "promote" and new_title:
            emp.title = new_title
        elif decision == "terminate":
            emp.status = "completed"
            emp.end_date = datetime.utcnow().date()

    review.decision = decision
    review.new_title = new_title if decision == "promote" else None
    review.decision_date = datetime.utcnow().date()
    review.status = "completed"
    review.completed_at = datetime.utcnow()
    review.reviewer_id = actor.id

    self_text = " ".join(str(v) for v in (review.self_report or {}).values())
    review.ai_summary = (
        f"[DRAFT AI Summary] {person.full_name} self-reports: '{self_text[:100]}...'. "
        f"Manager noted strengths: '{review.strengths or ''}'. Concerns: '{review.concerns or ''}'. "
        f"Score: {review.score}/5. Decision: {decision}."
    )
    db.session.commit()

    from app.utils.integrations_mock import send_email_notification
    send_email_notification(
        email=person.email,
        template_type="milestone_completed",
        context={"name": person.full_name, "review_type": f"{review.quarter} performance", "decision": decision},
    )

    log_action(
        action="performance.manager_completed",
        actor=actor,
        target_type="person",
        target_id=person.id,
        target_label=person.full_name,
        details={"review_id": review.id, "quarter": review.quarter, "decision": decision, "score": review.score},
    )
    return review


@performance_bp.post("/performance/reviews/<int:review_id>/manager-submit")
@require_role("people_manager")
def manager_submit_review(review_id):
    error = check_feature_enabled()
    if error:
        return error

    review = EmployeeReview.query.get_or_404(review_id)
    actor = request.current_user
    person = review.person

    allowed, reason = can_manage_person(actor, person)
    if not allowed:
        return jsonify({"error": reason or "Insufficient permissions", "code": "INSUFFICIENT_PERMISSIONS"}), 403
    if review.status == "completed":
        return _validation_error(["This review is already completed"])
    if review.status != "pending_manager":
        return _validation_error(["This review is awaiting the employee's self-report and cannot be graded yet"])

    data = request.get_json() or {}
    score = data.get("score")
    if score is None or not isinstance(score, int) or score < 1 or score > 5:
        return _validation_error(["score must be an integer between 1 and 5"])

    decision = data.get("decision")
    if decision not in EMPLOYEE_REVIEW_DECISIONS:
        return _validation_error([f"decision must be one of: {', '.join(sorted(EMPLOYEE_REVIEW_DECISIONS))}"])

    new_title = (data.get("new_title") or "").strip()
    if decision == "promote" and not new_title:
        return _validation_error(["new_title is required when decision is 'promote'"])

    review.score = score
    review.strengths = data.get("strengths")
    review.concerns = data.get("concerns")
    review.action_items = data.get("action_items", [])
    review.manager_notes = data.get("notes")

    # Terminations route through the governance queue when a policy is active.
    if decision == "terminate":
        from app.routes.governance import check_policy
        requires_approval, _policy, approval_request = check_policy(
            action="people.finalize_employee_review",
            actor=actor,
            target_type="employee_review",
            target_id=review.id,
            target_label=f"{review.quarter} termination for {person.full_name}",
            request_data={"review_id": review.id, "decision": decision,
                          "score": score, "new_title": new_title},
        )
        if requires_approval and approval_request:
            db.session.commit()  # persist scoring before awaiting approval
            return jsonify({
                "message": "Approval required to finalize termination",
                "code": "APPROVAL_REQUIRED",
                "approval_request": approval_request.to_dict(),
            }), 202

    review = _apply_employee_decision(review, decision, new_title, actor)
    return jsonify({"message": f"Performance review completed: {decision}", "review": review.to_dict()})
