import pytest
from datetime import date, datetime, timedelta
from app.models import (
    Person, Employment, User, BiweeklyReview, MilestoneReview,
    OnboardingTemplateItem, PersonOnboardingItem,
)


@pytest.fixture
def phase2_setup(app, create_user):
    from app.extensions import db
    with app.app_context():
        admin = create_user("admin@test.com", role="admin")
        manager = create_user("mgr@test.com", role="people_manager")
        intern_user = create_user("intern@test.com", role="user")

        mgr_p = Person(first_name="Mgr", last_name="User", email="mgr@test.com", user_id=manager.id, created_by_id=admin.id)
        db.session.add(mgr_p)
        db.session.flush()

        p = Person(
            first_name="Jane", last_name="Smith", email="jane@test.com",
            user_id=intern_user.id, created_by_id=admin.id,
            risk_flags=["low_ticket_velocity"],
        )
        db.session.add(p)
        db.session.flush()

        emp = Employment(
            person_id=p.id, employment_type="intern", intern_track="software",
            status="active", start_date=date.today() - timedelta(days=100),
            manager_person_id=mgr_p.id, created_by_id=admin.id,
        )
        db.session.add(emp)

        t_intern = OnboardingTemplateItem(
            title="Sign NDA", role_target="intern", owner_role="intern",
            days_to_complete=3, created_by_id=admin.id,
        )
        t_manager = OnboardingTemplateItem(
            title="Provision accounts", role_target="intern", owner_role="manager",
            days_to_complete=2, created_by_id=admin.id,
        )
        db.session.add_all([t_intern, t_manager])
        db.session.flush()

        # One overdue intern-owned item, one manager-owned item
        i1 = PersonOnboardingItem(
            person_id=p.id, template_item_id=t_intern.id, checked=False,
            due_date=date.today() - timedelta(days=5), status="pending",
        )
        i2 = PersonOnboardingItem(
            person_id=p.id, template_item_id=t_manager.id, checked=False,
            due_date=date.today() + timedelta(days=5), status="pending",
        )
        db.session.add_all([i1, i2])

        # A review waiting on the manager, plus a released and a draft milestone
        rev = BiweeklyReview(
            person_id=p.id, period_start=date.today() - timedelta(days=14),
            period_end=date.today() - timedelta(days=1), status="pending_manager",
            intern_responses={"accomplishments": "did things"},
            ai_summary="[DRAFT AI Summary] internal draft",
        )
        released = MilestoneReview(
            person_id=p.id, review_type="3_month", status="released",
            compiled_score=4.0, onboarding_progress=50.0, final_decision="extend",
            ai_recommendations="[DRAFT] internal reasoning",
            disciplinary_summary="internal note",
        )
        draft = MilestoneReview(
            person_id=p.id, review_type="6_month", status="draft",
            compiled_score=4.5, ai_recommendations="[DRAFT] pending",
        )
        db.session.add_all([rev, draft, released])
        db.session.commit()

        return {
            "admin_id": admin.id, "manager_id": manager.id, "intern_user_id": intern_user.id,
            "person_id": p.id, "intern_item_id": i1.id, "manager_item_id": i2.id,
            "pending_review_id": rev.id,
        }


def test_my_journey_returns_sanitized_own_data(client, phase2_setup, auth_header, app):
    ids = phase2_setup
    with app.app_context():
        intern = User.query.get(ids["intern_user_id"])
        headers = auth_header(intern)

    res = client.get("/admin/internship/my-journey", headers=headers)
    assert res.status_code == 200
    body = res.json
    assert body["linked"] is True
    assert body["profile"]["full_name"] == "Jane Smith"
    assert body["profile"]["employment"]["intern_track"] == "software"
    # Internal-only fields never reach the intern payload
    assert "risk_flags" not in body["profile"]
    assert "growth_summary" not in body["profile"]

    assert body["onboarding"]["total"] == 2

    assert len(body["biweekly_reviews"]) == 1
    assert "ai_summary" not in body["biweekly_reviews"][0]

    # Only released milestones, without draft AI text or disciplinary notes
    assert len(body["milestone_reviews"]) == 1
    m = body["milestone_reviews"][0]
    assert m["status"] == "released"
    assert "ai_recommendations" not in m
    assert "disciplinary_summary" not in m


def test_my_journey_unlinked_user(client, create_user, auth_header, app):
    with app.app_context():
        loner = create_user("noprofile@test.com", role="user")
        headers = auth_header(loner)

    res = client.get("/admin/internship/my-journey", headers=headers)
    assert res.status_code == 200
    assert res.json["linked"] is False


def test_intern_can_self_check_own_items_only(client, phase2_setup, auth_header, app):
    ids = phase2_setup
    with app.app_context():
        intern = User.query.get(ids["intern_user_id"])
        headers = auth_header(intern)
        other = create_second_intern(app, ids)

    # Own intern-owned item: allowed
    res = client.patch(f"/admin/internship/onboarding-item/{ids['intern_item_id']}",
                       json={"checked": True, "status": "completed"}, headers=headers)
    assert res.status_code == 200
    assert res.json["item"]["checked"] is True

    # Own item but manager-owned: denied
    res = client.patch(f"/admin/internship/onboarding-item/{ids['manager_item_id']}",
                       json={"checked": True}, headers=headers)
    assert res.status_code == 403

    # Own intern-owned item but touching restricted fields: denied
    res = client.patch(f"/admin/internship/onboarding-item/{ids['intern_item_id']}",
                       json={"checked": False, "due_date": "2027-01-01"}, headers=headers)
    assert res.status_code == 400

    # Another intern's item: denied
    res = client.patch(f"/admin/internship/onboarding-item/{other['item_id']}",
                       json={"checked": True}, headers=headers)
    assert res.status_code == 403


def create_second_intern(app, ids):
    from app.extensions import db
    from app.models import User as U
    other_user = U(email="other@test.com", role="user", is_active=True)
    other_user.set_password("Pass1234!")
    db.session.add(other_user)
    db.session.flush()
    other_p = Person(first_name="Other", last_name="Intern", email="other-p@test.com",
                     user_id=other_user.id, created_by_id=ids["admin_id"])
    db.session.add(other_p)
    db.session.flush()
    tmpl = OnboardingTemplateItem.query.filter_by(owner_role="intern").first()
    item = PersonOnboardingItem(person_id=other_p.id, template_item_id=tmpl.id, checked=False)
    db.session.add(item)
    db.session.commit()
    return {"user_id": other_user.id, "person_id": other_p.id, "item_id": item.id}


def test_ops_summary_scoping(client, phase2_setup, auth_header, app, create_user):
    ids = phase2_setup
    with app.app_context():
        mgr = User.query.get(ids["manager_id"])
        mgr_headers = auth_header(mgr)
        other_mgr = create_user("othermgr@test.com", role="people_manager")
        other_headers = auth_header(other_mgr)
        viewer = create_user("viewer@test.com", role="viewer")
        viewer_headers = auth_header(viewer)
        admin = User.query.get(ids["admin_id"])
        admin_headers = auth_header(admin)

    # Viewer role is below people_manager
    res = client.get("/admin/internship/ops-summary", headers=viewer_headers)
    assert res.status_code == 403

    # The intern's manager sees the pending review, overdue onboarding,
    # draft decision, and the at-risk flag for their direct report
    res = client.get("/admin/internship/ops-summary", headers=mgr_headers)
    assert res.status_code == 200
    body = res.json
    assert body["scope"] == "managed"
    assert body["counts"]["action_queue"] == 1
    assert body["action_queue"][0]["person_id"] == ids["person_id"]
    assert body["counts"]["overdue_onboarding"] == 1
    assert body["counts"]["pending_decisions"] == 1
    assert body["counts"]["at_risk"] == 1
    assert "low_ticket_velocity" in body["at_risk"][0]["risk_flags"]

    # A manager with no linked person profile sees an empty scope, not other people's data
    res = client.get("/admin/internship/ops-summary", headers=other_headers)
    assert res.status_code == 200
    assert res.json["scope"] == "none"
    assert res.json["action_queue"] == []

    # Admin sees everything program-wide
    res = client.get("/admin/internship/ops-summary", headers=admin_headers)
    assert res.status_code == 200
    assert res.json["scope"] == "all"
    assert res.json["counts"]["action_queue"] == 1
