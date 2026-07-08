import pytest
from datetime import date, timedelta
from app.models import Person, Employment, EmployeeReview, User, Policy


@pytest.fixture
def employee_setup(app, create_user):
    from app.extensions import db
    with app.app_context():
        admin = create_user("admin@test.com", role="admin")
        manager = create_user("mgr@test.com", role="people_manager")
        employee_user = create_user("emp@test.com", role="user")
        other_mgr = create_user("othermgr@test.com", role="people_manager")

        mgr_p = Person(first_name="Mgr", last_name="User", email="mgr@test.com", user_id=manager.id, created_by_id=admin.id)
        other_mgr_p = Person(first_name="Other", last_name="Mgr", email="othermgr-p@test.com", user_id=other_mgr.id, created_by_id=admin.id)
        db.session.add_all([mgr_p, other_mgr_p])
        db.session.flush()

        emp_person = Person(first_name="Erin", last_name="Employee", email="erin@test.com", user_id=employee_user.id, created_by_id=admin.id)
        db.session.add(emp_person)
        db.session.flush()

        employment = Employment(
            person_id=emp_person.id, employment_type="full_time", status="active",
            title="Software Engineer", start_date=date(2024, 1, 1),
            manager_person_id=mgr_p.id, created_by_id=admin.id,
        )
        db.session.add(employment)
        db.session.commit()

        return {
            "admin_id": admin.id, "manager_id": manager.id, "other_mgr_id": other_mgr.id,
            "employee_user_id": employee_user.id, "person_id": emp_person.id,
        }


def test_ensure_quarterly_reviews_is_idempotent_and_skips_interns(client, employee_setup, auth_header, app):
    ids = employee_setup
    from app.extensions import db

    with app.app_context():
        admin = User.query.get(ids["admin_id"])
        admin_h = auth_header(admin)
        # Add an intern too — must NOT get an employee review
        intern_user = User(email="intern-x@test.com", role="user", is_active=True)
        intern_user.set_password("Pass1234!")
        db.session.add(intern_user)
        db.session.flush()
        intern_p = Person(first_name="Ian", last_name="Intern", email="ian@test.com", user_id=intern_user.id, created_by_id=ids["admin_id"])
        db.session.add(intern_p)
        db.session.flush()
        db.session.add(Employment(person_id=intern_p.id, employment_type="intern", status="active",
                                  start_date=date.today(), created_by_id=ids["admin_id"]))
        db.session.commit()
        intern_person_id = intern_p.id

    res = client.post("/admin/performance/reviews/ensure", headers=admin_h)
    assert res.status_code == 200
    assert res.json["created"] >= 1

    with app.app_context():
        reviews = EmployeeReview.query.filter_by(person_id=ids["person_id"]).all()
        assert len(reviews) == 1
        assert reviews[0].status == "pending_self"
        # Interns never get an EmployeeReview
        assert EmployeeReview.query.filter_by(person_id=intern_person_id).count() == 0

    # Calling again does not create a duplicate for the same quarter
    res2 = client.post("/admin/performance/reviews/ensure", headers=admin_h)
    assert res2.status_code == 200
    assert res2.json["created"] == 0
    with app.app_context():
        assert EmployeeReview.query.filter_by(person_id=ids["person_id"]).count() == 1


def test_ensure_applies_regardless_of_start_date(client, employee_setup, auth_header, app):
    """A long-tenured employee (started years ago) still gets the CURRENT
    quarter's review, not one keyed to their hire anniversary."""
    ids = employee_setup
    with app.app_context():
        admin_h = auth_header(User.query.get(ids["admin_id"]))

    res = client.post("/admin/performance/reviews/ensure", headers=admin_h)
    assert res.status_code == 200

    with app.app_context():
        from app.routes.performance import current_quarter
        expected_quarter, _, _ = current_quarter()
        review = EmployeeReview.query.filter_by(person_id=ids["person_id"]).first()
        assert review.quarter == expected_quarter


def test_full_employee_review_cycle_retain(client, employee_setup, auth_header, app):
    ids = employee_setup
    with app.app_context():
        admin_h = auth_header(User.query.get(ids["admin_id"]))
        mgr_h = auth_header(User.query.get(ids["manager_id"]))
        emp_h = auth_header(User.query.get(ids["employee_user_id"]))

    client.post("/admin/performance/reviews/ensure", headers=admin_h)

    # Employees see their own reviews through the self-service endpoint
    # (the generic listing endpoint is mentor+, mirroring the intern pattern).
    res = client.get("/admin/performance/my-reviews", headers=emp_h)
    assert res.status_code == 200
    review_id = res.json["items"][0]["id"]

    # Employee submits self-report
    res = client.post(f"/admin/performance/reviews/{review_id}/self-submit",
                      json={"responses": {"summary": "Shipped the new billing module."}}, headers=emp_h)
    assert res.status_code == 200
    assert res.json["review"]["status"] == "pending_manager"

    # Employee cannot re-submit once passed to manager
    res = client.post(f"/admin/performance/reviews/{review_id}/self-submit",
                      json={"responses": {"summary": "edit"}}, headers=emp_h)
    assert res.status_code == 400

    # Manager scores and retains
    res = client.post(f"/admin/performance/reviews/{review_id}/manager-submit", json={
        "score": 4, "strengths": "Reliable delivery", "concerns": "None",
        "action_items": [{"task": "Mentor a junior dev"}], "decision": "retain",
    }, headers=mgr_h)
    assert res.status_code == 200
    body = res.json["review"]
    assert body["status"] == "completed"
    assert body["decision"] == "retain"
    assert "DRAFT AI Summary" in body["ai_summary"]

    with app.app_context():
        emp = Person.query.get(ids["person_id"]).active_employment
        assert emp.status == "active"
        assert emp.title == "Software Engineer"  # unchanged on retain


def test_decision_side_effects(client, employee_setup, auth_header, app):
    ids = employee_setup
    with app.app_context():
        from app.extensions import db
        admin_h = auth_header(User.query.get(ids["admin_id"]))
        mgr_h = auth_header(User.query.get(ids["manager_id"]))
        emp_h = auth_header(User.query.get(ids["employee_user_id"]))
        # give the employment an end_date so 'extend' has something to push
        emp = Person.query.get(ids["person_id"]).active_employment
        emp.end_date = date(2026, 12, 31)
        db.session.commit()

    client.post("/admin/performance/reviews/ensure", headers=admin_h)
    with app.app_context():
        review_id = EmployeeReview.query.filter_by(person_id=ids["person_id"]).first().id
    client.post(f"/admin/performance/reviews/{review_id}/self-submit",
                json={"responses": {"summary": "Solid quarter."}}, headers=emp_h)

    # Promote requires new_title
    res = client.post(f"/admin/performance/reviews/{review_id}/manager-submit", json={
        "score": 5, "decision": "promote"
    }, headers=mgr_h)
    assert res.status_code == 400

    res = client.post(f"/admin/performance/reviews/{review_id}/manager-submit", json={
        "score": 5, "decision": "promote", "new_title": "Senior Software Engineer"
    }, headers=mgr_h)
    assert res.status_code == 200
    with app.app_context():
        emp = Person.query.get(ids["person_id"]).active_employment
        assert emp.title == "Senior Software Engineer"


def test_extend_pushes_end_date(client, employee_setup, auth_header, app):
    ids = employee_setup
    from app.extensions import db
    with app.app_context():
        admin_h = auth_header(User.query.get(ids["admin_id"]))
        mgr_h = auth_header(User.query.get(ids["manager_id"]))
        emp_h = auth_header(User.query.get(ids["employee_user_id"]))
        emp = Person.query.get(ids["person_id"]).active_employment
        emp.end_date = date(2026, 12, 31)
        db.session.commit()

    client.post("/admin/performance/reviews/ensure", headers=admin_h)
    with app.app_context():
        review_id = EmployeeReview.query.filter_by(person_id=ids["person_id"]).first().id
    client.post(f"/admin/performance/reviews/{review_id}/self-submit",
                json={"responses": {"summary": "Solid quarter."}}, headers=emp_h)

    res = client.post(f"/admin/performance/reviews/{review_id}/manager-submit", json={
        "score": 3, "decision": "extend"
    }, headers=mgr_h)
    assert res.status_code == 200
    with app.app_context():
        emp = Person.query.get(ids["person_id"]).active_employment
        assert emp.end_date == date(2027, 3, 31)  # +90 days


def test_terminate_gated_by_governance_policy(client, employee_setup, auth_header, app):
    ids = employee_setup
    from app.extensions import db
    with app.app_context():
        admin = User.query.get(ids["admin_id"])
        admin_h = auth_header(admin)
        mgr_h = auth_header(User.query.get(ids["manager_id"]))
        emp_h = auth_header(User.query.get(ids["employee_user_id"]))

        policy = Policy(
            name="Employee Termination Approval",
            action="people.finalize_employee_review",
            requires_approval=True, approvals_required=1, approver_role="admin",
            is_active=True, created_by=admin.id,
        )
        db.session.add(policy)
        db.session.commit()

    client.post("/admin/performance/reviews/ensure", headers=admin_h)
    with app.app_context():
        review_id = EmployeeReview.query.filter_by(person_id=ids["person_id"]).first().id

    client.post(f"/admin/performance/reviews/{review_id}/self-submit",
                json={"responses": {"summary": "Struggled with deadlines this quarter."}}, headers=emp_h)

    res = client.post(f"/admin/performance/reviews/{review_id}/manager-submit", json={
        "score": 1, "decision": "terminate"
    }, headers=mgr_h)
    assert res.status_code == 202
    approval_id = res.json["approval_request"]["id"]

    with app.app_context():
        review = EmployeeReview.query.get(review_id)
        assert review.status == "pending_manager"  # not yet finalized

    res = client.post(f"/admin/approvals/{approval_id}/approve", headers=admin_h)
    assert res.status_code == 200

    with app.app_context():
        review = EmployeeReview.query.get(review_id)
        assert review.status == "completed"
        assert review.decision == "terminate"
        # active_employment excludes 'completed' rows by definition, so query
        # the (now terminated) employment directly rather than via that property.
        emp = Employment.query.filter_by(person_id=ids["person_id"]).order_by(Employment.id.desc()).first()
        assert emp.status == "completed"


def test_rbac_manager_scoping_and_unrelated_manager_blocked(client, employee_setup, auth_header, app):
    ids = employee_setup
    with app.app_context():
        admin_h = auth_header(User.query.get(ids["admin_id"]))
        other_h = auth_header(User.query.get(ids["other_mgr_id"]))

    client.post("/admin/performance/reviews/ensure", headers=admin_h)
    with app.app_context():
        review_id = EmployeeReview.query.filter_by(person_id=ids["person_id"]).first().id

    # A manager who doesn't manage this employee cannot read or grade
    res = client.get(f"/admin/performance/reviews?person_id={ids['person_id']}", headers=other_h)
    assert res.status_code == 403

    res = client.post(f"/admin/performance/reviews/{review_id}/manager-submit", json={
        "score": 5, "decision": "retain"
    }, headers=other_h)
    assert res.status_code == 403


def test_team_lead_cannot_access_employee_reviews(client, employee_setup, auth_header, app, create_user):
    ids = employee_setup
    with app.app_context():
        admin_h = auth_header(User.query.get(ids["admin_id"]))
        team_lead = create_user("lead@test.com", role="team_lead")
        lead_h = auth_header(team_lead)

    client.post("/admin/performance/reviews/ensure", headers=admin_h)
    with app.app_context():
        review_id = EmployeeReview.query.filter_by(person_id=ids["person_id"]).first().id

    res = client.get(f"/admin/performance/reviews?person_id={ids['person_id']}", headers=lead_h)
    assert res.status_code == 403

    res = client.post(f"/admin/performance/reviews/{review_id}/manager-submit", json={
        "score": 5, "decision": "retain"
    }, headers=lead_h)
    assert res.status_code == 403


def test_my_reviews_endpoint_creates_and_scopes_to_self(client, employee_setup, auth_header, app):
    ids = employee_setup
    with app.app_context():
        emp_h = auth_header(User.query.get(ids["employee_user_id"]))

    # No explicit ensure call — my-reviews triggers it lazily
    res = client.get("/admin/performance/my-reviews", headers=emp_h)
    assert res.status_code == 200
    assert res.json["linked"] is True
    assert res.json["applicable"] is True
    assert len(res.json["items"]) == 1
    assert res.json["items"][0]["status"] == "pending_self"


def test_intern_my_reviews_not_applicable(client, app, create_user, auth_header):
    from app.extensions import db
    with app.app_context():
        admin = create_user("admin2@test.com", role="admin")
        intern_user = create_user("internx2@test.com", role="user")
        p = Person(first_name="Izzy", last_name="Intern", email="izzy@test.com", user_id=intern_user.id, created_by_id=admin.id)
        db.session.add(p)
        db.session.flush()
        db.session.add(Employment(person_id=p.id, employment_type="intern", status="active",
                                  start_date=date.today(), created_by_id=admin.id))
        db.session.commit()
        intern_h = auth_header(intern_user)

    res = client.get("/admin/performance/my-reviews", headers=intern_h)
    assert res.status_code == 200
    assert res.json["linked"] is True
    assert res.json["applicable"] is False
    assert res.json["items"] == []


def test_team_lead_assignment_roster_and_update(client, employee_setup, auth_header, app, create_user):
    ids = employee_setup
    from app.extensions import db
    with app.app_context():
        admin_h = auth_header(User.query.get(ids["admin_id"]))
        mgr_h = auth_header(User.query.get(ids["manager_id"]))
        team_lead_user = create_user("lead2@test.com", role="team_lead")
        lead_person = Person(first_name="Lea", last_name="Lead", email="lea@test.com", user_id=team_lead_user.id, created_by_id=ids["admin_id"])
        db.session.add(lead_person)
        db.session.flush()

        intern_user = create_user("internz@test.com", role="user")
        intern_person = Person(first_name="Izzy", last_name="Zed", email="izzy2@test.com", user_id=intern_user.id, created_by_id=ids["admin_id"])
        db.session.add(intern_person)
        db.session.flush()
        db.session.add(Employment(person_id=intern_person.id, employment_type="intern", status="active",
                                  start_date=date.today(), created_by_id=ids["admin_id"]))
        db.session.commit()
        lead_person_id = lead_person.id
        intern_person_id = intern_person.id

    # Roster shows the team lead with no assigned interns yet, and the intern unassigned
    res = client.get("/admin/internship/team-lead-assignments", headers=admin_h)
    assert res.status_code == 200
    lead_row = next(r for r in res.json["team_leads"] if r["person_id"] == lead_person_id)
    assert lead_row["assigned_interns"] == []
    assert any(i["person_id"] == intern_person_id for i in res.json["unassigned_interns"])

    # Assign the intern to the team lead
    res = client.put(f"/admin/internship/people/{intern_person_id}/poc",
                     json={"poc_person_id": lead_person_id}, headers=mgr_h)
    assert res.status_code == 200
    assert res.json["employment"]["poc_person_id"] == lead_person_id

    res = client.get("/admin/internship/team-lead-assignments", headers=admin_h)
    lead_row = next(r for r in res.json["team_leads"] if r["person_id"] == lead_person_id)
    assert len(lead_row["assigned_interns"]) == 1
    assert lead_row["assigned_interns"][0]["person_id"] == intern_person_id
    assert not any(i["person_id"] == intern_person_id for i in res.json["unassigned_interns"])

    # Cannot assign a PoC to a non-intern employee
    res = client.put(f"/admin/internship/people/{ids['person_id']}/poc",
                     json={"poc_person_id": lead_person_id}, headers=mgr_h)
    assert res.status_code == 400

    # Unassign
    res = client.put(f"/admin/internship/people/{intern_person_id}/poc",
                     json={"poc_person_id": None}, headers=mgr_h)
    assert res.status_code == 200
    assert res.json["employment"]["poc_person_id"] is None
