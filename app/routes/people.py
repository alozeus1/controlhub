import csv
import io
from datetime import date, datetime

from flask import Blueprint, current_app, jsonify, request, Response
from sqlalchemy import and_, or_

from app.extensions import db, limiter
from app.utils.rate_limit import identity_rate_key
from app.models import (
    Person,
    Employment,
    PerformanceCheckin,
    AccessAssignment,
    User,
    ApprovalRequest,
    EMPLOYMENT_TYPES,
    EMPLOYMENT_STATUSES,
    INTERN_TRACKS,
)
from app.utils.audit import log_action
from app.utils.people_rbac import can_manage_person, can_add_checkin, get_person_for_user, is_hr_admin
from app.utils.rbac import require_role

people_bp = Blueprint("people", __name__)


def _feature_disabled():
    return jsonify({
        "error": "People feature is not enabled",
        "code": "FEATURE_DISABLED",
    }), 403


def check_feature_enabled():
    if not current_app.config.get("FEATURE_PEOPLE", False):
        return _feature_disabled()
    return None


def _validation_error(details):
    return jsonify({
        "error": "Validation failed",
        "code": "VALIDATION_ERROR",
        "details": details,
    }), 400


def _parse_date(value, field):
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ValueError(f"{field} must be a valid ISO date (YYYY-MM-DD)")


def _approved_request_or_none(request_id: int, action: str, requester_id: int):
    approval = ApprovalRequest.query.get(request_id)
    if not approval:
        return None
    if approval.action != action:
        return None
    if approval.requester_id != requester_id:
        return None
    if approval.status != "approved":
        return None
    return approval


def _employment_snapshot(emp: Employment):
    if not emp:
        return None
    return {
        "employment_type": emp.employment_type,
        "intern_track": emp.intern_track,
        "status": emp.status,
        "title": emp.title,
        "start_date": emp.start_date.isoformat() if emp.start_date else None,
        "end_date": emp.end_date.isoformat() if emp.end_date else None,
        "compensation_type": emp.compensation_type,
        "salary_amount": float(emp.salary_amount) if emp.salary_amount is not None else None,
        "currency": emp.currency,
        "contract_signed_date": emp.contract_signed_date.isoformat() if emp.contract_signed_date else None,
        "payment_status": emp.payment_status,
        "amount_paid": float(emp.amount_paid) if emp.amount_paid is not None else None,
        "amount_outstanding": float(emp.amount_outstanding) if emp.amount_outstanding is not None else None,
        "payment_due_date": emp.payment_due_date.isoformat() if emp.payment_due_date else None,
        "payment_frequency": emp.payment_frequency,
        "manager_person_id": emp.manager_person_id,
        "mentor_person_id": emp.mentor_person_id,
        "poc_person_id": emp.poc_person_id,
        "notes": emp.notes,
    }


def _compute_changes(before, after):
    changes = {}
    before = before or {}
    after = after or {}
    for field in set(before.keys()) | set(after.keys()):
        if before.get(field) != after.get(field):
            changes[field] = {"from": before.get(field), "to": after.get(field)}
    return changes


def _base_people_query():
    return Person.query


def _apply_people_filters(query):
    search = request.args.get("search")
    team = request.args.get("team")
    department = request.args.get("department")
    cohort = request.args.get("cohort")
    is_active = request.args.get("is_active")
    employment_type = request.args.get("employment_type")
    intern_track = request.args.get("intern_track")
    status = request.args.get("status")
    manager_person_id = request.args.get("manager_person_id", type=int)

    if search:
        pattern = f"%{search}%"
        query = query.filter(
            or_(
                Person.first_name.ilike(pattern),
                Person.last_name.ilike(pattern),
                Person.email.ilike(pattern),
            )
        )
    if team:
        query = query.filter(Person.team == team)
    if department:
        query = query.filter(Person.department == department)
    if cohort:
        query = query.filter(Person.cohort == cohort)
    if is_active is not None:
        query = query.filter(Person.is_active == (is_active.lower() == "true"))

    if any([employment_type, intern_track, status, manager_person_id]):
        employment_filters = []
        if employment_type:
            employment_filters.append(Employment.employment_type == employment_type)
        if intern_track:
            employment_filters.append(Employment.intern_track == intern_track)
        if status:
            employment_filters.append(Employment.status == status)
        if manager_person_id:
            employment_filters.append(Employment.manager_person_id == manager_person_id)
        # Use relationship EXISTS semantics instead of JOIN + DISTINCT ON to keep
        # query ordering portable and PostgreSQL-safe.
        query = query.filter(Person.employments.any(and_(*employment_filters)))

    return query


def _export_people_csv(rows, include_compensation=False):
    output = io.StringIO()
    writer = csv.writer(output)
    headers = [
        "person_id",
        "full_name",
        "email",
        "team",
        "department",
        "cohort",
        "is_active",
        "employment_type",
        "intern_track",
        "employment_status",
        "title",
        "manager",
        "mentor",
        "start_date",
        "end_date",
    ]
    if include_compensation:
        headers.extend(["compensation_type", "salary_amount", "currency", "contract_signed_date", "payment_status", "amount_paid", "amount_outstanding"])
    writer.writerow(headers)
    for person in rows:
        emp = person.active_employment
        row_data = [
            person.id,
            person.full_name,
            person.email,
            person.team or "",
            person.department or "",
            person.cohort or "",
            str(person.is_active).lower(),
            emp.employment_type if emp else "",
            emp.intern_track if emp else "",
            emp.status if emp else "",
            emp.title if emp else "",
            emp.manager.full_name if (emp and emp.manager) else "",
            emp.mentor.full_name if (emp and emp.mentor) else "",
            emp.start_date.isoformat() if (emp and emp.start_date) else "",
            emp.end_date.isoformat() if (emp and emp.end_date) else "",
        ]
        if include_compensation:
            row_data.extend([
                emp.compensation_type if emp else "",
                float(emp.salary_amount) if (emp and emp.salary_amount is not None) else "",
                emp.currency if emp else "",
                emp.contract_signed_date.isoformat() if (emp and emp.contract_signed_date) else "",
                emp.payment_status if emp else "",
                float(emp.amount_paid) if (emp and emp.amount_paid is not None) else "",
                float(emp.amount_outstanding) if (emp and emp.amount_outstanding is not None) else "",
            ])
        writer.writerow(row_data)
    return output.getvalue()


@people_bp.get("/people")
@require_role("viewer")
def list_people():
    error = check_feature_enabled()
    if error:
        return error

    query = _apply_people_filters(_base_people_query()).order_by(Person.created_at.desc())
    page = request.args.get("page", 1, type=int)
    page_size = min(request.args.get("page_size", 20, type=int), 100)
    pagination = query.paginate(page=page, per_page=page_size, error_out=False)

    return jsonify({
        "items": [p.to_dict() for p in pagination.items],
        "total": pagination.total,
        "page": pagination.page,
        "page_size": pagination.per_page,
        "pages": pagination.pages,
    })


@people_bp.get("/people/metadata")
@require_role("viewer")
def people_metadata():
    error = check_feature_enabled()
    if error:
        return error

    teams = sorted({v for (v,) in db.session.query(Person.team).filter(Person.team.isnot(None)).distinct().all() if v})
    departments = sorted({v for (v,) in db.session.query(Person.department).filter(Person.department.isnot(None)).distinct().all() if v})
    cohorts = sorted({v for (v,) in db.session.query(Person.cohort).filter(Person.cohort.isnot(None)).distinct().all() if v})
    # Authoritative "active cohorts" count — same source the Internship Hub uses
    # for "Running Cohorts" (InternshipCohort rows with status 'active'), so the
    # two pages agree instead of counting free-text Person.cohort labels.
    try:
        from app.models import InternshipCohort
        active_cohorts = InternshipCohort.query.filter_by(status="active").count()
    except Exception:
        active_cohorts = 0
    managers = [
        {"id": p.id, "name": p.full_name}
        for p in Person.query.order_by(Person.first_name.asc(), Person.last_name.asc()).all()
    ]
    return jsonify({
        "employment_types": sorted(list(EMPLOYMENT_TYPES)),
        "employment_statuses": sorted(list(EMPLOYMENT_STATUSES)),
        "intern_tracks": sorted(list(INTERN_TRACKS)),
        "teams": teams,
        "departments": departments,
        "cohorts": cohorts,
        "active_cohorts": active_cohorts,
        "managers": managers,
    })


@people_bp.get("/people/<int:person_id>")
@require_role("viewer")
def get_person(person_id):
    error = check_feature_enabled()
    if error:
        return error

    person = Person.query.get_or_404(person_id)
    actor = request.current_user
    allowed_manage, _ = can_manage_person(actor, person)
    show_compensation = is_hr_admin(actor) or allowed_manage or actor.id == person.user_id

    emp_history = []
    for e in sorted(person.employments, key=lambda x: x.created_at or datetime.min, reverse=True):
        e_dict = e.to_dict()
        if not show_compensation:
            # Mask sensitive compensation fields
            for f in ["salary_amount", "amount_paid", "amount_outstanding"]:
                e_dict[f] = None
        emp_history.append(e_dict)

    return jsonify({
        "person": person.to_dict(),
        "employment_history": emp_history,
    })


@people_bp.post("/people")
@require_role("people_manager")
def create_person():
    error = check_feature_enabled()
    if error:
        return error

    data = request.get_json() or {}
    errors = []
    for field in ("first_name", "last_name", "email", "employment_type"):
        if not isinstance(data.get(field), str) or not data.get(field).strip():
            errors.append(f"{field} is required")
    if data.get("employment_type") not in EMPLOYMENT_TYPES:
        errors.append(f"employment_type must be one of: {', '.join(sorted(EMPLOYMENT_TYPES))}")
    if data.get("employment_type") == "intern":
        if data.get("intern_track") not in INTERN_TRACKS:
            errors.append(f"intern_track must be one of: {', '.join(sorted(INTERN_TRACKS))}")
    if data.get("intern_track") and data.get("employment_type") != "intern":
        errors.append("intern_track is only allowed for intern employment_type")
    if errors:
        return _validation_error(errors)

    actor = request.current_user
    user_id = data.get("user_id")
    if user_id is not None and not User.query.get(user_id):
        return _validation_error(["user_id does not reference an existing user"])

    manager_person_id = data.get("manager_person_id")
    mentor_person_id = data.get("mentor_person_id")
    poc_person_id = data.get("poc_person_id")
    if manager_person_id and not Person.query.get(manager_person_id):
        return _validation_error(["manager_person_id not found"])
    if mentor_person_id and not Person.query.get(mentor_person_id):
        return _validation_error(["mentor_person_id not found"])
    if poc_person_id and not Person.query.get(poc_person_id):
        return _validation_error(["poc_person_id not found"])
    if actor.role == "people_manager":
        actor_person = get_person_for_user(actor.id)
        if not actor_person:
            return jsonify({"error": "people_manager requires linked person profile"}), 403
        if manager_person_id and manager_person_id != actor_person.id:
            return jsonify({"error": "people_manager may only create records under themselves"}), 403
        manager_person_id = actor_person.id

    try:
        start_date = _parse_date(data.get("start_date"), "start_date")
        end_date = _parse_date(data.get("end_date"), "end_date")
    except ValueError as exc:
        return _validation_error([str(exc)])

    person = Person(
        user_id=user_id,
        first_name=data["first_name"].strip(),
        last_name=data["last_name"].strip(),
        email=data["email"].strip().lower(),
        phone=data.get("phone"),
        team=data.get("team"),
        department=data.get("department"),
        cohort=data.get("cohort"),
        is_active=True,
        created_by_id=actor.id,
    )
    db.session.add(person)
    db.session.flush()

    employment = Employment(
        person_id=person.id,
        employment_type=data["employment_type"],
        intern_track=data.get("intern_track"),
        status=data.get("status", "active"),
        title=data.get("title"),
        start_date=start_date,
        end_date=end_date,
        manager_person_id=manager_person_id,
        mentor_person_id=mentor_person_id,
        poc_person_id=poc_person_id,
        notes=data.get("notes"),
        created_by_id=actor.id,
    )
    db.session.add(employment)
    db.session.commit()

    log_action(
        action="people.created",
        actor=actor,
        target_type="person",
        target_id=person.id,
        target_label=person.full_name,
        details={
            "employment_type": employment.employment_type,
            "intern_track": employment.intern_track,
            "team": person.team,
            "department": person.department,
            "cohort": person.cohort,
        },
    )
    return jsonify({"message": "Person created", "person": person.to_dict()}), 201


@people_bp.patch("/people/<int:person_id>")
@require_role("people_manager")
def update_person(person_id):
    error = check_feature_enabled()
    if error:
        return error

    actor = request.current_user
    person = Person.query.get_or_404(person_id)
    allowed, reason = can_manage_person(actor, person)
    if not allowed:
        return jsonify({"error": reason, "code": "INSUFFICIENT_PERMISSIONS"}), 403

    data = request.get_json() or {}
    allowed_fields = {
        "first_name",
        "last_name",
        "email",
        "phone",
        "team",
        "department",
        "cohort",
        "is_active",
        "taiga_username",
        "mattermost_username",
        "assigned_projects",
        "signed_documents",
        "risk_flags",
        "growth_summary",
    }
    unexpected = sorted(set(data.keys()) - allowed_fields)
    if unexpected:
        return _validation_error([f"Unexpected fields: {', '.join(unexpected)}"])

    errors = []
    for field in ("assigned_projects", "risk_flags"):
        if field in data and data[field] is not None:
            if not isinstance(data[field], list) or not all(isinstance(v, str) for v in data[field]):
                errors.append(f"{field} must be a list of strings")
    if "signed_documents" in data and data["signed_documents"] is not None:
        if not isinstance(data["signed_documents"], dict):
            errors.append("signed_documents must be an object")
    for field in ("taiga_username", "mattermost_username"):
        if field in data and data[field] is not None:
            if not isinstance(data[field], str) or len(data[field]) > 100:
                errors.append(f"{field} must be a string of at most 100 characters")
    if errors:
        return _validation_error(errors)

    before = {
        "first_name": person.first_name,
        "last_name": person.last_name,
        "email": person.email,
        "phone": person.phone,
        "team": person.team,
        "department": person.department,
        "cohort": person.cohort,
        "is_active": person.is_active,
        "taiga_username": person.taiga_username,
        "mattermost_username": person.mattermost_username,
        "assigned_projects": person.assigned_projects,
        "signed_documents": person.signed_documents,
        "risk_flags": person.risk_flags,
        "growth_summary": person.growth_summary,
    }
    for field in allowed_fields:
        if field in data:
            setattr(person, field, data[field])
    after = {
        "first_name": person.first_name,
        "last_name": person.last_name,
        "email": person.email,
        "phone": person.phone,
        "team": person.team,
        "department": person.department,
        "cohort": person.cohort,
        "is_active": person.is_active,
        "taiga_username": person.taiga_username,
        "mattermost_username": person.mattermost_username,
        "assigned_projects": person.assigned_projects,
        "signed_documents": person.signed_documents,
        "risk_flags": person.risk_flags,
        "growth_summary": person.growth_summary,
    }
    changes = _compute_changes(before, after)
    if not changes:
        return jsonify({"message": "No changes made", "person": person.to_dict(), "changes": {}})

    db.session.commit()
    log_action(
        action="people.updated",
        actor=actor,
        target_type="person",
        target_id=person.id,
        target_label=person.full_name,
        details={"changes": changes},
    )
    return jsonify({"message": "Person updated", "person": person.to_dict(), "changes": changes})


@people_bp.post("/people/<int:person_id>/employment")
@require_role("people_manager")
def update_employment(person_id):
    error = check_feature_enabled()
    if error:
        return error

    actor = request.current_user
    person = Person.query.get_or_404(person_id)
    allowed, reason = can_manage_person(actor, person)
    if not allowed:
        return jsonify({"error": reason, "code": "INSUFFICIENT_PERMISSIONS"}), 403

    data = request.get_json() or {}
    allowed_fields = {
        "employment_type",
        "intern_track",
        "status",
        "title",
        "start_date",
        "end_date",
        "compensation_type",
        "salary_amount",
        "currency",
        "contract_signed_date",
        "payment_status",
        "amount_paid",
        "amount_outstanding",
        "payment_due_date",
        "payment_frequency",
        "manager_person_id",
        "mentor_person_id",
        "poc_person_id",
        "notes",
    }
    unexpected = sorted(set(data.keys()) - allowed_fields)
    if unexpected:
        return _validation_error([f"Unexpected fields: {', '.join(unexpected)}"])

    if "employment_type" in data and data["employment_type"] not in EMPLOYMENT_TYPES:
        return _validation_error([f"employment_type must be one of: {', '.join(sorted(EMPLOYMENT_TYPES))}"])
    if "intern_track" in data and data["intern_track"] not in (None, "", *INTERN_TRACKS):
        return _validation_error([f"intern_track must be one of: {', '.join(sorted(INTERN_TRACKS))}"])
    if "status" in data and data["status"] not in EMPLOYMENT_STATUSES:
        return _validation_error([f"status must be one of: {', '.join(sorted(EMPLOYMENT_STATUSES))}"])

    employment = person.active_employment
    if not employment:
        employment = Employment(
            person_id=person.id,
            employment_type=data.get("employment_type", "full_time"),
            status=data.get("status", "active"),
            created_by_id=actor.id,
        )
        db.session.add(employment)
        db.session.flush()

    before = _employment_snapshot(employment)
    if "employment_type" in data:
        employment.employment_type = data["employment_type"]
        if employment.employment_type != "intern":
            employment.intern_track = None
    if "intern_track" in data:
        employment.intern_track = data["intern_track"] or None
    if "status" in data:
        employment.status = data["status"]
    if "title" in data:
        employment.title = data["title"]
    if "manager_person_id" in data:
        if data["manager_person_id"] and not Person.query.get(data["manager_person_id"]):
            return _validation_error(["manager_person_id not found"])
        employment.manager_person_id = data["manager_person_id"]
    if "mentor_person_id" in data:
        if data["mentor_person_id"] and not Person.query.get(data["mentor_person_id"]):
            return _validation_error(["mentor_person_id not found"])
        employment.mentor_person_id = data["mentor_person_id"]
    if "poc_person_id" in data:
        if data["poc_person_id"] and not Person.query.get(data["poc_person_id"]):
            return _validation_error(["poc_person_id not found"])
        employment.poc_person_id = data["poc_person_id"]
    if "notes" in data:
        employment.notes = data["notes"]
    if "start_date" in data:
        try:
            employment.start_date = _parse_date(data.get("start_date"), "start_date")
        except ValueError as exc:
            return _validation_error([str(exc)])
    if "end_date" in data:
        try:
            employment.end_date = _parse_date(data.get("end_date"), "end_date")
        except ValueError as exc:
            return _validation_error([str(exc)])
    if "contract_signed_date" in data:
        try:
            employment.contract_signed_date = _parse_date(data.get("contract_signed_date"), "contract_signed_date")
        except ValueError as exc:
            return _validation_error([str(exc)])
    if "payment_due_date" in data:
        try:
            employment.payment_due_date = _parse_date(data.get("payment_due_date"), "payment_due_date")
        except ValueError as exc:
            return _validation_error([str(exc)])
            
    for f in ["compensation_type", "salary_amount", "currency", "payment_status", "amount_paid", "amount_outstanding", "payment_frequency"]:
        if f in data:
            if "amount" in f or "salary" in f:
                val = data[f]
                if val in ("", None):
                    setattr(employment, f, None)
                else:
                    try:
                        setattr(employment, f, float(val))
                    except ValueError:
                        return _validation_error([f"{f} must be a valid number"])
            else:
                setattr(employment, f, data[f])

    employment.updated_by_id = actor.id
    after = _employment_snapshot(employment)
    changes = _compute_changes(before, after)
    if not changes:
        return jsonify({"message": "No changes made", "employment": employment.to_dict(), "changes": {}})

    db.session.commit()
    log_action(
        action="people.employment_updated",
        actor=actor,
        target_type="person",
        target_id=person.id,
        target_label=person.full_name,
        details={"changes": changes},
    )
    return jsonify({"message": "Employment updated", "employment": employment.to_dict(), "changes": changes})


@people_bp.post("/people/<int:person_id>/convert-to-full-time")
@require_role("people_manager")
def convert_intern_to_full_time(person_id):
    error = check_feature_enabled()
    if error:
        return error

    actor = request.current_user
    person = Person.query.get_or_404(person_id)
    allowed, reason = can_manage_person(actor, person)
    if not allowed:
        return jsonify({"error": reason, "code": "INSUFFICIENT_PERMISSIONS"}), 403

    current = person.active_employment
    if not current or current.employment_type != "intern":
        return jsonify({"error": "Person is not an active intern"}), 400

    data = request.get_json() or {}
    from app.routes.governance import check_policy
    requires_approval, _policy, approval_request = check_policy(
        action="people.convert_intern",
        actor=actor,
        target_type="person",
        target_id=person.id,
        target_label=person.full_name,
        request_data={
            "person_id": person.id,
            "title": data.get("title"),
            "start_date": data.get("start_date"),
            "manager_person_id": data.get("manager_person_id", current.manager_person_id),
        },
    )
    if requires_approval and approval_request:
        return jsonify({
            "message": "Approval required for intern conversion",
            "code": "APPROVAL_REQUIRED",
            "approval_request": approval_request.to_dict(),
        }), 202

    current.status = "completed"
    current.end_date = date.today()

    try:
        new_start = _parse_date(data.get("start_date"), "start_date") or date.today()
    except ValueError as exc:
        return _validation_error([str(exc)])
    new_emp = Employment(
        person_id=person.id,
        employment_type="full_time",
        intern_track=None,
        status="active",
        title=data.get("title") or current.title,
        start_date=new_start,
        manager_person_id=data.get("manager_person_id", current.manager_person_id),
        mentor_person_id=None,
        notes=data.get("notes"),
        created_by_id=actor.id,
    )
    db.session.add(new_emp)
    db.session.commit()

    log_action(
        action="people.converted_to_full_time",
        actor=actor,
        target_type="person",
        target_id=person.id,
        target_label=person.full_name,
        details={"from_track": current.intern_track, "new_title": new_emp.title},
    )
    return jsonify({"message": "Intern converted to full-time", "employment": new_emp.to_dict()})


@people_bp.post("/people/<int:person_id>/terminate")
@require_role("people_manager")
def terminate_person(person_id):
    error = check_feature_enabled()
    if error:
        return error

    actor = request.current_user
    person = Person.query.get_or_404(person_id)
    allowed, reason = can_manage_person(actor, person)
    if not allowed:
        return jsonify({"error": reason, "code": "INSUFFICIENT_PERMISSIONS"}), 403

    current = person.active_employment
    if not current:
        return jsonify({"error": "No active employment to terminate"}), 400

    data = request.get_json() or {}
    from app.routes.governance import check_policy
    requires_approval, _policy, approval_request = check_policy(
        action="people.terminate",
        actor=actor,
        target_type="person",
        target_id=person.id,
        target_label=person.full_name,
        request_data={"person_id": person.id, "notes": data.get("notes"), "end_date": data.get("end_date")},
    )
    if requires_approval and approval_request:
        return jsonify({
            "message": "Approval required for termination",
            "code": "APPROVAL_REQUIRED",
            "approval_request": approval_request.to_dict(),
        }), 202

    try:
        term_date = _parse_date(data.get("end_date"), "end_date") or date.today()
    except ValueError as exc:
        return _validation_error([str(exc)])

    current.status = "terminated"
    current.end_date = term_date
    if data.get("notes"):
        current.notes = data["notes"]
    current.updated_by_id = actor.id
    person.is_active = False
    db.session.commit()

    log_action(
        action="people.terminated",
        actor=actor,
        target_type="person",
        target_id=person.id,
        target_label=person.full_name,
        details={"end_date": term_date.isoformat()},
    )
    return jsonify({"message": "Person terminated", "employment": current.to_dict(), "person": person.to_dict()})


@people_bp.patch("/people/<int:person_id>/user-role")
@require_role("hr_admin")
def change_linked_user_role(person_id):
    error = check_feature_enabled()
    if error:
        return error

    actor = request.current_user
    person = Person.query.get_or_404(person_id)
    if not person.user_id:
        return jsonify({"error": "Person is not linked to an application user"}), 400

    user = User.query.get(person.user_id)
    if not user:
        return jsonify({"error": "Linked user not found"}), 404

    data = request.get_json() or {}
    new_role = data.get("role")
    if not isinstance(new_role, str) or not new_role:
        return _validation_error(["role is required"])

    from app.models import ROLE_LEVELS
    if new_role not in ROLE_LEVELS:
        return _validation_error([f"role must be one of: {', '.join(sorted(ROLE_LEVELS.keys()))}"])
    if actor.role != "superadmin" and new_role in {"superadmin", "hr_admin"}:
        return jsonify({"error": "Only superadmin can assign superadmin/hr_admin roles"}), 403

    from app.routes.governance import check_policy
    requires_approval, _policy, approval_request = check_policy(
        action="user.role_change",
        actor=actor,
        target_type="user",
        target_id=user.id,
        target_label=user.email,
        request_data={"new_role": new_role},
    )
    if requires_approval and approval_request:
        return jsonify({
            "message": "Approval required for role change",
            "code": "APPROVAL_REQUIRED",
            "approval_request": approval_request.to_dict(),
        }), 202

    old_role = user.role
    user.role = new_role
    db.session.commit()
    log_action(
        action="people.user_role_changed",
        actor=actor,
        target_type="user",
        target_id=user.id,
        target_label=user.email,
        details={"from": old_role, "to": new_role, "person_id": person.id},
    )
    return jsonify({"message": "User role updated", "user": user.to_dict()})


@people_bp.get("/people/export/csv")
@limiter.limit("20 per hour", key_func=identity_rate_key)
@require_role("people_manager")
def export_people_csv():
    error = check_feature_enabled()
    if error:
        return error

    actor = request.current_user
    approval_request_id = request.args.get("approval_request_id", type=int)

    if approval_request_id:
        approval = _approved_request_or_none(approval_request_id, "people.export_bulk", actor.id)
        if not approval:
            return jsonify({"error": "Invalid or non-approved approval_request_id", "code": "INVALID_APPROVAL"}), 403
    else:
        from app.routes.governance import check_policy

        requires_approval, _policy, approval_request = check_policy(
            action="people.export_bulk",
            actor=actor,
            target_type="person",
            target_label="directory_export",
            request_data={"filters": request.args.to_dict()},
        )
        if requires_approval and approval_request:
            return jsonify({
                "message": "Approval required for directory export",
                "code": "APPROVAL_REQUIRED",
                "approval_request": approval_request.to_dict(),
            }), 202

    rows = _apply_people_filters(_base_people_query()).order_by(Person.created_at.desc()).all()
    include_compensation = is_hr_admin(actor) or actor.role == "superadmin"
    csv_data = _export_people_csv(rows, include_compensation=include_compensation)
    log_action(
        action="people.exported",
        actor=actor,
        target_type="person",
        target_label="directory_export",
        details={"count": len(rows), "filters": request.args.to_dict()},
    )
    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename=people_directory_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"},
    )


@people_bp.get("/people/<int:person_id>/checkins")
@require_role("viewer")
def list_checkins(person_id):
    error = check_feature_enabled()
    if error:
        return error

    person = Person.query.get_or_404(person_id)
    checkins = PerformanceCheckin.query.filter_by(person_id=person.id).order_by(PerformanceCheckin.created_at.desc()).all()
    return jsonify({"items": [c.to_dict() for c in checkins], "total": len(checkins)})


@people_bp.post("/people/<int:person_id>/checkins")
@require_role("mentor")
def add_checkin(person_id):
    error = check_feature_enabled()
    if error:
        return error

    actor = request.current_user
    person = Person.query.get_or_404(person_id)
    allowed, reason = can_add_checkin(actor, person)
    if not allowed:
        return jsonify({"error": reason, "code": "INSUFFICIENT_PERMISSIONS"}), 403

    data = request.get_json() or {}
    summary = (data.get("summary") or "").strip()
    if not summary:
        return _validation_error(["summary is required"])

    checkin = PerformanceCheckin(
        person_id=person.id,
        author_id=actor.id,
        summary=summary,
        notes=data.get("notes"),
    )
    db.session.add(checkin)
    db.session.commit()

    log_action(
        action="people.checkin_added",
        actor=actor,
        target_type="person",
        target_id=person.id,
        target_label=person.full_name,
        details={"checkin_id": checkin.id},
    )
    return jsonify({"message": "Check-in added", "checkin": checkin.to_dict()}), 201


@people_bp.get("/people/<int:person_id>/access-assignments")
@require_role("viewer")
def list_access_assignments(person_id):
    error = check_feature_enabled()
    if error:
        return error

    person = Person.query.get_or_404(person_id)
    assignments = AccessAssignment.query.filter_by(person_id=person.id).order_by(AccessAssignment.created_at.desc()).all()
    return jsonify({"items": [a.to_dict() for a in assignments], "total": len(assignments)})


@people_bp.post("/people/<int:person_id>/access-assignments")
@require_role("people_manager")
def add_access_assignment(person_id):
    error = check_feature_enabled()
    if error:
        return error

    actor = request.current_user
    person = Person.query.get_or_404(person_id)
    allowed, reason = can_manage_person(actor, person)
    if not allowed and not is_hr_admin(actor):
        return jsonify({"error": reason, "code": "INSUFFICIENT_PERMISSIONS"}), 403

    data = request.get_json() or {}
    if not data.get("system_name") or not data.get("access_level"):
        return _validation_error(["system_name and access_level are required"])

    assignment = AccessAssignment(
        person_id=person.id,
        system_name=data["system_name"],
        access_level=data["access_level"],
        status=data.get("status", "active"),
        assigned_by_id=actor.id,
    )
    db.session.add(assignment)
    db.session.commit()
    log_action(
        action="people.access_assigned",
        actor=actor,
        target_type="person",
        target_id=person.id,
        target_label=person.full_name,
        details={"system_name": assignment.system_name, "access_level": assignment.access_level},
    )
    return jsonify({"message": "Access assigned", "assignment": assignment.to_dict()}), 201
