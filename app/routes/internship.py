import secrets
from datetime import date, datetime

from flask import Blueprint, current_app, jsonify, request
from sqlalchemy import or_

from app.extensions import db
from app.models import (
    INTERNSHIP_COHORT_MEMBER_ROLES,
    INTERNSHIP_COHORT_STATUSES,
    INTERNSHIP_PROGRAM_STATUSES,
    InternshipCertificate,
    InternshipCohort,
    InternshipCohortMember,
    InternshipCompletionChecklist,
    InternshipProgram,
    OnboardingTemplateItem,
    Person,
    PersonOnboardingItem,
)
from app.utils.audit import log_action
from app.utils.people_rbac import can_manage_person, is_hr_admin
from app.utils.rbac import require_role


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
        track=track,
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
    allowed_fields = {"name", "track", "status", "start_date", "end_date"}
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

    for field in ("name", "track", "status"):
        if field in data:
            value = data[field]
            if field in {"name", "track"} and isinstance(value, str):
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
    allowed_fields = {"title", "description", "is_active"}
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

    templates = OnboardingTemplateItem.query.filter_by(is_active=True).order_by(OnboardingTemplateItem.created_at.asc()).all()
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
            "template_item_id": template.id,
            "title": template.title,
            "description": template.description,
            "checked": checked,
            "checked_at": check.checked_at.isoformat() if (check and check.checked_at) else None,
            "updated_at": check.updated_at.isoformat() if check else None,
            "updated_by_id": check.updated_by_id if check else None,
        })

    total = len(items)
    progress_percent = round((done / total) * 100) if total else 0
    return jsonify({
        "person": person.to_dict(),
        "items": items,
        "done": done,
        "total": total,
        "progress_percent": progress_percent,
    })


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
