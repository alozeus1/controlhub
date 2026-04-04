from app.extensions import db
from app.models import (
    Person,
    Employment,
    PerformanceCheckin,
    Policy,
)
from app.routes.people import _apply_people_filters, _base_people_query
from sqlalchemy.dialects import postgresql


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


def test_people_manager_can_only_update_direct_reports(client, create_user, auth_header):
    manager_user = create_user("mgr@acme.test", role="people_manager")
    admin_user = create_user("admin@acme.test", role="admin")

    manager_person = _make_person(manager_user.id, "Mina", "Manager", "mina.manager@acme.test", user_id=manager_user.id)
    direct = _make_person(admin_user.id, "Dee", "Report", "dee.report@acme.test", team="Platform")
    other = _make_person(admin_user.id, "Ola", "Other", "ola.other@acme.test", team="Security")
    _make_employment(admin_user.id, direct.id, manager_person_id=manager_person.id)
    _make_employment(admin_user.id, other.id, manager_person_id=None)
    db.session.commit()

    ok = client.patch(f"/admin/people/{direct.id}", json={"team": "Core Platform"}, headers=auth_header(manager_user))
    assert ok.status_code == 200
    assert ok.get_json()["person"]["team"] == "Core Platform"

    forbidden = client.patch(f"/admin/people/{other.id}", json={"team": "Operations"}, headers=auth_header(manager_user))
    assert forbidden.status_code == 403
    assert forbidden.get_json()["code"] == "INSUFFICIENT_PERMISSIONS"


def test_mentor_checkin_permissions(client, create_user, auth_header):
    mentor_user = create_user("mentor@acme.test", role="mentor")
    admin_user = create_user("admin2@acme.test", role="admin")
    manager_user = create_user("mgr2@acme.test", role="people_manager")

    mentor_person = _make_person(mentor_user.id, "Mona", "Mentor", "mona.mentor@acme.test", user_id=mentor_user.id)
    manager_person = _make_person(manager_user.id, "Mark", "Manager", "mark.manager@acme.test", user_id=manager_user.id)
    intern = _make_person(admin_user.id, "Ian", "Intern", "ian.intern@acme.test")
    full_time = _make_person(admin_user.id, "Fiona", "Fte", "fiona.fte@acme.test")

    _make_employment(admin_user.id, intern.id, employment_type="intern", intern_track="software", mentor_person_id=mentor_person.id, manager_person_id=manager_person.id)
    _make_employment(admin_user.id, full_time.id, employment_type="full_time", mentor_person_id=mentor_person.id, manager_person_id=manager_person.id)
    db.session.commit()

    checkin_ok = client.post(
        f"/admin/people/{intern.id}/checkins",
        json={"summary": "Week 2 review", "notes": "Good progress"},
        headers=auth_header(mentor_user),
    )
    assert checkin_ok.status_code == 201
    assert PerformanceCheckin.query.filter_by(person_id=intern.id).count() == 1

    checkin_blocked = client.post(
        f"/admin/people/{full_time.id}/checkins",
        json={"summary": "Invalid checkin"},
        headers=auth_header(mentor_user),
    )
    assert checkin_blocked.status_code == 403
    assert checkin_blocked.get_json()["code"] == "INSUFFICIENT_PERMISSIONS"


def test_people_sensitive_actions_with_approval_flow(client, create_user, auth_header):
    hr_admin = create_user("hr@acme.test", role="hr_admin")
    approver = create_user("approver@acme.test", role="admin")

    person = _make_person(hr_admin.id, "Ina", "Intern", "ina.intern@acme.test", team="Platform")
    employment = _make_employment(hr_admin.id, person.id, employment_type="intern", intern_track="ai_ml", status="active")
    db.session.commit()

    terminate_policy = Policy(
        name="Termination Approval",
        action="people.terminate",
        requires_approval=True,
        approvals_required=1,
        approver_role="admin",
        is_active=True,
        created_by=approver.id,
    )
    export_policy = Policy(
        name="Directory Export Approval",
        action="people.export_bulk",
        requires_approval=True,
        approvals_required=1,
        approver_role="admin",
        is_active=True,
        created_by=approver.id,
    )
    db.session.add_all([terminate_policy, export_policy])
    db.session.commit()

    terminate_req = client.post(f"/admin/people/{person.id}/terminate", json={}, headers=auth_header(hr_admin))
    assert terminate_req.status_code == 202
    terminate_approval_id = terminate_req.get_json()["approval_request"]["id"]

    approve_terminate = client.post(f"/admin/approvals/{terminate_approval_id}/approve", headers=auth_header(approver))
    assert approve_terminate.status_code == 200
    db.session.refresh(person)
    db.session.refresh(employment)
    assert person.is_active is False
    assert employment.status == "terminated"

    export_req = client.get("/admin/people/export/csv", headers=auth_header(hr_admin))
    assert export_req.status_code == 202
    export_approval_id = export_req.get_json()["approval_request"]["id"]

    approve_export = client.post(f"/admin/approvals/{export_approval_id}/approve", headers=auth_header(approver))
    assert approve_export.status_code == 200

    export_download = client.get(
        f"/admin/people/export/csv?approval_request_id={export_approval_id}",
        headers=auth_header(hr_admin),
    )
    assert export_download.status_code == 200
    assert "text/csv" in export_download.headers["Content-Type"]
    assert "Ina Intern" in export_download.get_data(as_text=True)


def test_convert_intern_to_full_time_with_approval(client, create_user, auth_header):
    hr_admin = create_user("hr2@acme.test", role="hr_admin")
    approver = create_user("approver2@acme.test", role="admin")

    person = _make_person(hr_admin.id, "Cora", "Candidate", "cora.candidate@acme.test")
    intern_employment = _make_employment(
        hr_admin.id,
        person.id,
        employment_type="intern",
        intern_track="devops",
        status="active",
        title="Platform Intern",
    )
    db.session.commit()

    policy = Policy(
        name="Intern Conversion Approval",
        action="people.convert_intern",
        requires_approval=True,
        approvals_required=1,
        approver_role="admin",
        is_active=True,
        created_by=approver.id,
    )
    db.session.add(policy)
    db.session.commit()

    convert_req = client.post(
        f"/admin/people/{person.id}/convert-to-full-time",
        json={"title": "Platform Engineer I"},
        headers=auth_header(hr_admin),
    )
    assert convert_req.status_code == 202
    approval_id = convert_req.get_json()["approval_request"]["id"]

    approve = client.post(f"/admin/approvals/{approval_id}/approve", headers=auth_header(approver))
    assert approve.status_code == 200

    db.session.refresh(intern_employment)
    assert intern_employment.status == "completed"
    full_time = (
        Employment.query
        .filter_by(person_id=person.id, employment_type="full_time", status="active")
        .order_by(Employment.created_at.desc())
        .first()
    )
    assert full_time is not None
    assert full_time.title == "Platform Engineer I"


def test_people_list_filters_by_employment_type(client, create_user, auth_header):
    people_manager = create_user("pm@acme.test", role="people_manager")
    creator = create_user("creator@acme.test", role="admin")

    intern = _make_person(creator.id, "Ivy", "Intern", "ivy.intern@acme.test")
    fte = _make_person(creator.id, "Fred", "Fte", "fred.fte@acme.test")
    _make_employment(creator.id, intern.id, employment_type="intern", intern_track="software", status="active")
    _make_employment(creator.id, fte.id, employment_type="full_time", status="active")
    db.session.commit()

    res = client.get("/admin/people?employment_type=intern", headers=auth_header(people_manager))
    assert res.status_code == 200
    payload = res.get_json()
    assert payload["total"] == 1
    assert payload["items"][0]["id"] == intern.id


def test_people_export_csv_filters_by_employment_type(client, create_user, auth_header):
    people_manager = create_user("pm2@acme.test", role="people_manager")
    creator = create_user("creator2@acme.test", role="admin")

    intern = _make_person(creator.id, "Nia", "Intern", "nia.intern@acme.test")
    fte = _make_person(creator.id, "Noel", "Fte", "noel.fte@acme.test")
    _make_employment(creator.id, intern.id, employment_type="intern", intern_track="devops", status="active")
    _make_employment(creator.id, fte.id, employment_type="full_time", status="active")
    db.session.commit()

    res = client.get("/admin/people/export/csv?employment_type=intern", headers=auth_header(people_manager))
    assert res.status_code == 200
    csv_text = res.get_data(as_text=True)
    assert "Nia Intern" in csv_text
    assert "Noel Fte" not in csv_text


def test_people_filtered_query_does_not_emit_postgres_distinct_on(app):
    with app.test_request_context("/admin/people?employment_type=intern"):
        query = _apply_people_filters(_base_people_query()).order_by(Person.created_at.desc())
        sql = str(
            query.statement.compile(
                dialect=postgresql.dialect(),
                compile_kwargs={"literal_binds": True},
            )
        )

    assert "DISTINCT ON" not in sql.upper()
