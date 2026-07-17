import pytest
from datetime import date
from app.models import Person, Employment, EmployeeReview, User, Notification


@pytest.fixture
def notif_setup(app, create_user):
    from app.extensions import db
    with app.app_context():
        admin = create_user("admin@test.com", role="admin")
        manager = create_user("mgr@test.com", role="people_manager")
        intern_user = create_user("intern@test.com", role="user")

        mgr_p = Person(first_name="Mgr", last_name="User", email="mgr@test.com", user_id=manager.id, created_by_id=admin.id)
        db.session.add(mgr_p)
        db.session.flush()

        p = Person(first_name="Jane", last_name="Smith", email="jane@test.com", user_id=intern_user.id, created_by_id=admin.id)
        db.session.add(p)
        db.session.flush()

        emp = Employment(
            person_id=p.id, employment_type="intern", intern_track="software",
            status="active", start_date=date(2026, 7, 1), manager_person_id=mgr_p.id,
            created_by_id=admin.id,
        )
        db.session.add(emp)
        db.session.commit()

        return {"admin_id": admin.id, "manager_id": manager.id, "intern_user_id": intern_user.id, "person_id": p.id}


def test_notify_helper_respects_active_and_preference(app, notif_setup):
    from app.utils.notify import notify_user
    from app.extensions import db
    ids = notif_setup
    with app.app_context():
        n = notify_user(ids["manager_id"], "test_event", "Hello", body="World")
        assert n is not None
        assert Notification.query.filter_by(user_id=ids["manager_id"]).count() == 1

        # Disable preference -> suppressed
        mgr = User.query.get(ids["manager_id"])
        mgr.notifications_enabled = False
        db.session.commit()
        n2 = notify_user(ids["manager_id"], "test_event", "Should be suppressed")
        assert n2 is None
        assert Notification.query.filter_by(user_id=ids["manager_id"]).count() == 1

        # Inactive user -> suppressed
        mgr.notifications_enabled = True
        mgr.is_active = False
        db.session.commit()
        n3 = notify_user(ids["manager_id"], "test_event", "Should also be suppressed")
        assert n3 is None


def test_biweekly_workflow_creates_notifications(client, notif_setup, auth_header, app):
    ids = notif_setup
    with app.app_context():
        mgr_h = auth_header(User.query.get(ids["manager_id"]))
        intern_h = auth_header(User.query.get(ids["intern_user_id"]))

    res = client.post("/admin/internship/reviews/biweekly", json={
        "person_id": ids["person_id"], "period_start": "2026-07-01", "period_end": "2026-07-15"
    }, headers=mgr_h)
    review_id = res.json["review"]["id"]

    res = client.post(f"/admin/internship/reviews/biweekly/{review_id}/intern-submit",
                      json={"responses": {"a": "b"}}, headers=intern_h)
    assert res.status_code == 200

    # No PoC assigned -> manager gets notified directly
    res = client.get("/admin/notifications/inbox", headers=mgr_h)
    assert res.status_code == 200
    assert res.json["unread_count"] >= 1
    assert any(n["type"] == "biweekly_ready_for_review" for n in res.json["items"])

    res = client.post(f"/admin/internship/reviews/biweekly/{review_id}/manager-submit",
                      json={"score_progress": 4}, headers=mgr_h)
    assert res.status_code == 200

    # Intern gets notified their review completed
    res = client.get("/admin/notifications/inbox", headers=intern_h)
    assert res.status_code == 200
    assert any(n["type"] == "biweekly_completed" for n in res.json["items"])


def test_inbox_scoped_to_own_notifications_and_actions(client, notif_setup, auth_header, app, create_user):
    ids = notif_setup
    from app.extensions import db
    with app.app_context():
        mgr_h = auth_header(User.query.get(ids["manager_id"]))
        other = create_user("other@test.com", role="people_manager")

        n1 = Notification(user_id=ids["manager_id"], type="x", title="For manager")
        n2 = Notification(user_id=other.id, type="x", title="For other")
        db.session.add_all([n1, n2])
        db.session.commit()
        n1_id, n2_id = n1.id, n2.id

    res = client.get("/admin/notifications/inbox", headers=mgr_h)
    ids_seen = [n["id"] for n in res.json["items"]]
    assert n1_id in ids_seen
    assert n2_id not in ids_seen

    # Cannot mark or delete another user's notification
    res = client.post(f"/admin/notifications/inbox/{n2_id}/read", headers=mgr_h)
    assert res.status_code == 404
    res = client.delete(f"/admin/notifications/inbox/{n2_id}", headers=mgr_h)
    assert res.status_code == 404

    # Can mark and delete own
    res = client.post(f"/admin/notifications/inbox/{n1_id}/read", headers=mgr_h)
    assert res.status_code == 200
    assert res.json["notification"]["is_read"] is True

    res = client.delete(f"/admin/notifications/inbox/{n1_id}", headers=mgr_h)
    assert res.status_code == 200
    with app.app_context():
        assert Notification.query.get(n1_id) is None


def test_mark_all_read(client, notif_setup, auth_header, app):
    ids = notif_setup
    from app.extensions import db
    with app.app_context():
        mgr_h = auth_header(User.query.get(ids["manager_id"]))
        for i in range(3):
            db.session.add(Notification(user_id=ids["manager_id"], type="x", title=f"N{i}"))
        db.session.commit()

    res = client.get("/admin/notifications/inbox", headers=mgr_h)
    assert res.json["unread_count"] == 3

    res = client.post("/admin/notifications/inbox/read-all", headers=mgr_h)
    assert res.status_code == 200

    res = client.get("/admin/notifications/inbox", headers=mgr_h)
    assert res.json["unread_count"] == 0


def test_preference_toggle_via_me_endpoint(client, notif_setup, auth_header, app):
    ids = notif_setup
    with app.app_context():
        mgr_h = auth_header(User.query.get(ids["manager_id"]))

    res = client.get("/auth/me", headers=mgr_h)
    assert res.json["notifications_enabled"] is True

    res = client.patch("/auth/me", json={"notifications_enabled": False}, headers=mgr_h)
    assert res.status_code == 200
    assert res.json["notifications_enabled"] is False

    res = client.patch("/auth/me", json={"role": "admin"}, headers=mgr_h)
    assert res.status_code == 400

    res = client.patch("/auth/me", json={"notifications_enabled": "yes"}, headers=mgr_h)
    assert res.status_code == 400


def test_approval_flow_notifies_approver_and_requester(client, notif_setup, auth_header, app):
    from app.models import Policy
    from app.extensions import db
    ids = notif_setup
    with app.app_context():
        admin = User.query.get(ids["admin_id"])
        admin_h = auth_header(admin)
        mgr_h = auth_header(User.query.get(ids["manager_id"]))

        policy = Policy(
            name="Employee Termination Approval",
            action="people.finalize_employee_review",
            requires_approval=True, approvals_required=1, approver_role="admin",
            is_active=True, created_by=admin.id,
        )
        db.session.add(policy)

        # A distinct employee managed by the manager (a manager cannot review
        # their own performance record, correctly, so use a real report).
        mgr_person = Person.query.filter_by(email="mgr@test.com").first()
        emp_user = User(email="report@test.com", role="user", is_active=True)
        emp_user.set_password("Pass1234!")
        db.session.add(emp_user)
        db.session.flush()
        report_person = Person(first_name="Rex", last_name="Report", email="report@test.com",
                               user_id=emp_user.id, created_by_id=ids["admin_id"])
        db.session.add(report_person)
        db.session.flush()
        emp = Employment(person_id=report_person.id, employment_type="full_time", status="active",
                         start_date=date(2024, 1, 1), manager_person_id=mgr_person.id,
                         created_by_id=ids["admin_id"])
        db.session.add(emp)
        db.session.commit()
        report_h = auth_header(emp_user)
        report_person_id = report_person.id

    client.post("/admin/performance/reviews/ensure", headers=admin_h)
    with app.app_context():
        review = EmployeeReview.query.filter_by(person_id=report_person_id).first()
        review_id = review.id

    client.post(f"/admin/performance/reviews/{review_id}/self-submit",
                json={"responses": {"summary": "ok"}}, headers=report_h)

    res = client.post(f"/admin/performance/reviews/{review_id}/manager-submit", json={
        "score": 1, "decision": "terminate"
    }, headers=mgr_h)
    assert res.status_code == 202

    # Admin (the approver) got notified of the pending approval
    res = client.get("/admin/notifications/inbox", headers=admin_h)
    assert any(n["type"] == "approval_requested" for n in res.json["items"])

    approval_id = res.json["items"][0]["target_id"] if res.json["items"][0]["type"] == "approval_requested" else None
    approvals = client.get("/admin/approvals", headers=admin_h).json
    pending = [a for a in approvals.get("items", []) if a["status"] == "pending"]
    assert len(pending) >= 1
    approval_id = pending[0]["id"]

    res = client.post(f"/admin/approvals/{approval_id}/approve", headers=admin_h)
    assert res.status_code == 200

    # The requester (manager) got notified their request was approved
    res = client.get("/admin/notifications/inbox", headers=mgr_h)
    assert any(n["type"] == "approval_decided" for n in res.json["items"])
