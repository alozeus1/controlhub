import secrets
from datetime import date, datetime

from flask import Blueprint, current_app, jsonify, request
from sqlalchemy import or_

from app.extensions import db
from app.models import (
    INTERNSHIP_COHORT_MEMBER_ROLES,
    INTERNSHIP_COHORT_STATUSES,
    INTERNSHIP_PROGRAM_STATUSES,
    Employment,
    InternshipCertificate,
    InternshipCohort,
    InternshipCohortMember,
    InternshipCompletionChecklist,
    InternshipProgram,
    OnboardingTemplateItem,
    Person,
    PersonOnboardingItem,
    BiweeklyReview,
    MilestoneReview,
    User,
)
from app.utils.audit import log_action
from app.utils.notify import notify_user
from app.utils.people_rbac import can_manage_person, is_hr_admin, is_poc_for
from app.utils.rbac import require_role, require_active_user


internship_bp = Blueprint("internship", __name__)


def _feature_disabled():
    return jsonify({
        "error": "Internship Program feature is not enabled",
        "code": "FEATURE_DISABLED",
    }), 403


def check_feature_enabled():
    if not current_app.config.get("FEATURE_PEOPLE", False):
        return _feature_disabled()
    if not current_app.config.get("FEATURE_INTERNSHIP_PROGRAM", False):
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
    except ValueError as exc:
        raise ValueError(f"{field} must be a valid ISO date (YYYY-MM-DD)") from exc


def _can_view_person_internship(actor, person):
    if is_hr_admin(actor) or actor.role in {"admin", "people_manager", "mentor"}:
        if actor.role in {"people_manager", "mentor"}:
            can_manage, _ = can_manage_person(actor, person)
            if can_manage:
                return True
            return actor.id == person.user_id
        return True
    if actor.role == "team_lead":
        return is_poc_for(actor, person) or actor.id == person.user_id
    return actor.id == person.user_id


def _can_update_person_internship(actor, person):
    if is_hr_admin(actor) or actor.role == "admin":
        return True, None
    return can_manage_person(actor, person)


def _issue_certificate(person, actor, pdf_url=None):
    year = datetime.utcnow().year
    code = secrets.token_hex(3).upper()
    certificate_no = f"CH-{year}-{code}"

    certificate = InternshipCertificate(
        person_id=person.id,
        certificate_no=certificate_no,
        pdf_url=pdf_url,
        issued_by_id=actor.id if actor else None,
    )
    db.session.add(certificate)
    db.session.commit()

    log_action(
        action="internship.certificate_issued",
        actor=actor,
        target_type="person",
        target_id=person.id,
        target_label=person.full_name,
        details={
            "certificate_id": certificate.id,
            "certificate_no": certificate.certificate_no,
            "pdf_url": certificate.pdf_url,
        },
    )
    return certificate


@internship_bp.get("/internship/metadata")
@require_role("viewer")
def internship_metadata():
    error = check_feature_enabled()
    if error:
        return error

    return jsonify({
        "program_statuses": sorted(list(INTERNSHIP_PROGRAM_STATUSES)),
        "cohort_statuses": sorted(list(INTERNSHIP_COHORT_STATUSES)),
        "cohort_member_roles": sorted(list(INTERNSHIP_COHORT_MEMBER_ROLES)),
    })


@internship_bp.get("/internship/programs")
@require_role("viewer")
def list_programs():
    error = check_feature_enabled()
    if error:
        return error

    query = InternshipProgram.query
    status = request.args.get("status")
    search = request.args.get("search")

    if status:
        query = query.filter(InternshipProgram.status == status)
    if search:
        pattern = f"%{search}%"
        query = query.filter(
            or_(
                InternshipProgram.name.ilike(pattern),
                InternshipProgram.description.ilike(pattern),
            )
        )

    query = query.order_by(InternshipProgram.created_at.desc())
    page = request.args.get("page", 1, type=int)
    page_size = min(request.args.get("page_size", 20, type=int), 100)
    pagination = query.paginate(page=page, per_page=page_size, error_out=False)

    return jsonify({
        "items": [item.to_dict() for item in pagination.items],
        "total": pagination.total,
        "page": pagination.page,
        "page_size": pagination.per_page,
        "pages": pagination.pages,
    })


@internship_bp.post("/internship/programs")
@require_role("people_manager")
def create_program():
    error = check_feature_enabled()
    if error:
        return error

    actor = request.current_user
    data = request.get_json() or {}
    errors = []

    name = (data.get("name") or "").strip()
    if not name:
        errors.append("name is required")
    if data.get("status") and data["status"] not in INTERNSHIP_PROGRAM_STATUSES:
        errors.append(f"status must be one of: {', '.join(sorted(INTERNSHIP_PROGRAM_STATUSES))}")

    if errors:
        return _validation_error(errors)

    try:
        start_date = _parse_date(data.get("start_date"), "start_date")
        end_date = _parse_date(data.get("end_date"), "end_date")
    except ValueError as exc:
        return _validation_error([str(exc)])

    program = InternshipProgram(
        name=name,
        description=data.get("description"),
        start_date=start_date,
        end_date=end_date,
        status=data.get("status", "planned"),
        created_by_id=actor.id,
    )
    db.session.add(program)
    db.session.commit()

    log_action(
        action="internship.program_created",
        actor=actor,
        target_type="internship_program",
        target_id=program.id,
        target_label=program.name,
        details={"status": program.status},
    )
    return jsonify({"message": "Program created", "program": program.to_dict()}), 201


@internship_bp.patch("/internship/programs/<int:program_id>")
@require_role("people_manager")
def update_program(program_id):
    error = check_feature_enabled()
    if error:
        return error

    actor = request.current_user
    program = InternshipProgram.query.get_or_404(program_id)
    data = request.get_json() or {}
    changes = {}

    allowed_fields = {"name", "description", "start_date", "end_date", "status"}
    unexpected = sorted(set(data.keys()) - allowed_fields)
    if unexpected:
        return _validation_error([f"Unexpected fields: {', '.join(unexpected)}"])

    if "status" in data and data["status"] not in INTERNSHIP_PROGRAM_STATUSES:
        return _validation_error([f"status must be one of: {', '.join(sorted(INTERNSHIP_PROGRAM_STATUSES))}"])

    if "start_date" in data:
        try:
            parsed = _parse_date(data.get("start_date"), "start_date")
        except ValueError as exc:
            return _validation_error([str(exc)])
        if program.start_date != parsed:
            changes["start_date"] = {"from": program.start_date.isoformat() if program.start_date else None, "to": parsed.isoformat() if parsed else None}
            program.start_date = parsed

    if "end_date" in data:
        try:
            parsed = _parse_date(data.get("end_date"), "end_date")
        except ValueError as exc:
            return _validation_error([str(exc)])
        if program.end_date != parsed:
            changes["end_date"] = {"from": program.end_date.isoformat() if program.end_date else None, "to": parsed.isoformat() if parsed else None}
            program.end_date = parsed

    for field in ("name", "description", "status"):
        if field in data:
            value = data[field]
            if field == "name" and isinstance(value, str):
                value = value.strip()
            if getattr(program, field) != value:
                changes[field] = {"from": getattr(program, field), "to": value}
                setattr(program, field, value)

    if not changes:
        return jsonify({"message": "No changes made", "program": program.to_dict(), "changes": {}})

    db.session.commit()
    log_action(
        action="internship.program_updated",
        actor=actor,
        target_type="internship_program",
        target_id=program.id,
        target_label=program.name,
        details={"changes": changes},
    )
    return jsonify({"message": "Program updated", "program": program.to_dict(), "changes": changes})


@internship_bp.get("/internship/cohorts")
@require_role("viewer")
def list_cohorts():
    error = check_feature_enabled()
    if error:
        return error

    query = InternshipCohort.query
    program_id = request.args.get("program_id", type=int)
    status = request.args.get("status")
    track = request.args.get("track")

    if program_id:
        query = query.filter(InternshipCohort.program_id == program_id)
    if status:
        query = query.filter(InternshipCohort.status == status)
    if track:
        query = query.filter(InternshipCohort.track == track)

    query = query.order_by(InternshipCohort.created_at.desc())
    page = request.args.get("page", 1, type=int)
    page_size = min(request.args.get("page_size", 20, type=int), 100)
    pagination = query.paginate(page=page, per_page=page_size, error_out=False)

    return jsonify({
        "items": [item.to_dict() for item in pagination.items],
        "total": pagination.total,
        "page": pagination.page,
        "page_size": pagination.per_page,
        "pages": pagination.pages,
    })


@internship_bp.post("/internship/cohorts")
@require_role("people_manager")
def create_cohort():
    error = check_feature_enabled()
    if error:
        return error

    actor = request.current_user
    data = request.get_json() or {}
    errors = []

    program_id = data.get("program_id")
    if not isinstance(program_id, int):
        errors.append("program_id is required")
    elif not InternshipProgram.query.get(program_id):
        errors.append("program_id not found")

    name = (data.get("name") or "").strip()
    track = (data.get("track") or "").strip()
    if not name:
        errors.append("name is required")
    if not track:
        errors.append("track is required")
    if data.get("status") and data["status"] not in INTERNSHIP_COHORT_STATUSES:
        errors.append(f"status must be one of: {', '.join(sorted(INTERNSHIP_COHORT_STATUSES))}")

    if errors:
        return _validation_error(errors)

    try:
        start_date = _parse_date(data.get("start_date"), "start_date")
        end_date = _parse_date(data.get("end_date"), "end_date")
    except ValueError as exc:
        return _validation_error([str(exc)])

    cohort = InternshipCohort(
        program_id=program_id,
        name=name,
        department=data.get("department"),
        track=track,
        specialization=data.get("specialization"),
        status=data.get("status", "active"),
        start_date=start_date,
        end_date=end_date,
        created_by_id=actor.id,
    )
    db.session.add(cohort)
    db.session.commit()

    log_action(
        action="internship.cohort_created",
        actor=actor,
        target_type="internship_cohort",
        target_id=cohort.id,
        target_label=cohort.name,
        details={"program_id": cohort.program_id, "track": cohort.track, "status": cohort.status},
    )
    return jsonify({"message": "Cohort created", "cohort": cohort.to_dict()}), 201


@internship_bp.patch("/internship/cohorts/<int:cohort_id>")
@require_role("people_manager")
def update_cohort(cohort_id):
    error = check_feature_enabled()
    if error:
        return error

    actor = request.current_user
    cohort = InternshipCohort.query.get_or_404(cohort_id)
    data = request.get_json() or {}
    allowed_fields = {"name", "department", "track", "specialization", "status", "start_date", "end_date"}
    unexpected = sorted(set(data.keys()) - allowed_fields)
    if unexpected:
        return _validation_error([f"Unexpected fields: {', '.join(unexpected)}"])

    if "status" in data and data["status"] not in INTERNSHIP_COHORT_STATUSES:
        return _validation_error([f"status must be one of: {', '.join(sorted(INTERNSHIP_COHORT_STATUSES))}"])

    changes = {}

    if "start_date" in data:
        try:
            parsed = _parse_date(data.get("start_date"), "start_date")
        except ValueError as exc:
            return _validation_error([str(exc)])
        if cohort.start_date != parsed:
            changes["start_date"] = {"from": cohort.start_date.isoformat() if cohort.start_date else None, "to": parsed.isoformat() if parsed else None}
            cohort.start_date = parsed

    if "end_date" in data:
        try:
            parsed = _parse_date(data.get("end_date"), "end_date")
        except ValueError as exc:
            return _validation_error([str(exc)])
        if cohort.end_date != parsed:
            changes["end_date"] = {"from": cohort.end_date.isoformat() if cohort.end_date else None, "to": parsed.isoformat() if parsed else None}
            cohort.end_date = parsed

    for field in ("name", "track", "status", "department", "specialization"):
        if field in data:
            value = data[field]
            if field in {"name", "track", "department", "specialization"} and isinstance(value, str):
                value = value.strip()
            if getattr(cohort, field) != value:
                changes[field] = {"from": getattr(cohort, field), "to": value}
                setattr(cohort, field, value)

    if not changes:
        return jsonify({"message": "No changes made", "cohort": cohort.to_dict(), "changes": {}})

    db.session.commit()
    log_action(
        action="internship.cohort_updated",
        actor=actor,
        target_type="internship_cohort",
        target_id=cohort.id,
        target_label=cohort.name,
        details={"changes": changes},
    )
    return jsonify({"message": "Cohort updated", "cohort": cohort.to_dict(), "changes": changes})


@internship_bp.get("/internship/cohorts/<int:cohort_id>/members")
@require_role("viewer")
def list_cohort_members(cohort_id):
    error = check_feature_enabled()
    if error:
        return error

    cohort = InternshipCohort.query.get_or_404(cohort_id)
    members = (
        InternshipCohortMember.query
        .filter_by(cohort_id=cohort.id)
        .order_by(InternshipCohortMember.created_at.desc())
        .all()
    )
    return jsonify({"cohort": cohort.to_dict(), "items": [m.to_dict() for m in members], "total": len(members)})


@internship_bp.post("/internship/cohorts/<int:cohort_id>/members")
@require_role("people_manager")
def add_cohort_member(cohort_id):
    error = check_feature_enabled()
    if error:
        return error

    actor = request.current_user
    cohort = InternshipCohort.query.get_or_404(cohort_id)
    data = request.get_json() or {}

    person_id = data.get("person_id")
    role = data.get("role", "intern")

    if not isinstance(person_id, int):
        return _validation_error(["person_id is required"])
    if role not in INTERNSHIP_COHORT_MEMBER_ROLES:
        return _validation_error([f"role must be one of: {', '.join(sorted(INTERNSHIP_COHORT_MEMBER_ROLES))}"])

    person = Person.query.get(person_id)
    if not person:
        return _validation_error(["person_id not found"])

    if actor.role == "people_manager":
        allowed, reason = can_manage_person(actor, person)
        if not allowed:
            return jsonify({"error": reason, "code": "INSUFFICIENT_PERMISSIONS"}), 403

    membership = InternshipCohortMember.query.filter_by(cohort_id=cohort.id, person_id=person.id, role=role).first()
    if membership:
        return jsonify({"message": "Member already assigned", "membership": membership.to_dict()})

    membership = InternshipCohortMember(
        cohort_id=cohort.id,
        person_id=person.id,
        role=role,
        created_by_id=actor.id,
    )
    db.session.add(membership)
    db.session.commit()

    log_action(
        action="internship.cohort_member_added",
        actor=actor,
        target_type="internship_cohort",
        target_id=cohort.id,
        target_label=cohort.name,
        details={"person_id": person.id, "person_name": person.full_name, "role": role},
    )
    return jsonify({"message": "Cohort member added", "membership": membership.to_dict()}), 201


@internship_bp.delete("/internship/cohorts/<int:cohort_id>/members/<int:member_id>")
@require_role("people_manager")
def remove_cohort_member(cohort_id, member_id):
    error = check_feature_enabled()
    if error:
        return error

    actor = request.current_user
    cohort = InternshipCohort.query.get_or_404(cohort_id)
    membership = InternshipCohortMember.query.filter_by(id=member_id, cohort_id=cohort.id).first_or_404()

    db.session.delete(membership)
    db.session.commit()

    log_action(
        action="internship.cohort_member_removed",
        actor=actor,
        target_type="internship_cohort",
        target_id=cohort.id,
        target_label=cohort.name,
        details={"member_id": member_id, "person_id": membership.person_id},
    )
    return jsonify({"message": "Cohort member removed", "member_id": member_id})


@internship_bp.get("/internship/onboarding/templates")
@require_role("viewer")
def list_onboarding_templates():
    error = check_feature_enabled()
    if error:
        return error

    query = OnboardingTemplateItem.query
    active_only = request.args.get("active_only")
    if active_only is not None:
        query = query.filter(OnboardingTemplateItem.is_active == (active_only.lower() == "true"))

    items = query.order_by(OnboardingTemplateItem.created_at.asc()).all()
    return jsonify({"items": [item.to_dict() for item in items], "total": len(items)})


@internship_bp.post("/internship/onboarding/templates")
@require_role("people_manager")
def create_onboarding_template():
    error = check_feature_enabled()
    if error:
        return error

    actor = request.current_user
    data = request.get_json() or {}

    title = (data.get("title") or "").strip()
    if not title:
        return _validation_error(["title is required"])

    item = OnboardingTemplateItem(
        title=title,
        description=data.get("description"),
        is_active=bool(data.get("is_active", True)),
        role_target=data.get("role_target", "intern"),
        owner_role=data.get("owner_role", "intern"),
        days_to_complete=int(data.get("days_to_complete", 7)),
        created_by_id=actor.id,
    )
    db.session.add(item)
    db.session.commit()

    log_action(
        action="internship.onboarding_template_created",
        actor=actor,
        target_type="onboarding_template_item",
        target_id=item.id,
        target_label=item.title,
        details={"is_active": item.is_active},
    )
    return jsonify({"message": "Onboarding template item created", "item": item.to_dict()}), 201


@internship_bp.patch("/internship/onboarding/templates/<int:item_id>")
@require_role("people_manager")
def update_onboarding_template(item_id):
    error = check_feature_enabled()
    if error:
        return error

    actor = request.current_user
    item = OnboardingTemplateItem.query.get_or_404(item_id)
    data = request.get_json() or {}
    allowed_fields = {"title", "description", "is_active", "role_target", "owner_role", "days_to_complete"}
    unexpected = sorted(set(data.keys()) - allowed_fields)
    if unexpected:
        return _validation_error([f"Unexpected fields: {', '.join(unexpected)}"])

    changes = {}
    for field in allowed_fields:
        if field not in data:
            continue
        value = data[field]
        if field == "title" and isinstance(value, str):
            value = value.strip()
        if getattr(item, field) != value:
            changes[field] = {"from": getattr(item, field), "to": value}
            setattr(item, field, value)

    if not changes:
        return jsonify({"message": "No changes made", "item": item.to_dict(), "changes": {}})

    db.session.commit()
    log_action(
        action="internship.onboarding_template_updated",
        actor=actor,
        target_type="onboarding_template_item",
        target_id=item.id,
        target_label=item.title,
        details={"changes": changes},
    )
    return jsonify({"message": "Onboarding template updated", "item": item.to_dict(), "changes": changes})


def _build_onboarding_payload(person):
    # Mirror the initialize filtering: only templates targeting this person's
    # role count toward the radar, so creating a template for another role
    # doesn't drop everyone's progress percentage.
    employment = person.active_employment
    employment_type = employment.employment_type if employment else "intern"
    role_key = "intern" if employment_type == "intern" else "employee"
    templates = [
        t for t in OnboardingTemplateItem.query.filter_by(is_active=True).order_by(OnboardingTemplateItem.created_at.asc()).all()
        if t.role_target in (role_key, employment_type, "all")
    ]
    checks = {
        c.template_item_id: c
        for c in PersonOnboardingItem.query.filter_by(person_id=person.id).all()
    }

    items = []
    done = 0
    for template in templates:
        check = checks.get(template.id)
        checked = bool(check.checked) if check else False
        if checked:
            done += 1
        items.append({
            "id": check.id if check else None,
            "template_item_id": template.id,
            "title": template.title,
            "description": template.description,
            "checked": checked,
            "checked_at": check.checked_at.isoformat() if (check and check.checked_at) else None,
            "due_date": check.due_date.isoformat() if (check and check.due_date) else None,
            "status": check.status if check else "pending",
            "item_type": check.item_type if check else "general",
            "owner_role": template.owner_role,
            "updated_at": check.updated_at.isoformat() if check else None,
            "updated_by_id": check.updated_by_id if check else None,
        })

    total = len(items)
    progress_percent = round((done / total) * 100) if total else 0
    return {
        "items": items,
        "done": done,
        "total": total,
        "progress_percent": progress_percent,
    }


@internship_bp.get("/internship/people/<int:person_id>/onboarding")
@require_role("viewer")
def get_person_onboarding(person_id):
    error = check_feature_enabled()
    if error:
        return error

    actor = request.current_user
    person = Person.query.get_or_404(person_id)
    if not _can_view_person_internship(actor, person):
        return jsonify({"error": "Insufficient permissions", "code": "INSUFFICIENT_PERMISSIONS"}), 403

    payload = _build_onboarding_payload(person)
    payload["person"] = person.to_dict()
    return jsonify(payload)


@internship_bp.put("/internship/people/<int:person_id>/onboarding/<int:template_item_id>/check")
@require_role("viewer")
def update_person_onboarding_check(person_id, template_item_id):
    error = check_feature_enabled()
    if error:
        return error

    actor = request.current_user
    person = Person.query.get_or_404(person_id)
    allowed, reason = _can_update_person_internship(actor, person)
    if not allowed:
        return jsonify({"error": reason or "Insufficient permissions", "code": "INSUFFICIENT_PERMISSIONS"}), 403

    template_item = OnboardingTemplateItem.query.get_or_404(template_item_id)
    if not template_item.is_active:
        return _validation_error(["Cannot update an inactive onboarding template item"])

    data = request.get_json() or {}
    if "checked" not in data or not isinstance(data["checked"], bool):
        return _validation_error(["checked (boolean) is required"])

    record = PersonOnboardingItem.query.filter_by(person_id=person.id, template_item_id=template_item.id).first()
    if not record:
        record = PersonOnboardingItem(
            person_id=person.id,
            template_item_id=template_item.id,
            checked=False,
        )
        db.session.add(record)
        db.session.flush()

    record.checked = data["checked"]
    record.checked_at = datetime.utcnow() if record.checked else None
    record.updated_by_id = actor.id
    db.session.commit()

    log_action(
        action="internship.onboarding_check_updated",
        actor=actor,
        target_type="person",
        target_id=person.id,
        target_label=person.full_name,
        details={"template_item_id": template_item.id, "checked": record.checked},
    )
    return jsonify({"message": "Onboarding progress updated", "check": record.to_dict()})


@internship_bp.get("/internship/people/<int:person_id>/completion")
@require_role("viewer")
def get_completion(person_id):
    error = check_feature_enabled()
    if error:
        return error

    actor = request.current_user
    person = Person.query.get_or_404(person_id)
    if not _can_view_person_internship(actor, person):
        return jsonify({"error": "Insufficient permissions", "code": "INSUFFICIENT_PERMISSIONS"}), 403

    checklist = InternshipCompletionChecklist.query.filter_by(person_id=person.id).first()
    if not checklist:
        checklist = InternshipCompletionChecklist(person_id=person.id)
        db.session.add(checklist)
        db.session.commit()

    return jsonify({"person": person.to_dict(), "checklist": checklist.to_dict()})


@internship_bp.put("/internship/people/<int:person_id>/completion")
@require_role("people_manager")
def update_completion(person_id):
    error = check_feature_enabled()
    if error:
        return error

    actor = request.current_user
    person = Person.query.get_or_404(person_id)
    allowed, reason = _can_update_person_internship(actor, person)
    if not allowed:
        return jsonify({"error": reason or "Insufficient permissions", "code": "INSUFFICIENT_PERMISSIONS"}), 403

    data = request.get_json() or {}
    allowed_fields = {"project_submitted", "evaluation_done", "admin_validated"}
    unexpected = sorted(set(data.keys()) - allowed_fields)
    if unexpected:
        return _validation_error([f"Unexpected fields: {', '.join(unexpected)}"])

    checklist = InternshipCompletionChecklist.query.filter_by(person_id=person.id).first()
    if not checklist:
        checklist = InternshipCompletionChecklist(person_id=person.id)
        db.session.add(checklist)
        db.session.flush()

    changes = {}
    for field in allowed_fields:
        if field not in data:
            continue
        if not isinstance(data[field], bool):
            return _validation_error([f"{field} must be boolean"])
        old_value = getattr(checklist, field)
        new_value = data[field]
        if old_value != new_value:
            setattr(checklist, field, new_value)
            changes[field] = {"from": old_value, "to": new_value}

    if not changes:
        return jsonify({"message": "No changes made", "checklist": checklist.to_dict(), "changes": {}})

    checklist.updated_by_id = actor.id
    db.session.commit()

    log_action(
        action="internship.completion_updated",
        actor=actor,
        target_type="person",
        target_id=person.id,
        target_label=person.full_name,
        details={"changes": changes},
    )
    return jsonify({"message": "Completion checklist updated", "checklist": checklist.to_dict(), "changes": changes})


@internship_bp.get("/internship/people/<int:person_id>/certificates")
@require_role("viewer")
def list_person_certificates(person_id):
    error = check_feature_enabled()
    if error:
        return error

    actor = request.current_user
    person = Person.query.get_or_404(person_id)
    if not _can_view_person_internship(actor, person):
        return jsonify({"error": "Insufficient permissions", "code": "INSUFFICIENT_PERMISSIONS"}), 403

    items = (
        InternshipCertificate.query
        .filter_by(person_id=person.id)
        .order_by(InternshipCertificate.issued_at.desc())
        .all()
    )
    return jsonify({"person": person.to_dict(), "items": [item.to_dict() for item in items], "total": len(items)})


@internship_bp.post("/internship/people/<int:person_id>/certificate")
@require_role("people_manager")
def issue_person_certificate(person_id):
    error = check_feature_enabled()
    if error:
        return error

    actor = request.current_user
    person = Person.query.get_or_404(person_id)
    allowed, reason = _can_update_person_internship(actor, person)
    if not allowed:
        return jsonify({"error": reason or "Insufficient permissions", "code": "INSUFFICIENT_PERMISSIONS"}), 403

    checklist = InternshipCompletionChecklist.query.filter_by(person_id=person.id).first()
    if not checklist or not checklist.admin_validated:
        return _validation_error(["Completion checklist must be admin_validated before issuing certificate"])

    data = request.get_json() or {}

    from app.routes.governance import check_policy

    requires_approval, _policy, approval_request = check_policy(
        action="people.issue_certificate",
        actor=actor,
        target_type="person",
        target_id=person.id,
        target_label=person.full_name,
        request_data={
            "person_id": person.id,
            "pdf_url": data.get("pdf_url"),
        },
    )

    if requires_approval and approval_request:
        return jsonify({
            "message": "Approval required for certificate issuance",
            "code": "APPROVAL_REQUIRED",
            "approval_request": approval_request.to_dict(),
        }), 202

    certificate = _issue_certificate(person, actor, pdf_url=data.get("pdf_url"))
    return jsonify({"message": "Certificate issued", "certificate": certificate.to_dict()}), 201

@internship_bp.get("/internship/cohort-analysis")
@require_role("people_manager")
def cohort_analysis():
    error = check_feature_enabled()
    if error:
        return error

    
    # We will build batch analytics focusing on Cohort performance and retention
    # This combines InternshipCohort, InternshipCohortMember
    cohorts = InternshipCohort.query.all()
    results = []
    for c in cohorts:
        members = InternshipCohortMember.query.filter_by(cohort_id=c.id).all()
        total_interns = len(members)
        if total_interns == 0:
            continue
            
        active_interns = sum(1 for m in members if m.person.active_employment and m.person.active_employment.status == "active")
        withdrawn = sum(1 for m in members if m.person.active_employment and m.person.active_employment.status in ("terminated", "withdrawn"))
        completed = sum(1 for m in members if m.person.active_employment and m.person.active_employment.status == "completed")
        
        retention = round((active_interns + completed) / total_interns * 100, 1) if total_interns > 0 else 0
        
        # Calculate payment compliance
        paid_ok = 0
        for m in members:
            emp = m.person.active_employment
            if emp and emp.payment_status in ("paid", "cleared"):
                paid_ok += 1

        payment_compliance = round(paid_ok / total_interns * 100, 1) if total_interns > 0 else 0
                    
        # Check-ins count
        total_checkins = 0
        from app.models import PerformanceCheckin
        for m in members:
            total_checkins += PerformanceCheckin.query.filter_by(person_id=m.person_id).count()

        results.append({
            "cohort_id": c.id,
            "cohort_name": c.name,
            "department": c.department,
            "specialization": c.specialization,
            "program_id": c.program_id,
            "total_interns": total_interns,
            "active_interns": active_interns,
            "withdrawn_interns": withdrawn,
            "completed_interns": completed,
            "retention_rate_pct": retention,
            "payment_compliance_pct": payment_compliance,
            "total_checkins": total_checkins,
            "average_completion": round((completed / total_interns) * 100, 1) if total_interns > 0 else 0
        })

    return jsonify({"cohort_analytics": results})


@internship_bp.post("/internship/people/<int:person_id>/onboarding/initialize")
@require_role("people_manager")
def initialize_person_onboarding(person_id):
    error = check_feature_enabled()
    if error:
        return error

    actor = request.current_user
    person = Person.query.get_or_404(person_id)
    allowed, reason = _can_update_person_internship(actor, person)
    if not allowed:
        return jsonify({"error": reason or "Insufficient permissions", "code": "INSUFFICIENT_PERMISSIONS"}), 403

    # Fetch active employment to know start date and which templates apply
    employment = person.active_employment
    start_date = employment.start_date if (employment and employment.start_date) else datetime.utcnow().date()

    # Only apply active template items targeting this person's role.
    # People without an employment record default to the intern checklist.
    employment_type = employment.employment_type if employment else "intern"
    role_key = "intern" if employment_type == "intern" else "employee"
    templates = [
        t for t in OnboardingTemplateItem.query.filter_by(is_active=True).all()
        if t.role_target in (role_key, employment_type, "all")
    ]
    
    initialized_count = 0
    from datetime import timedelta
    for t in templates:
        existing = PersonOnboardingItem.query.filter_by(person_id=person.id, template_item_id=t.id).first()
        if not existing:
            due_date = start_date + timedelta(days=t.days_to_complete)
            item = PersonOnboardingItem(
                person_id=person.id,
                template_item_id=t.id,
                checked=False,
                due_date=due_date,
                status="pending",
                item_type="general",
            )
            db.session.add(item)
            initialized_count += 1
            
    db.session.commit()
    
    from app.utils.integrations_mock import send_email_notification
    send_email_notification(
        email=person.email,
        template_type="onboarding_initialized",
        context={"name": person.full_name, "count": initialized_count}
    )
    
    log_action(
        action="internship.onboarding_initialized",
        actor=actor,
        target_type="person",
        target_id=person.id,
        target_label=person.full_name,
        details={"count": initialized_count},
    )
    
    return jsonify({"message": f"Initialized onboarding checklist with {initialized_count} items."}), 201


@internship_bp.patch("/internship/onboarding-item/<int:item_id>")
@require_active_user
def patch_person_onboarding_item(item_id):
    error = check_feature_enabled()
    if error:
        return error

    actor = request.current_user
    item = PersonOnboardingItem.query.get_or_404(item_id)
    person = item.person

    data = request.get_json() or {}

    allowed, reason = _can_update_person_internship(actor, person)
    if not allowed:
        # Self-service: people may update completion state on their own items
        # when the checklist item is owned by them (owner_role == "intern").
        template = item.template_item
        is_self_service = (
            person.user_id == actor.id
            and template is not None
            and template.owner_role == "intern"
        )
        if not is_self_service:
            return jsonify({"error": reason or "Insufficient permissions", "code": "INSUFFICIENT_PERMISSIONS"}), 403
        extra = sorted(set(data.keys()) - {"checked", "status"})
        if extra:
            return _validation_error([f"You can only update checked/status on your own items (not: {', '.join(extra)})"])

    if "status" in data and data["status"] not in {"pending", "in_progress", "completed", "overdue"}:
        return _validation_error(["status must be one of: pending, in_progress, completed, overdue"])

    if "checked" in data:
        item.checked = bool(data["checked"])
        item.checked_at = datetime.utcnow() if item.checked else None
        item.status = "completed" if item.checked else "pending"
    if "status" in data:
        item.status = data["status"]
    if "due_date" in data:
        try:
            item.due_date = _parse_date(data["due_date"], "due_date")
        except ValueError as exc:
            return _validation_error([str(exc)])
    if "item_type" in data:
        item.item_type = data["item_type"]
        
    item.updated_by_id = actor.id
    db.session.commit()
    
    log_action(
        action="internship.onboarding_item_patched",
        actor=actor,
        target_type="person",
        target_id=person.id,
        target_label=person.full_name,
        details={"item_id": item.id, "checked": item.checked, "status": item.status},
    )
    
    return jsonify({"message": "Onboarding item updated", "item": item.to_dict()})


@internship_bp.get("/internship/reviews/biweekly")
@require_role("viewer")
def list_biweekly_reviews():
    error = check_feature_enabled()
    if error:
        return error
        
    actor = request.current_user
    person_id = request.args.get("person_id", type=int)
    query = BiweeklyReview.query
    if person_id:
        person = Person.query.get_or_404(person_id)
        if not _can_view_person_internship(actor, person):
            return jsonify({"error": "Insufficient permissions", "code": "INSUFFICIENT_PERMISSIONS"}), 403
        query = query.filter(BiweeklyReview.person_id == person_id)

    reviews = query.order_by(BiweeklyReview.period_end.desc()).all()
    if not person_id:
        reviews = [r for r in reviews if _can_view_person_internship(actor, r.person)]
    return jsonify({"items": [r.to_dict() for r in reviews]})


@internship_bp.post("/internship/reviews/biweekly")
@require_role("people_manager")
def create_biweekly_review():
    error = check_feature_enabled()
    if error:
        return error
        
    actor = request.current_user
    data = request.get_json() or {}
    person_id = data.get("person_id")
    if not isinstance(person_id, int):
        return _validation_error(["person_id is required"])
    person = Person.query.get_or_404(person_id)

    allowed, reason = _can_update_person_internship(actor, person)
    if not allowed:
        return jsonify({"error": reason or "Insufficient permissions", "code": "INSUFFICIENT_PERMISSIONS"}), 403

    try:
        period_start = _parse_date(data.get("period_start"), "period_start")
        period_end = _parse_date(data.get("period_end"), "period_end")
    except ValueError as exc:
        return _validation_error([str(exc)])

    if not period_start or not period_end:
        return _validation_error(["period_start and period_end are required (YYYY-MM-DD)"])
    if period_start > period_end:
        return _validation_error(["period_start must be on or before period_end"])

    overlapping = BiweeklyReview.query.filter(
        BiweeklyReview.person_id == person.id,
        BiweeklyReview.period_start <= period_end,
        BiweeklyReview.period_end >= period_start,
    ).first()
    if overlapping:
        return _validation_error([
            f"A biweekly review already exists for an overlapping period ({overlapping.period_start} to {overlapping.period_end})"
        ])

    track_name = "general"
    emp = person.active_employment
    if emp and emp.intern_track:
        track_name = emp.intern_track
        
    manager_questions_by_track = {
        "software": [
            "How well did they apply clean code principles in their commits this sprint?",
            "Are they showing autonomy in debugging issue tasks?",
            "Ask them: What technical design pattern did they implement recently?"
        ],
        "devops": [
            "Did they verify CI/CD execution pipeline performance?",
            "How did they handle secret credentials storage safely?",
            "Ask them: What was the main infrastructure bottleneck they noticed?"
        ],
        "devsecops_cybersecurity": [
            "Did they perform static application safety testing audits?",
            "Did they review Nginx configuration security headers?",
            "Ask them: What vulnerability did they locate and mitigate?"
        ],
        "ai_ml": [
            "How did they handle multimodal structured prompts inference?",
            "Did they evaluate the accuracy/LCP metrics of generated UI?",
            "Ask them: How did you validate prompt templates locally?"
        ]
    }
    
    questions = manager_questions_by_track.get(track_name, [
        "What was their primary contribution during this review period?",
        "Are they meeting the objectives set in the onboarding roadmap?",
        "Ask them: What can we do to help clear any current blockers?"
    ])
    
    review = BiweeklyReview(
        person_id=person.id,
        period_start=period_start,
        period_end=period_end,
        status="pending_intern",
        manager_questions=questions,
        intern_responses={},
        manager_responses={},
    )
    
    db.session.add(review)
    db.session.commit()
    
    from app.utils.integrations_mock import send_mattermost_notification, send_email_notification
    if person.mattermost_username:
        send_mattermost_notification(
            username=person.mattermost_username,
            template_type="review_reminder",
            context={}
        )
    send_email_notification(
        email=person.email,
        template_type="biweekly_reminder",
        context={"name": person.full_name, "period_start": period_start.isoformat(), "period_end": period_end.isoformat()}
    )
    
    log_action(
        action="internship.review.biweekly_created",
        actor=request.current_user,
        target_type="person",
        target_id=person.id,
        target_label=person.full_name,
        details={"review_id": review.id},
    )
    
    return jsonify({"message": "Biweekly review period initialized", "review": review.to_dict()}), 201


@internship_bp.post("/internship/reviews/biweekly/<int:review_id>/intern-submit")
@require_active_user
def intern_submit_biweekly(review_id):
    error = check_feature_enabled()
    if error:
        return error
        
    review = BiweeklyReview.query.get_or_404(review_id)
    actor = request.current_user
    
    person = review.person
    if actor.role not in {"admin", "superadmin", "hr_admin"}:
        if person.user_id != actor.id:
            return jsonify({"error": "You can only submit responses for your own profile", "code": "ACCESS_DENIED"}), 403

    if review.status == "completed":
        return _validation_error(["This review is already completed and can no longer be edited"])

    data = request.get_json() or {}
    responses = data.get("responses")
    if not isinstance(responses, dict):
        return _validation_error(["responses dict is required"])
        
    review.intern_responses = responses

    # If a PoC/team lead is assigned, they review first and pass the report
    # to the manager; otherwise the review goes straight to the manager.
    emp = person.active_employment
    next_reviewer = emp.poc if (emp and emp.poc_person_id) else (emp.manager if emp else None)
    review.status = "pending_poc" if (emp and emp.poc_person_id) else "pending_manager"
    db.session.commit()

    from app.utils.integrations_mock import send_mattermost_notification, send_email_notification
    if next_reviewer:
        if next_reviewer.mattermost_username:
            send_mattermost_notification(
                username=next_reviewer.mattermost_username,
                template_type="manager_task",
                context={"intern_name": person.full_name}
            )
        send_email_notification(
            email=next_reviewer.email,
            template_type="manager_reminder",
            context={"intern_name": person.full_name}
        )
        notify_user(
            next_reviewer.user_id,
            "biweekly_ready_for_review",
            f"{person.full_name} submitted a biweekly reflection",
            body=f"Period {review.period_start} to {review.period_end} is ready for your {'assessment' if review.status == 'pending_poc' else 'review'}.",
            link=f"/ui/people/{person.id}",
            target_type="biweekly_review",
            target_id=review.id,
        )

    log_action(
        action="internship.review.intern_submitted",
        actor=actor,
        target_type="person",
        target_id=person.id,
        target_label=person.full_name,
        details={"review_id": review.id, "routed_to": review.status},
    )

    return jsonify({"message": "Intern responses saved successfully", "review": review.to_dict()})


@internship_bp.post("/internship/reviews/biweekly/<int:review_id>/poc-submit")
@require_role("mentor")
def poc_submit_biweekly(review_id):
    """PoC/team lead assessment step: grade the intern's reflection and pass
    the report on to the manager (status pending_poc -> pending_manager)."""
    error = check_feature_enabled()
    if error:
        return error

    review = BiweeklyReview.query.get_or_404(review_id)
    actor = request.current_user
    person = review.person

    # The assigned PoC, or anyone with manage rights (manager/HR/admin), may
    # record the PoC assessment.
    allowed, _reason = _can_update_person_internship(actor, person)
    if not allowed and not is_poc_for(actor, person):
        return jsonify({"error": "Only the assigned PoC or a manager can submit this assessment", "code": "INSUFFICIENT_PERMISSIONS"}), 403

    if review.status not in {"pending_poc", "pending_intern"}:
        return _validation_error(["This review is not awaiting a PoC assessment"])

    data = request.get_json() or {}
    score = data.get("score_progress")
    if score is None or not isinstance(score, int) or score < 1 or score > 5:
        return _validation_error(["score_progress must be an integer between 1 and 5"])

    review.score_progress = score
    review.blockers = data.get("blockers")
    review.strengths = data.get("strengths")
    review.action_items = data.get("action_items", [])
    review.poc_notes = data.get("notes")
    review.poc_reviewer_id = actor.id
    review.poc_submitted_at = datetime.utcnow()
    review.status = "pending_manager"
    db.session.commit()

    from app.utils.integrations_mock import send_mattermost_notification, send_email_notification
    emp = person.active_employment
    if emp and emp.manager:
        if emp.manager.mattermost_username:
            send_mattermost_notification(
                username=emp.manager.mattermost_username,
                template_type="manager_task",
                context={"intern_name": person.full_name}
            )
        send_email_notification(
            email=emp.manager.email,
            template_type="manager_reminder",
            context={"intern_name": person.full_name}
        )
        notify_user(
            emp.manager.user_id,
            "biweekly_ready_for_review",
            f"{actor.email} passed {person.full_name}'s biweekly review to you",
            body=f"Score {score}/5. Period {review.period_start} to {review.period_end}.",
            link=f"/ui/people/{person.id}",
            target_type="biweekly_review",
            target_id=review.id,
        )

    log_action(
        action="internship.review.poc_submitted",
        actor=actor,
        target_type="person",
        target_id=person.id,
        target_label=person.full_name,
        details={"review_id": review.id, "score": score},
    )

    return jsonify({"message": "PoC assessment recorded and passed to the manager", "review": review.to_dict()})


@internship_bp.post("/internship/reviews/biweekly/<int:review_id>/manager-submit")
@require_role("people_manager")
def manager_submit_biweekly(review_id):
    error = check_feature_enabled()
    if error:
        return error
        
    review = BiweeklyReview.query.get_or_404(review_id)
    actor = request.current_user

    allowed, reason = _can_update_person_internship(actor, review.person)
    if not allowed:
        return jsonify({"error": reason or "Insufficient permissions", "code": "INSUFFICIENT_PERMISSIONS"}), 403

    data = request.get_json() or {}
    score = data.get("score_progress")
    if score is None or not isinstance(score, int) or score < 1 or score > 5:
        return _validation_error(["score_progress must be an integer between 1 and 5"])
        
    review.score_progress = score
    review.reviewer_id = actor.id
    review.manager_responses = data.get("responses", {})
    review.blockers = data.get("blockers")
    review.strengths = data.get("strengths")
    review.action_items = data.get("action_items", [])
    
    intern_answers = " ".join(str(v) for v in (review.intern_responses or {}).values())
    blockers_text = review.blockers or ""
    strengths_text = review.strengths or ""
    
    poc_note = f" PoC assessment by {review.poc_reviewer.email}." if review.poc_reviewer else ""
    review.ai_summary = f"[DRAFT AI Summary] Intern reports: '{intern_answers[:100]}...'. Manager noted strengths: '{strengths_text}'. Key blocker identified: '{blockers_text}'. Score: {score}/5.{poc_note}"
    review.status = "completed"
    review.completed_at = datetime.utcnow()
    
    db.session.commit()
    
    log_action(
        action="internship.review.manager_submitted",
        actor=actor,
        target_type="person",
        target_id=review.person_id,
        target_label=review.person.full_name,
        details={"review_id": review.id, "score": score},
    )

    notify_user(
        review.person.user_id,
        "biweekly_completed",
        "Your biweekly review is complete",
        body=f"Score: {score}/5. Period {review.period_start} to {review.period_end}.",
        link="/ui/my-journey",
        target_type="biweekly_review",
        target_id=review.id,
    )

    return jsonify({"message": "Manager review completed", "review": review.to_dict()})


@internship_bp.get("/internship/reviews/milestone")
@require_role("viewer")
def list_milestone_reviews():
    error = check_feature_enabled()
    if error:
        return error
        
    actor = request.current_user
    person_id = request.args.get("person_id", type=int)
    query = MilestoneReview.query
    if person_id:
        person = Person.query.get_or_404(person_id)
        if not _can_view_person_internship(actor, person):
            return jsonify({"error": "Insufficient permissions", "code": "INSUFFICIENT_PERMISSIONS"}), 403
        query = query.filter(MilestoneReview.person_id == person_id)

    reviews = query.order_by(MilestoneReview.created_at.desc()).all()
    if not person_id:
        reviews = [r for r in reviews if _can_view_person_internship(actor, r.person)]
    return jsonify({"items": [r.to_dict() for r in reviews]})


@internship_bp.post("/internship/reviews/milestone/compile")
@require_role("people_manager")
def compile_milestone_review():
    error = check_feature_enabled()
    if error:
        return error
        
    actor = request.current_user
    data = request.get_json() or {}
    person_id = data.get("person_id")
    if not isinstance(person_id, int):
        return _validation_error(["person_id is required"])
    person = Person.query.get_or_404(person_id)
    review_type = data.get("review_type", "3_month")

    if review_type not in {"3_month", "6_month"}:
        return _validation_error(["review_type must be either 3_month or 6_month"])

    allowed, reason = _can_update_person_internship(actor, person)
    if not allowed:
        return jsonify({"error": reason or "Insufficient permissions", "code": "INSUFFICIENT_PERMISSIONS"}), 403
        
    existing = MilestoneReview.query.filter_by(person_id=person.id, review_type=review_type).first()
    if existing:
        return jsonify({"message": f"{review_type} review already exists", "review": existing.to_dict()})
        
    biweeklies = BiweeklyReview.query.filter_by(person_id=person.id, status="completed").all()
    scores = [r.score_progress for r in biweeklies if r.score_progress is not None]
    avg_score = round(sum(scores) / len(scores), 2) if scores else 3.0
    
    from app.models import PersonOnboardingItem
    onboarding_items = PersonOnboardingItem.query.filter_by(person_id=person.id).all()
    total_onboarding = len(onboarding_items)
    completed_onboarding = sum(1 for item in onboarding_items if item.checked)
    onboarding_pct = round((completed_onboarding / total_onboarding) * 100, 2) if total_onboarding else 0.0
    
    from app.utils.integrations_mock import get_taiga_activity
    taiga_summary = get_taiga_activity(person.taiga_username)
    
    mattermost_summary = {
        "username": person.mattermost_username or "unknown",
        "posts_count": 42 if person.mattermost_username else 0,
        "active_days": 10 if person.mattermost_username else 0,
    }
    
    ai_recs = f"[DRAFT AI RECOMMENDATION] Intern shows solid progress. Onboarding completed at {onboarding_pct}%. Suggesting conversion to full-time." if avg_score >= 4.0 else f"[DRAFT AI RECOMMENDATION] Performance is average ({avg_score}/5). Recommend extending internship cohort period."
    
    milestone = MilestoneReview(
        person_id=person.id,
        review_type=review_type,
        status="draft",
        compiled_score=avg_score,
        onboarding_progress=onboarding_pct,
        taiga_activity_summary=taiga_summary,
        mattermost_activity_summary=mattermost_summary,
        disciplinary_summary="No disciplinary incidents logged.",
        ai_recommendations=ai_recs,
        ai_recommendations_approved=False,
        report_card_json={
            "competencies": {
                "technical": round(avg_score * 0.9 + 0.3, 1),
                "communication": 4.0 if person.mattermost_username else 2.5,
                "velocity": round(avg_score, 1),
                "collaboration": 3.8,
                "problem_solving": round(avg_score - 0.2, 1),
            }
        }
    )
    
    db.session.add(milestone)
    db.session.commit()
    
    log_action(
        action="internship.review.milestone_compiled",
        actor=request.current_user,
        target_type="person",
        target_id=person.id,
        target_label=person.full_name,
        details={"review_type": review_type, "milestone_id": milestone.id},
    )
    
    return jsonify({"message": "Milestone review compiled", "review": milestone.to_dict()}), 201


@internship_bp.post("/internship/reviews/milestone/<int:review_id>/approve-ai")
@require_role("people_manager")
def approve_ai_milestone_recommendations(review_id):
    error = check_feature_enabled()
    if error:
        return error
        
    milestone = MilestoneReview.query.get_or_404(review_id)

    allowed, reason = _can_update_person_internship(request.current_user, milestone.person)
    if not allowed:
        return jsonify({"error": reason or "Insufficient permissions", "code": "INSUFFICIENT_PERMISSIONS"}), 403

    data = request.get_json(silent=True) or {}
    approved = data.get("approved", True)
    if not isinstance(approved, bool):
        return _validation_error(["approved must be a boolean"])

    # Approval can be granted or revoked freely while the review is a draft;
    # once released the decision is final.
    if milestone.status == "released":
        return _validation_error(["This milestone review has already been finalized"])

    milestone.ai_recommendations_approved = approved
    db.session.commit()

    log_action(
        action="internship.review.milestone_ai_approved" if approved else "internship.review.milestone_ai_approval_revoked",
        actor=request.current_user,
        target_type="person",
        target_id=milestone.person_id,
        target_label=milestone.person.full_name,
        details={"milestone_id": milestone.id, "approved": approved},
    )

    message = "AI recommendations approved by manager" if approved else "Draft approval revoked"
    return jsonify({"message": message, "review": milestone.to_dict()})


def _finalize_milestone(milestone, decision, actor):
    """Apply a final milestone decision. Callers must have validated permissions,
    decision value, and that the milestone is not already released."""
    milestone.final_decision = decision
    milestone.decision_by_id = actor.id
    milestone.decision_date = datetime.utcnow().date()
    milestone.status = "released"

    person = milestone.person
    emp = person.active_employment
    if emp:
        if decision == "convert":
            emp.employment_type = "full_time"
        elif decision == "extend":
            from datetime import timedelta
            if emp.end_date:
                emp.end_date = emp.end_date + timedelta(days=90)
        elif decision == "release":
            emp.status = "completed"
            emp.end_date = datetime.utcnow().date()

    db.session.commit()

    from app.utils.integrations_mock import send_email_notification
    send_email_notification(
        email=person.email,
        template_type="milestone_completed",
        context={"name": person.full_name, "review_type": milestone.review_type, "decision": decision}
    )

    log_action(
        action="internship.review.milestone_finalized",
        actor=actor,
        target_type="person",
        target_id=milestone.person_id,
        target_label=person.full_name,
        details={"milestone_id": milestone.id, "decision": decision},
    )

    notify_user(
        person.user_id,
        "milestone_decided",
        f"Your {milestone.review_type.replace('_', ' ')} milestone decision is in",
        body=f"Decision: {decision}.",
        link="/ui/my-journey",
        target_type="milestone_review",
        target_id=milestone.id,
    )

    return milestone


@internship_bp.post("/internship/reviews/milestone/<int:review_id>/finalize")
@require_role("people_manager")
def finalize_milestone_review(review_id):
    error = check_feature_enabled()
    if error:
        return error

    milestone = MilestoneReview.query.get_or_404(review_id)

    allowed, reason = _can_update_person_internship(request.current_user, milestone.person)
    if not allowed:
        return jsonify({"error": reason or "Insufficient permissions", "code": "INSUFFICIENT_PERMISSIONS"}), 403

    if milestone.status == "released":
        return _validation_error(["This milestone review has already been finalized"])

    if not milestone.ai_recommendations_approved:
        return _validation_error(["The draft recommendation must be reviewed and approved before finalizing"])

    data = request.get_json() or {}
    decision = data.get("decision")

    if decision not in {"convert", "extend", "reassign", "release"}:
        return _validation_error(["decision must be one of: convert, extend, reassign, release"])

    from app.routes.governance import check_policy

    requires_approval, _policy, approval_request = check_policy(
        action="people.finalize_milestone",
        actor=request.current_user,
        target_type="milestone_review",
        target_id=milestone.id,
        target_label=f"{milestone.review_type} review for {milestone.person.full_name}",
        request_data={"milestone_id": milestone.id, "decision": decision},
    )
    if requires_approval and approval_request:
        return jsonify({
            "message": "Approval required to finalize milestone decision",
            "code": "APPROVAL_REQUIRED",
            "approval_request": approval_request.to_dict(),
        }), 202

    milestone = _finalize_milestone(milestone, decision, request.current_user)
    return jsonify({"message": f"Milestone review finalized with decision: {decision}", "review": milestone.to_dict()})


# =============================================================================
# PHASE 2: INTERN SELF-SERVICE PORTAL + MANAGER OPS SUMMARY
# =============================================================================

def _intern_biweekly_view(review):
    """Biweekly review as shown to the intern it belongs to (no draft AI text)."""
    data = review.to_dict()
    data.pop("ai_summary", None)
    return data


def _intern_milestone_view(milestone):
    """Released milestone review as shown to the intern (no draft AI text or
    disciplinary notes — those are HR-internal)."""
    data = milestone.to_dict()
    data.pop("ai_recommendations", None)
    data.pop("ai_recommendations_approved", None)
    data.pop("disciplinary_summary", None)
    return data


@internship_bp.get("/internship/my-journey")
@require_active_user
def my_journey():
    """Self-service view for the logged-in user's own internship journey.
    Available to any authenticated active user, including role `user` interns."""
    error = check_feature_enabled()
    if error:
        return error

    actor = request.current_user
    person = Person.query.filter_by(user_id=actor.id).first()
    if not person:
        return jsonify({
            "linked": False,
            "profile": None,
            "onboarding": None,
            "biweekly_reviews": [],
            "milestone_reviews": [],
        })

    employment = person.active_employment
    profile = {
        "person_id": person.id,
        "full_name": person.full_name,
        "email": person.email,
        "team": person.team,
        "department": person.department,
        "cohort": person.cohort,
        "taiga_username": person.taiga_username,
        "mattermost_username": person.mattermost_username,
        "assigned_projects": person.assigned_projects or [],
        "employment": {
            "title": employment.title,
            "employment_type": employment.employment_type,
            "intern_track": employment.intern_track,
            "status": employment.status,
            "start_date": employment.start_date.isoformat() if employment.start_date else None,
            "end_date": employment.end_date.isoformat() if employment.end_date else None,
            "manager_name": employment.manager.full_name if employment.manager else None,
            "mentor_name": employment.mentor.full_name if employment.mentor else None,
        } if employment else None,
    }

    biweeklies = (
        BiweeklyReview.query.filter_by(person_id=person.id)
        .order_by(BiweeklyReview.period_end.desc())
        .all()
    )
    milestones = (
        MilestoneReview.query.filter_by(person_id=person.id, status="released")
        .order_by(MilestoneReview.created_at.desc())
        .all()
    )

    return jsonify({
        "linked": True,
        "profile": profile,
        "onboarding": _build_onboarding_payload(person),
        "biweekly_reviews": [_intern_biweekly_view(r) for r in biweeklies],
        "milestone_reviews": [_intern_milestone_view(m) for m in milestones],
    })


@internship_bp.get("/internship/ops-summary")
@require_role("mentor")
def internship_ops_summary():
    """Action center: pending grading, overdue reflections, overdue onboarding,
    draft milestone decisions, milestones due for compilation, and at-risk
    interns. HR admins/admins see the whole program; people_managers their
    direct reports; team leads (PoCs) and mentors the interns assigned to them."""
    error = check_feature_enabled()
    if error:
        return error

    from app.utils.people_rbac import get_person_for_user

    actor = request.current_user
    today = datetime.utcnow().date()

    unrestricted = is_hr_admin(actor) or actor.role == "admin"
    scoped_ids = None
    if not unrestricted:
        actor_person = get_person_for_user(actor.id)
        if not actor_person:
            return jsonify({
                "action_queue": [], "overdue_reflections": [], "overdue_onboarding": [],
                "pending_decisions": [], "milestones_due": [], "at_risk": [],
                "counts": {"action_queue": 0, "overdue_reflections": 0, "overdue_onboarding": 0,
                           "pending_decisions": 0, "milestones_due": 0, "at_risk": 0},
                "scope": "none", "message": "No linked person profile for your account",
            })
        # In scope: anyone whose active employment lists the actor as manager,
        # PoC, or mentor.
        scoped_ids = {
            e.person_id
            for e in Employment.query.filter(
                or_(
                    Employment.manager_person_id == actor_person.id,
                    Employment.poc_person_id == actor_person.id,
                    Employment.mentor_person_id == actor_person.id,
                )
            ).all()
            if e.person and e.person.active_employment and e.person.active_employment.id == e.id
        }

    def in_scope(person_id):
        return scoped_ids is None or person_id in scoped_ids

    def person_ref(person):
        emp = person.active_employment
        return {
            "person_id": person.id,
            "full_name": person.full_name,
            "email": person.email,
            "cohort": person.cohort,
            "intern_track": emp.intern_track if emp else None,
        }

    # 1. Biweekly reviews waiting on a reviewer — PoC assessments and manager
    # grading are both actionable; `stage` says which step each item is at.
    action_queue = [
        {**person_ref(r.person), "review_id": r.id,
         "stage": "poc" if r.status == "pending_poc" else "manager",
         "period_start": r.period_start.isoformat(), "period_end": r.period_end.isoformat()}
        for r in BiweeklyReview.query.filter(BiweeklyReview.status.in_(["pending_poc", "pending_manager"])).all()
        if in_scope(r.person_id)
    ]

    # 2. Intern reflections past their period end
    overdue_reflections = [
        {**person_ref(r.person), "review_id": r.id,
         "period_end": r.period_end.isoformat(),
         "days_overdue": (today - r.period_end).days}
        for r in BiweeklyReview.query.filter_by(status="pending_intern").all()
        if in_scope(r.person_id) and r.period_end < today
    ]

    # 3. Overdue onboarding items, grouped per person
    overdue_items = [
        i for i in PersonOnboardingItem.query.filter(
            PersonOnboardingItem.checked.is_(False),
            PersonOnboardingItem.due_date.isnot(None),
            PersonOnboardingItem.due_date < today,
        ).all()
        if in_scope(i.person_id)
    ]
    by_person = {}
    for i in overdue_items:
        entry = by_person.setdefault(i.person_id, {**person_ref(i.person), "overdue_count": 0, "items": []})
        entry["overdue_count"] += 1
        entry["items"].append({
            "item_id": i.id,
            "title": i.template_item.title if i.template_item else None,
            "due_date": i.due_date.isoformat(),
            "owner_role": i.template_item.owner_role if i.template_item else None,
        })
    overdue_onboarding = sorted(by_person.values(), key=lambda e: -e["overdue_count"])

    # 4. Draft milestone reviews awaiting a decision
    pending_decisions = [
        {**person_ref(m.person), "milestone_id": m.id, "review_type": m.review_type,
         "compiled_score": m.compiled_score,
         "ai_recommendations_approved": m.ai_recommendations_approved,
         "created_at": m.created_at.isoformat() if m.created_at else None}
        for m in MilestoneReview.query.filter_by(status="draft").all()
        if in_scope(m.person_id)
    ]

    # 5. Interns due for a milestone compilation (approaching 3/6 months in)
    milestones_due = []
    intern_employments = [
        e for e in Employment.query.filter_by(employment_type="intern", status="active").all()
        if in_scope(e.person_id) and e.person and e.person.active_employment
        and e.person.active_employment.id == e.id and e.start_date
    ]
    for e in intern_employments:
        days_in = (today - e.start_date).days
        existing_types = {m.review_type for m in MilestoneReview.query.filter_by(person_id=e.person_id).all()}
        due_type = None
        if days_in >= 170 and "6_month" not in existing_types:
            due_type = "6_month"
        elif days_in >= 80 and "3_month" not in existing_types:
            due_type = "3_month"
        if due_type:
            milestones_due.append({**person_ref(e.person), "due_type": due_type, "days_in_program": days_in})

    # 6. At-risk board: flagged interns or declining/low recent scores
    at_risk = []
    for e in intern_employments:
        person = e.person
        flags = person.risk_flags or []
        recent = (
            BiweeklyReview.query.filter_by(person_id=person.id, status="completed")
            .order_by(BiweeklyReview.period_end.desc())
            .limit(2)
            .all()
        )
        recent_scores = [r.score_progress for r in recent if r.score_progress is not None]
        low_score = bool(recent_scores) and (sum(recent_scores) / len(recent_scores)) <= 2.5
        if flags or low_score:
            at_risk.append({
                **person_ref(person),
                "risk_flags": flags,
                "recent_scores": recent_scores,
                "reasons": (["risk_flags"] if flags else []) + (["low_recent_scores"] if low_score else []),
            })

    return jsonify({
        "scope": "all" if unrestricted else "managed",
        "action_queue": action_queue,
        "overdue_reflections": overdue_reflections,
        "overdue_onboarding": overdue_onboarding,
        "pending_decisions": pending_decisions,
        "milestones_due": milestones_due,
        "at_risk": at_risk,
        "counts": {
            "action_queue": len(action_queue),
            "overdue_reflections": len(overdue_reflections),
            "overdue_onboarding": len(overdue_onboarding),
            "pending_decisions": len(pending_decisions),
            "milestones_due": len(milestones_due),
            "at_risk": len(at_risk),
        },
    })


# =============================================================================
# TEAM LEAD (PoC) ASSIGNMENTS
# =============================================================================

@internship_bp.get("/internship/team-lead-assignments")
@require_role("people_manager")
def list_team_lead_assignments():
    """Roster of every team_lead with the interns currently assigned to them,
    plus the list of unassigned interns. Admin/manager-only."""
    error = check_feature_enabled()
    if error:
        return error

    team_leads = User.query.filter_by(role="team_lead", is_active=True).order_by(User.email.asc()).all()
    lead_rows = []
    for lead in team_leads:
        lead_person = Person.query.filter_by(user_id=lead.id).first()
        assigned = []
        if lead_person:
            assigned = [
                {"person_id": e.person_id, "full_name": e.person.full_name, "email": e.person.email,
                 "intern_track": e.intern_track}
                for e in Employment.query.filter_by(poc_person_id=lead_person.id, employment_type="intern").all()
                if e.person and e.person.active_employment and e.person.active_employment.id == e.id
            ]
        lead_rows.append({
            "user_id": lead.id,
            "person_id": lead_person.id if lead_person else None,
            "full_name": lead_person.full_name if lead_person else lead.email,
            "email": lead.email,
            "assigned_interns": assigned,
        })

    unassigned = [
        {"person_id": e.person_id, "full_name": e.person.full_name, "email": e.person.email,
         "intern_track": e.intern_track}
        for e in Employment.query.filter_by(employment_type="intern", poc_person_id=None).all()
        if e.person and e.person.active_employment and e.person.active_employment.id == e.id
    ]

    return jsonify({"team_leads": lead_rows, "unassigned_interns": unassigned})


@internship_bp.put("/internship/people/<int:person_id>/poc")
@require_role("people_manager")
def assign_poc(person_id):
    """Assign or unassign the PoC/team lead for an intern's active employment."""
    error = check_feature_enabled()
    if error:
        return error

    person = Person.query.get_or_404(person_id)
    employment = person.active_employment
    if not employment or employment.employment_type != "intern":
        return _validation_error(["Only active intern employments can have a PoC assigned"])

    data = request.get_json() or {}
    poc_person_id = data.get("poc_person_id")
    if poc_person_id is not None:
        poc_person = Person.query.get(poc_person_id)
        if not poc_person:
            return _validation_error(["poc_person_id not found"])
        poc_user = User.query.filter_by(id=poc_person.user_id, role="team_lead").first() if poc_person.user_id else None
        if not poc_user:
            return _validation_error(["poc_person_id must reference a person whose linked user has the team_lead role"])

    before = employment.poc_person_id
    employment.poc_person_id = poc_person_id
    db.session.commit()

    log_action(
        action="internship.poc_assigned" if poc_person_id else "internship.poc_unassigned",
        actor=request.current_user,
        target_type="person",
        target_id=person.id,
        target_label=person.full_name,
        details={"from_poc_person_id": before, "to_poc_person_id": poc_person_id},
    )
    return jsonify({"message": "PoC assignment updated", "employment": employment.to_dict()})
