import pytest
from datetime import date
from app.models import Person, Employment, OnboardingTemplateItem, PersonOnboardingItem, User

@pytest.fixture
def onboarding_setup(app, create_user):
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

        # Create template items
        t1 = OnboardingTemplateItem(title="Sign NDA", description="Sign nondisclosure agreement", role_target="intern", owner_role="intern", days_to_complete=3, created_by_id=admin.id)
        t2 = OnboardingTemplateItem(title="Create Slack", description="Create communication access", role_target="intern", owner_role="manager", days_to_complete=5, created_by_id=admin.id)
        db.session.add_all([t1, t2])
        db.session.flush()

        # Create Person profile for intern
        p = Person(first_name="John", last_name="Doe", email="john@test.com", user_id=intern_user.id, created_by_id=admin.id)
        db.session.add(p)
        db.session.flush()

        # Create Employment profile
        emp = Employment(
            person_id=p.id,
            employment_type="intern",
            intern_track="software",
            status="active",
            start_date=date(2026, 7, 1),
            manager_person_id=mgr_p.id,
            created_by_id=admin.id
        )
        db.session.add(emp)
        db.session.commit()

        # Re-fetch ids
        return admin.id, manager.id, intern_user.id, p.id, t1.id, t2.id

def test_initialize_onboarding_requires_role(client, onboarding_setup, auth_header, app):
    admin_id, manager_id, intern_user_id, person_id, t1_id, t2_id = onboarding_setup
    
    with app.app_context():
        user = User.query.get(intern_user_id)
        headers = auth_header(user)

    # Normal user should be rejected (requires people_manager role)
    res = client.post(f"/admin/internship/people/{person_id}/onboarding/initialize", headers=headers)
    assert res.status_code == 403

    # Manager should be accepted
    with app.app_context():
        mgr = User.query.get(manager_id)
        mgr_headers = auth_header(mgr)
        
    res = client.post(f"/admin/internship/people/{person_id}/onboarding/initialize", headers=mgr_headers)
    assert res.status_code == 201
    
    with app.app_context():
        items = PersonOnboardingItem.query.filter_by(person_id=person_id).all()
        assert len(items) == 2
        assert items[0].due_date == date(2026, 7, 4)  # 2026-07-01 + 3 days

def test_patch_onboarding_item(client, onboarding_setup, auth_header, app):
    admin_id, manager_id, intern_user_id, person_id, t1_id, t2_id = onboarding_setup

    with app.app_context():
        mgr = User.query.get(manager_id)
        mgr_headers = auth_header(mgr)

    # Initialize first
    client.post(f"/admin/internship/people/{person_id}/onboarding/initialize", headers=mgr_headers)

    with app.app_context():
        item = PersonOnboardingItem.query.filter_by(person_id=person_id, template_item_id=t1_id).first()
        item_id = item.id

    # Check status update
    res = client.patch(f"/admin/internship/onboarding-item/{item_id}", json={
        "checked": True,
        "status": "completed"
    }, headers=mgr_headers)
    assert res.status_code == 200
    assert res.json["item"]["checked"] is True
    assert res.json["item"]["status"] == "completed"
