from app.extensions import db
from app.models import (
    AuditLog,
    Employment,
    InternshipCertificate,
    Person,
    Policy,
)


def _make_person(created_by_id, first_name, last_name, email, user_id=None, **kwargs):
    person = Person(
        user_id=user_id,
        first_name=first_name,
        last_name=last_name,
        email=email,
        created_by_id=created_by_id,
        is_active=True,
        **kwargs,
    )
    db.session.add(person)
    db.session.flush()
    return person


def _make_employment(created_by_id, person_id, **kwargs):
    employment = Employment(
        person_id=person_id,
        created_by_id=created_by_id,
        employment_type=kwargs.pop("employment_type", "full_time"),
        status=kwargs.pop("status", "active"),
        **kwargs,
    )
    db.session.add(employment)
    db.session.flush()
    return employment


def test_program_cohort_membership_flow(client, create_user, auth_header):
    manager = create_user("program-mgr@acme.test", role="people_manager")
    admin = create_user("program-admin@acme.test", role="admin")

    manager_person = _make_person(manager.id, "Mia", "Manager", "mia.manager@acme.test", user_id=manager.id)
    intern = _make_person(admin.id, "Ian", "Intern", "ian.intern@acme.test", cohort="Spring-26")
    _make_employment(admin.id, intern.id, employment_type="intern", manager_person_id=manager_person.id, intern_track="software")
    db.session.commit()

    program_resp = client.post(
        "/admin/internship/programs",
        json={"name": "Talent Program 2026", "status": "planned"},
        headers=auth_header(manager),
    )
    assert program_resp.status_code == 201
    program_id = program_resp.get_json()["program"]["id"]

    cohort_resp = client.post(
        "/admin/internship/cohorts",
        json={
            "program_id": program_id,
            "name": "Cohort A",
            "track": "software",
            "status": "active",
        },
        headers=auth_header(manager),
    )
    assert cohort_resp.status_code == 201
    cohort_id = cohort_resp.get_json()["cohort"]["id"]

    add_member_resp = client.post(
        f"/admin/internship/cohorts/{cohort_id}/members",
        json={"person_id": intern.id, "role": "intern"},
        headers=auth_header(manager),
    )
    assert add_member_resp.status_code == 201

    list_members = client.get(f"/admin/internship/cohorts/{cohort_id}/members", headers=auth_header(manager))
    assert list_members.status_code == 200
    payload = list_members.get_json()
    assert payload["total"] == 1
    assert payload["items"][0]["person_id"] == intern.id



def test_onboarding_progress_rbac(client, create_user, auth_header):
    manager = create_user("onboard-mgr@acme.test", role="people_manager")
    other_manager = create_user("onboard-other@acme.test", role="people_manager")
    admin = create_user("onboard-admin@acme.test", role="admin")

    manager_person = _make_person(manager.id, "Mark", "Manager", "mark.manager@acme.test", user_id=manager.id)
    _make_person(other_manager.id, "Olly", "Manager", "olly.manager@acme.test", user_id=other_manager.id)
    intern = _make_person(admin.id, "Nina", "Intern", "nina.intern@acme.test")
    _make_employment(admin.id, intern.id, employment_type="intern", manager_person_id=manager_person.id, intern_track="devops")
    db.session.commit()

    template_resp = client.post(
        "/admin/internship/onboarding/templates",
        json={"title": "Submit signed NDA", "description": "Upload signed document"},
        headers=auth_header(manager),
    )
    assert template_resp.status_code == 201
    template_id = template_resp.get_json()["item"]["id"]

    check_resp = client.put(
        f"/admin/internship/people/{intern.id}/onboarding/{template_id}/check",
        json={"checked": True},
        headers=auth_header(manager),
    )
    assert check_resp.status_code == 200

    forbidden = client.put(
        f"/admin/internship/people/{intern.id}/onboarding/{template_id}/check",
        json={"checked": False},
        headers=auth_header(other_manager),
    )
    assert forbidden.status_code == 403

    progress = client.get(f"/admin/internship/people/{intern.id}/onboarding", headers=auth_header(manager))
    assert progress.status_code == 200
    body = progress.get_json()
    assert body["done"] == 1
    assert body["total"] == 1
    assert body["progress_percent"] == 100



def test_certificate_issuance_with_approval(client, create_user, auth_header):
    hr_admin = create_user("cert-hr@acme.test", role="hr_admin")
    approver = create_user("cert-approver@acme.test", role="admin")

    person = _make_person(hr_admin.id, "Cory", "Candidate", "cory.candidate@acme.test")
    _make_employment(hr_admin.id, person.id, employment_type="intern", intern_track="ai_ml", status="active")
    db.session.commit()

    completion = client.put(
        f"/admin/internship/people/{person.id}/completion",
        json={"project_submitted": True, "evaluation_done": True, "admin_validated": True},
        headers=auth_header(hr_admin),
    )
    assert completion.status_code == 200

    policy = Policy(
        name="Certificate Approval",
        action="people.issue_certificate",
        requires_approval=True,
        approvals_required=1,
        approver_role="admin",
        is_active=True,
        created_by=approver.id,
    )
    db.session.add(policy)
    db.session.commit()

    request_cert = client.post(
        f"/admin/internship/people/{person.id}/certificate",
        json={"pdf_url": "https://example.test/certificate.pdf"},
        headers=auth_header(hr_admin),
    )
    assert request_cert.status_code == 202
    approval_id = request_cert.get_json()["approval_request"]["id"]

    approve = client.post(f"/admin/approvals/{approval_id}/approve", headers=auth_header(approver))
    assert approve.status_code == 200

    certificate = InternshipCertificate.query.filter_by(person_id=person.id).first()
    assert certificate is not None
    assert certificate.certificate_no.startswith("CH-")

    certs_resp = client.get(f"/admin/internship/people/{person.id}/certificates", headers=auth_header(hr_admin))
    assert certs_resp.status_code == 200
    assert certs_resp.get_json()["total"] == 1

    audit = (
        AuditLog.query
        .filter_by(action="internship.certificate_issued", target_id=person.id)
        .order_by(AuditLog.created_at.desc())
        .first()
    )
    assert audit is not None
    assert audit.details["certificate_no"] == certificate.certificate_no
