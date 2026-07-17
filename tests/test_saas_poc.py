import pytest
from datetime import date
from app.models import Person, Employment, User


@pytest.fixture
def poc_setup(app, create_user):
    from app.extensions import db
    with app.app_context():
        admin = create_user("admin@test.com", role="admin")
        manager = create_user("mgr@test.com", role="people_manager")
        poc = create_user("poc@test.com", role="team_lead")
        other_poc = create_user("otherpoc@test.com", role="team_lead")
        intern_user = create_user("intern@test.com", role="user")

        mgr_p = Person(first_name="Mgr", last_name="User", email="mgr@test.com", user_id=manager.id, created_by_id=admin.id)
        poc_p = Person(first_name="Poc", last_name="Lead", email="poc-p@test.com", user_id=poc.id, created_by_id=admin.id)
        other_poc_p = Person(first_name="Other", last_name="Lead", email="otherpoc-p@test.com", user_id=other_poc.id, created_by_id=admin.id)
        db.session.add_all([mgr_p, poc_p, other_poc_p])
        db.session.flush()

        p = Person(first_name="Jane", last_name="Smith", email="jane@test.com", user_id=intern_user.id, created_by_id=admin.id)
        db.session.add(p)
        db.session.flush()

        emp = Employment(
            person_id=p.id, employment_type="intern", intern_track="software",
            status="active", start_date=date(2026, 7, 1),
            manager_person_id=mgr_p.id, poc_person_id=poc_p.id,
            created_by_id=admin.id,
        )
        db.session.add(emp)
        db.session.commit()

        return {
            "admin_id": admin.id, "manager_id": manager.id, "poc_id": poc.id,
            "other_poc_id": other_poc.id, "intern_user_id": intern_user.id, "person_id": p.id,
        }


def test_full_poc_review_workflow(client, poc_setup, auth_header, app):
    ids = poc_setup
    with app.app_context():
        mgr_h = auth_header(User.query.get(ids["manager_id"]))
        poc_h = auth_header(User.query.get(ids["poc_id"]))
        intern_h = auth_header(User.query.get(ids["intern_user_id"]))

    # Manager opens the period
    res = client.post("/admin/internship/reviews/biweekly", json={
        "person_id": ids["person_id"], "period_start": "2026-07-01", "period_end": "2026-07-15"
    }, headers=mgr_h)
    assert res.status_code == 201
    review_id = res.json["review"]["id"]

    # Intern submits -> routed to the PoC because one is assigned
    res = client.post(f"/admin/internship/reviews/biweekly/{review_id}/intern-submit",
                      json={"responses": {"accomplishments": "built things"}}, headers=intern_h)
    assert res.status_code == 200
    assert res.json["review"]["status"] == "pending_poc"

    # Manager cannot be skipped INTO yet; PoC grades and passes the report on
    res = client.post(f"/admin/internship/reviews/biweekly/{review_id}/poc-submit", json={
        "score_progress": 4, "blockers": "None", "strengths": "Ownership",
        "action_items": [{"task": "demo prep", "due": "2026-07-20"}],
        "notes": "Solid sprint; recommend keeping current pace.",
    }, headers=poc_h)
    assert res.status_code == 200
    body = res.json["review"]
    assert body["status"] == "pending_manager"
    assert body["poc_reviewer_id"] == ids["poc_id"]
    assert body["poc_notes"].startswith("Solid sprint")
    assert body["score_progress"] == 4

    # PoC cannot re-submit once passed on
    res = client.post(f"/admin/internship/reviews/biweekly/{review_id}/poc-submit",
                      json={"score_progress": 5}, headers=poc_h)
    assert res.status_code == 400

    # Manager finalizes; the summary credits the PoC assessment
    res = client.post(f"/admin/internship/reviews/biweekly/{review_id}/manager-submit", json={
        "score_progress": 4, "strengths": "Ownership", "blockers": "None"
    }, headers=mgr_h)
    assert res.status_code == 200
    assert res.json["review"]["status"] == "completed"
    assert "PoC assessment by" in res.json["review"]["ai_summary"]


def test_poc_rbac_scoping(client, poc_setup, auth_header, app):
    ids = poc_setup
    with app.app_context():
        mgr_h = auth_header(User.query.get(ids["manager_id"]))
        poc_h = auth_header(User.query.get(ids["poc_id"]))
        other_h = auth_header(User.query.get(ids["other_poc_id"]))
        intern_h = auth_header(User.query.get(ids["intern_user_id"]))

    res = client.post("/admin/internship/reviews/biweekly", json={
        "person_id": ids["person_id"], "period_start": "2026-07-01", "period_end": "2026-07-15"
    }, headers=mgr_h)
    review_id = res.json["review"]["id"]
    client.post(f"/admin/internship/reviews/biweekly/{review_id}/intern-submit",
                json={"responses": {"a": "b"}}, headers=intern_h)

    # A team lead who is NOT this intern's PoC cannot assess
    res = client.post(f"/admin/internship/reviews/biweekly/{review_id}/poc-submit",
                      json={"score_progress": 3}, headers=other_h)
    assert res.status_code == 403

    # ...and cannot read the intern's reviews
    res = client.get(f"/admin/internship/reviews/biweekly?person_id={ids['person_id']}", headers=other_h)
    assert res.status_code == 403

    # The assigned PoC CAN read them
    res = client.get(f"/admin/internship/reviews/biweekly?person_id={ids['person_id']}", headers=poc_h)
    assert res.status_code == 200
    assert len(res.json["items"]) == 1

    # PoCs cannot open review periods, compile milestones, or finalize decisions
    res = client.post("/admin/internship/reviews/biweekly", json={
        "person_id": ids["person_id"], "period_start": "2026-08-01", "period_end": "2026-08-15"
    }, headers=poc_h)
    assert res.status_code == 403
    res = client.post("/admin/internship/reviews/milestone/compile", json={
        "person_id": ids["person_id"], "review_type": "3_month"
    }, headers=poc_h)
    assert res.status_code == 403

    # PoC sees the pending assessment in their ops queue, scoped to their interns
    res = client.get("/admin/internship/ops-summary", headers=poc_h)
    assert res.status_code == 200
    assert res.json["scope"] == "managed"
    assert res.json["counts"]["action_queue"] == 1
    assert res.json["action_queue"][0]["stage"] == "poc"

    # The other team lead's queue is empty
    res = client.get("/admin/internship/ops-summary", headers=other_h)
    assert res.status_code == 200
    assert res.json["counts"]["action_queue"] == 0


def test_intern_without_poc_goes_straight_to_manager(client, poc_setup, auth_header, app, create_user):
    ids = poc_setup
    from app.extensions import db
    with app.app_context():
        mgr_h = auth_header(User.query.get(ids["manager_id"]))
        solo_user = create_user("solo@test.com", role="user")
        mgr_p = Person.query.filter_by(email="mgr-p@test.com").first() or Person.query.filter_by(user_id=ids["manager_id"]).first()
        solo = Person(first_name="Solo", last_name="Intern", email="solo-p@test.com", user_id=solo_user.id, created_by_id=ids["admin_id"])
        db.session.add(solo)
        db.session.flush()
        emp = Employment(person_id=solo.id, employment_type="intern", status="active",
                         start_date=date(2026, 7, 1), manager_person_id=mgr_p.id, created_by_id=ids["admin_id"])
        db.session.add(emp)
        db.session.commit()
        solo_h = auth_header(solo_user)
        solo_id = solo.id

    res = client.post("/admin/internship/reviews/biweekly", json={
        "person_id": solo_id, "period_start": "2026-07-01", "period_end": "2026-07-15"
    }, headers=mgr_h)
    review_id = res.json["review"]["id"]

    res = client.post(f"/admin/internship/reviews/biweekly/{review_id}/intern-submit",
                      json={"responses": {"a": "b"}}, headers=solo_h)
    assert res.status_code == 200
    # No PoC assigned -> straight to the manager, exactly as before
    assert res.json["review"]["status"] == "pending_manager"
