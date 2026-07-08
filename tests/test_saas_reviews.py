import pytest
from datetime import datetime, date
from app.models import Person, Employment, BiweeklyReview, MilestoneReview, User

@pytest.fixture
def reviews_setup(app, create_user):
    from app.extensions import db
    with app.app_context():
        # Create users
        admin = create_user("admin@test.com", role="admin")
        manager = create_user("mgr@test.com", role="people_manager")
        intern_user = create_user("intern@test.com", role="user")

        # Create Person profile for manager
        mgr_p = Person(first_name="Mgr", last_name="User", email="mgr@test.com", user_id=manager.id, created_by_id=admin.id)
        db.session.add(mgr_p)
        db.session.flush()

        # Create Person profile linked to intern_user
        p = Person(first_name="Jane", last_name="Smith", email="jane@test.com", user_id=intern_user.id, created_by_id=admin.id)
        db.session.add(p)
        db.session.flush()

        # Create Employment profile
        emp = Employment(
            person_id=p.id,
            employment_type="intern",
            intern_track="software",
            status="active",
            start_date=date(2026, 7, 1),
            manager_person_id=mgr_p.id,  # Link to manager profile
            created_by_id=admin.id
        )
        db.session.add(emp)
        db.session.commit()

        # Re-fetch ids
        return admin.id, manager.id, intern_user.id, p.id

def test_biweekly_review_submission_flow(client, reviews_setup, auth_header, app):
    admin_id, manager_id, intern_user_id, person_id = reviews_setup

    with app.app_context():
        mgr = User.query.get(manager_id)
        mgr_headers = auth_header(mgr)
        intern = User.query.get(intern_user_id)
        intern_headers = auth_header(intern)

    # 1. Manager initializes biweekly review
    res = client.post("/admin/internship/reviews/biweekly", json={
        "person_id": person_id,
        "period_start": "2026-07-01",
        "period_end": "2026-07-15"
    }, headers=mgr_headers)
    assert res.status_code == 201
    review_id = res.json["review"]["id"]
    assert len(res.json["review"]["manager_questions"]) > 0

    # 2. Intern submits answers
    res = client.post(f"/admin/internship/reviews/biweekly/{review_id}/intern-submit", json={
        "responses": {
            "How was your sprint?": "Going well, learned React integration."
        }
    }, headers=intern_headers)
    assert res.status_code == 200
    assert res.json["review"]["status"] == "pending_manager"

    # 3. Manager grades review
    res = client.post(f"/admin/internship/reviews/biweekly/{review_id}/manager-submit", json={
        "score_progress": 4,
        "responses": {"Clean code application": "Good clean formatting"},
        "blockers": "None",
        "strengths": "Quick adaptation",
        "action_items": [{"task": "Read more docs", "due": "2026-07-20"}]
    }, headers=mgr_headers)
    assert res.status_code == 200
    assert res.json["review"]["status"] == "completed"
    assert "DRAFT AI" in res.json["review"]["ai_summary"]

def test_milestone_review_flow(client, reviews_setup, auth_header, app):
    admin_id, manager_id, intern_user_id, person_id = reviews_setup

    with app.app_context():
        mgr = User.query.get(manager_id)
        mgr_headers = auth_header(mgr)

    # 1. Compile 3-month review
    res = client.post("/admin/internship/reviews/milestone/compile", json={
        "person_id": person_id,
        "review_type": "3_month"
    }, headers=mgr_headers)
    assert res.status_code == 201
    review_id = res.json["review"]["id"]
    assert res.json["review"]["status"] == "draft"
    assert res.json["review"]["ai_recommendations_approved"] is False

    # 2. Approve AI recommendation
    res = client.post(f"/admin/internship/reviews/milestone/{review_id}/approve-ai", headers=mgr_headers)
    assert res.status_code == 200
    assert res.json["review"]["ai_recommendations_approved"] is True

    # 3. Finalize and Convert
    res = client.post(f"/admin/internship/reviews/milestone/{review_id}/finalize", json={
        "decision": "convert"
    }, headers=mgr_headers)
    assert res.status_code == 200
    assert res.json["review"]["status"] == "released"
    assert res.json["review"]["final_decision"] == "convert"

    # Verify employment was updated to full_time
    with app.app_context():
        person = Person.query.get(person_id)
        assert person.active_employment.employment_type == "full_time"


def test_biweekly_overlapping_period_rejected(client, reviews_setup, auth_header, app):
    admin_id, manager_id, intern_user_id, person_id = reviews_setup

    with app.app_context():
        mgr = User.query.get(manager_id)
        mgr_headers = auth_header(mgr)

    res = client.post("/admin/internship/reviews/biweekly", json={
        "person_id": person_id,
        "period_start": "2026-07-01",
        "period_end": "2026-07-15"
    }, headers=mgr_headers)
    assert res.status_code == 201

    # Exact duplicate is rejected
    res = client.post("/admin/internship/reviews/biweekly", json={
        "person_id": person_id,
        "period_start": "2026-07-01",
        "period_end": "2026-07-15"
    }, headers=mgr_headers)
    assert res.status_code == 400

    # Overlapping period is rejected
    res = client.post("/admin/internship/reviews/biweekly", json={
        "person_id": person_id,
        "period_start": "2026-07-10",
        "period_end": "2026-07-24"
    }, headers=mgr_headers)
    assert res.status_code == 400

    # Missing dates are rejected with 400 (not a 500)
    res = client.post("/admin/internship/reviews/biweekly", json={
        "person_id": person_id
    }, headers=mgr_headers)
    assert res.status_code == 400

    # Inverted range is rejected
    res = client.post("/admin/internship/reviews/biweekly", json={
        "person_id": person_id,
        "period_start": "2026-08-15",
        "period_end": "2026-08-01"
    }, headers=mgr_headers)
    assert res.status_code == 400


def test_unrelated_viewer_cannot_read_reviews(client, reviews_setup, auth_header, app, create_user):
    admin_id, manager_id, intern_user_id, person_id = reviews_setup

    with app.app_context():
        mgr = User.query.get(manager_id)
        mgr_headers = auth_header(mgr)
        outsider = create_user("outsider@test.com", role="viewer")
        outsider_headers = auth_header(outsider)

    res = client.post("/admin/internship/reviews/biweekly", json={
        "person_id": person_id,
        "period_start": "2026-07-01",
        "period_end": "2026-07-15"
    }, headers=mgr_headers)
    assert res.status_code == 201

    # A viewer with no relationship to the person cannot read their reviews
    res = client.get(f"/admin/internship/reviews/biweekly?person_id={person_id}", headers=outsider_headers)
    assert res.status_code == 403

    # Without person_id the unrelated viewer sees nothing
    res = client.get("/admin/internship/reviews/biweekly", headers=outsider_headers)
    assert res.status_code == 200
    assert res.json["items"] == []

    # Milestone reviews are protected the same way
    res = client.post("/admin/internship/reviews/milestone/compile", json={
        "person_id": person_id, "review_type": "3_month"
    }, headers=mgr_headers)
    assert res.status_code == 201

    res = client.get(f"/admin/internship/reviews/milestone?person_id={person_id}", headers=outsider_headers)
    assert res.status_code == 403
    res = client.get("/admin/internship/reviews/milestone", headers=outsider_headers)
    assert res.status_code == 200
    assert res.json["items"] == []


def test_unrelated_manager_cannot_manage_reviews(client, reviews_setup, auth_header, app, create_user):
    admin_id, manager_id, intern_user_id, person_id = reviews_setup

    with app.app_context():
        other_mgr = create_user("othermgr@test.com", role="people_manager")
        other_headers = auth_header(other_mgr)
        mgr = User.query.get(manager_id)
        mgr_headers = auth_header(mgr)

    # A people_manager who does not manage this person cannot open reviews for them
    res = client.post("/admin/internship/reviews/biweekly", json={
        "person_id": person_id,
        "period_start": "2026-07-01",
        "period_end": "2026-07-15"
    }, headers=other_headers)
    assert res.status_code == 403

    # ...nor compile or finalize their milestone reviews
    res = client.post("/admin/internship/reviews/milestone/compile", json={
        "person_id": person_id, "review_type": "3_month"
    }, headers=other_headers)
    assert res.status_code == 403

    res = client.post("/admin/internship/reviews/milestone/compile", json={
        "person_id": person_id, "review_type": "3_month"
    }, headers=mgr_headers)
    assert res.status_code == 201
    review_id = res.json["review"]["id"]

    res = client.post(f"/admin/internship/reviews/milestone/{review_id}/finalize", json={
        "decision": "convert"
    }, headers=other_headers)
    assert res.status_code == 403


def test_finalized_milestone_cannot_be_refinalized(client, reviews_setup, auth_header, app):
    admin_id, manager_id, intern_user_id, person_id = reviews_setup

    with app.app_context():
        mgr = User.query.get(manager_id)
        mgr_headers = auth_header(mgr)

    res = client.post("/admin/internship/reviews/milestone/compile", json={
        "person_id": person_id, "review_type": "6_month"
    }, headers=mgr_headers)
    assert res.status_code == 201
    review_id = res.json["review"]["id"]

    # Finalizing before the draft recommendation is reviewed is rejected
    res = client.post(f"/admin/internship/reviews/milestone/{review_id}/finalize", json={
        "decision": "extend"
    }, headers=mgr_headers)
    assert res.status_code == 400

    res = client.post(f"/admin/internship/reviews/milestone/{review_id}/approve-ai", headers=mgr_headers)
    assert res.status_code == 200

    res = client.post(f"/admin/internship/reviews/milestone/{review_id}/finalize", json={
        "decision": "extend"
    }, headers=mgr_headers)
    assert res.status_code == 200

    res = client.post(f"/admin/internship/reviews/milestone/{review_id}/finalize", json={
        "decision": "release"
    }, headers=mgr_headers)
    assert res.status_code == 400


def test_completed_biweekly_cannot_be_resubmitted_by_intern(client, reviews_setup, auth_header, app):
    admin_id, manager_id, intern_user_id, person_id = reviews_setup

    with app.app_context():
        mgr = User.query.get(manager_id)
        mgr_headers = auth_header(mgr)
        intern = User.query.get(intern_user_id)
        intern_headers = auth_header(intern)

    res = client.post("/admin/internship/reviews/biweekly", json={
        "person_id": person_id,
        "period_start": "2026-07-01",
        "period_end": "2026-07-15"
    }, headers=mgr_headers)
    review_id = res.json["review"]["id"]

    client.post(f"/admin/internship/reviews/biweekly/{review_id}/intern-submit",
                json={"responses": {"q": "a"}}, headers=intern_headers)
    res = client.post(f"/admin/internship/reviews/biweekly/{review_id}/manager-submit", json={
        "score_progress": 4
    }, headers=mgr_headers)
    assert res.status_code == 200

    res = client.post(f"/admin/internship/reviews/biweekly/{review_id}/intern-submit",
                      json={"responses": {"q": "changed"}}, headers=intern_headers)
    assert res.status_code == 400


def test_finalize_milestone_respects_governance_policy(client, reviews_setup, auth_header, app, create_user):
    admin_id, manager_id, intern_user_id, person_id = reviews_setup

    with app.app_context():
        from app.extensions import db
        from app.models import Policy, MilestoneReview

        mgr = User.query.get(manager_id)
        mgr_headers = auth_header(mgr)
        approver = create_user("hr-approver@test.com", role="admin")
        approver_headers = auth_header(approver)

        policy = Policy(
            name="Milestone Finalization Approval",
            action="people.finalize_milestone",
            requires_approval=True,
            approvals_required=1,
            approver_role="admin",
            is_active=True,
            created_by=approver.id,
        )
        db.session.add(policy)
        db.session.commit()

    res = client.post("/admin/internship/reviews/milestone/compile", json={
        "person_id": person_id, "review_type": "3_month"
    }, headers=mgr_headers)
    assert res.status_code == 201
    review_id = res.json["review"]["id"]

    res = client.post(f"/admin/internship/reviews/milestone/{review_id}/approve-ai", headers=mgr_headers)
    assert res.status_code == 200

    # With the policy active, finalize returns a pending approval instead of executing
    res = client.post(f"/admin/internship/reviews/milestone/{review_id}/finalize", json={
        "decision": "convert"
    }, headers=mgr_headers)
    assert res.status_code == 202
    approval_id = res.json["approval_request"]["id"]

    with app.app_context():
        review = MilestoneReview.query.get(review_id)
        assert review.status == "draft"

    # Approving through governance executes the decision
    res = client.post(f"/admin/approvals/{approval_id}/approve", headers=approver_headers)
    assert res.status_code == 200

    with app.app_context():
        review = MilestoneReview.query.get(review_id)
        assert review.status == "released"
        assert review.final_decision == "convert"
        person = Person.query.get(person_id)
        assert person.active_employment.employment_type == "full_time"


def test_draft_approval_can_be_revoked(client, reviews_setup, auth_header, app):
    admin_id, manager_id, intern_user_id, person_id = reviews_setup

    with app.app_context():
        mgr = User.query.get(manager_id)
        mgr_headers = auth_header(mgr)

    res = client.post("/admin/internship/reviews/milestone/compile", json={
        "person_id": person_id, "review_type": "3_month"
    }, headers=mgr_headers)
    review_id = res.json["review"]["id"]

    res = client.post(f"/admin/internship/reviews/milestone/{review_id}/approve-ai", headers=mgr_headers)
    assert res.status_code == 200
    assert res.json["review"]["ai_recommendations_approved"] is True

    # Manager reconsiders: revoke while still a draft
    res = client.post(f"/admin/internship/reviews/milestone/{review_id}/approve-ai",
                      json={"approved": False}, headers=mgr_headers)
    assert res.status_code == 200
    assert res.json["review"]["ai_recommendations_approved"] is False

    # Finalize is blocked again after revocation
    res = client.post(f"/admin/internship/reviews/milestone/{review_id}/finalize", json={
        "decision": "convert"
    }, headers=mgr_headers)
    assert res.status_code == 400

    # Re-approve and finalize; approval is then immutable
    client.post(f"/admin/internship/reviews/milestone/{review_id}/approve-ai", headers=mgr_headers)
    res = client.post(f"/admin/internship/reviews/milestone/{review_id}/finalize", json={
        "decision": "extend"
    }, headers=mgr_headers)
    assert res.status_code == 200

    res = client.post(f"/admin/internship/reviews/milestone/{review_id}/approve-ai",
                      json={"approved": False}, headers=mgr_headers)
    assert res.status_code == 400
