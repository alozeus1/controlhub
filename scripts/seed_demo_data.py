#!/usr/bin/env python3
"""
Seed script to create mock SaaS organization data:
Managers, Mentors, Interns, Onboarding Checklists, Biweekly Reviews, and Milestone Reviews.
"""
import os
import sys
from datetime import date, datetime, timedelta

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.extensions import db
from app.models import (
    User, Person, Employment, OnboardingTemplateItem,
    PersonOnboardingItem, BiweeklyReview, MilestoneReview
)

def seed_demo_data():
    app = create_app()

    with app.app_context():
        # This script WIPES all onboarding, employment, and review tables before
        # seeding. Refuse to run against a production environment.
        environment = (app.config.get("ENVIRONMENT") or os.environ.get("ENVIRONMENT") or "").lower()
        if environment == "production" and os.environ.get("SEED_DEMO_FORCE") != "1":
            print("Refusing to seed demo data in production (set SEED_DEMO_FORCE=1 to override).")
            sys.exit(1)

        print("Clearing old demo data...")
        # Delete existing items to make seed repeatable
        PersonOnboardingItem.query.delete()
        OnboardingTemplateItem.query.delete()
        BiweeklyReview.query.delete()
        MilestoneReview.query.delete()
        Employment.query.delete()
        
        # Don't delete all users/people in case admin exists, but clear demo users
        demo_emails = [
            "manager@example.com", "mentor@example.com", 
            "intern1@example.com", "intern2@example.com", "intern3@example.com"
        ]
        for email in demo_emails:
            p = Person.query.filter_by(email=email).first()
            if p:
                db.session.delete(p)
            u = User.query.filter_by(email=email).first()
            if u:
                db.session.delete(u)
        db.session.commit()

        print("Seeding Users & People profiles...")
        # 1. Admin/HR Creator
        admin = User.query.filter_by(role="admin").first()
        if not admin:
            admin = User(email="admin@example.com", role="admin")
            admin.set_password("Admin123!")
            db.session.add(admin)
            db.session.commit()

        # 2. Manager
        mgr_user = User(email="manager@example.com", role="people_manager")
        mgr_user.set_password("Manager123!")
        db.session.add(mgr_user)
        db.session.flush()
        mgr_person = Person(
            first_name="Marcus", last_name="Aurelius", email="manager@example.com",
            user_id=mgr_user.id, team="Engineering", department="Operations",
            taiga_username="marcus_ops", mattermost_username="marcus_mm",
            created_by_id=admin.id
        )
        db.session.add(mgr_person)
        
        # 3. Mentor
        mentor_user = User(email="mentor@example.com", role="viewer")
        mentor_user.set_password("Mentor123!")
        db.session.add(mentor_user)
        db.session.flush()
        mentor_person = Person(
            first_name="Seneca", last_name="Younger", email="mentor@example.com",
            user_id=mentor_user.id, team="Engineering", department="Mentorship",
            taiga_username="seneca_guide", mattermost_username="seneca_mm",
            created_by_id=admin.id
        )
        db.session.add(mentor_person)
        db.session.commit()

        # 4. Onboarding Templates
        templates = [
            OnboardingTemplateItem(
                title="Sign Employee NDA", description="Review and sign the operational non-disclosure agreement.",
                role_target="intern", owner_role="intern", days_to_complete=3, created_by_id=admin.id
            ),
            OnboardingTemplateItem(
                title="Provision Communication Accounts", description="Provision Mattermost, Jira/Taiga, and email aliases.",
                role_target="intern", owner_role="manager", days_to_complete=2, created_by_id=admin.id
            ),
            OnboardingTemplateItem(
                title="Configure Keyless AWS LocalStack", description="Perform local smoke test to verify local AWS WIF integrations.",
                role_target="intern", owner_role="intern", days_to_complete=7, created_by_id=admin.id
            ),
            OnboardingTemplateItem(
                title="Complete Cyber Security Awareness Training", description="Read SECURITY.md and complete the initial compliance briefing.",
                role_target="intern", owner_role="intern", days_to_complete=10, created_by_id=admin.id
            )
        ]
        db.session.add_all(templates)
        db.session.commit()

        # 5. Interns (John, Alice, Bob)
        # Intern 1: John (Software) - 2 months in
        john_user = User(email="intern1@example.com", role="user")
        john_user.set_password("Intern123!")
        db.session.add(john_user)
        db.session.flush()
        john = Person(
            first_name="John", last_name="Developer", email="intern1@example.com",
            user_id=john_user.id, team="Frontend Dev", department="Engineering", cohort="Cohort 2026-A",
            taiga_username="john_dev", mattermost_username="john_mm",
            assigned_projects=["controlhub-v2-migration"],
            signed_documents={"NDA": datetime.utcnow().isoformat()},
            risk_flags=[],
            growth_summary="John has integrated well. Demonstrates strong commitment to clean React components and TypeScript styling.",
            created_by_id=admin.id
        )
        db.session.add(john)
        db.session.flush()
        john_emp = Employment(
            person_id=john.id, employment_type="intern", intern_track="software",
            status="active", title="Frontend Engineering Intern",
            start_date=date.today() - timedelta(days=60), end_date=date.today() + timedelta(days=120),
            compensation_type="stipend", salary_amount=1500.00, currency="USD",
            manager_person_id=mgr_person.id, mentor_person_id=mentor_person.id,
            created_by_id=admin.id
        )
        db.session.add(john_emp)

        # Intern 2: Alice (DevOps) - 1 month in (at risk)
        alice_user = User(email="intern2@example.com", role="user")
        alice_user.set_password("Intern123!")
        db.session.add(alice_user)
        db.session.flush()
        alice = Person(
            first_name="Alice", last_name="SecOps", email="intern2@example.com",
            user_id=alice_user.id, team="Infrastructure", department="Engineering", cohort="Cohort 2026-A",
            taiga_username="alice_ops", mattermost_username="alice_mm",
            assigned_projects=["localstack-s3-upgrade"],
            signed_documents={"NDA": datetime.utcnow().isoformat()},
            risk_flags=["low_ticket_velocity", "unresolved_blockers"],
            growth_summary="Alice is struggling with local credentials mapping. Requires direct mentorship session to assist in configuration.",
            created_by_id=admin.id
        )
        db.session.add(alice)
        db.session.flush()
        alice_emp = Employment(
            person_id=alice.id, employment_type="intern", intern_track="devops",
            status="active", title="DevOps Engineering Intern",
            start_date=date.today() - timedelta(days=30), end_date=date.today() + timedelta(days=150),
            compensation_type="stipend", salary_amount=1600.00, currency="USD",
            manager_person_id=mgr_person.id, mentor_person_id=mentor_person.id,
            created_by_id=admin.id
        )
        db.session.add(alice_emp)

        # Intern 3: Bob (DevSecOps) - 5 months in (completed onboarding, ready for final review)
        bob_user = User(email="intern3@example.com", role="user")
        bob_user.set_password("Bob1234!")
        db.session.add(bob_user)
        db.session.flush()
        bob = Person(
            first_name="Bob", last_name="Securite", email="intern3@example.com",
            user_id=bob_user.id, team="Security Auditing", department="Security", cohort="Cohort 2025-B",
            taiga_username="bob_sec", mattermost_username="bob_mm",
            assigned_projects=["static-code-scanner-setup", "siem-cef-validation"],
            signed_documents={"NDA": datetime.utcnow().isoformat(), "Security_Declaration": datetime.utcnow().isoformat()},
            risk_flags=[],
            growth_summary="Bob has demonstrated superadmin-level maturity in identifying secrets leakage vectors. Highly recommended for conversion.",
            created_by_id=admin.id
        )
        db.session.add(bob)
        db.session.flush()
        bob_emp = Employment(
            person_id=bob.id, employment_type="intern", intern_track="devsecops_cybersecurity",
            status="active", title="DevSecOps Intern",
            start_date=date.today() - timedelta(days=150), end_date=date.today() + timedelta(days=30),
            compensation_type="stipend", salary_amount=1700.00, currency="USD",
            manager_person_id=mgr_person.id, mentor_person_id=mentor_person.id,
            created_by_id=admin.id
        )
        db.session.add(bob_emp)
        db.session.commit()

        # 6. Seed Onboarding Items Checklist
        # John (completed most)
        for idx, t in enumerate(templates):
            checked = idx < 3
            item = PersonOnboardingItem(
                person_id=john.id, template_item_id=t.id, checked=checked,
                checked_at=datetime.utcnow() - timedelta(days=10) if checked else None,
                due_date=john_emp.start_date + timedelta(days=t.days_to_complete),
                status="completed" if checked else "pending",
                item_type="document" if "NDA" in t.title else "general"
            )
            db.session.add(item)
            
        # Alice (completed some, one overdue)
        for idx, t in enumerate(templates):
            checked = idx < 1
            item = PersonOnboardingItem(
                person_id=alice.id, template_item_id=t.id, checked=checked,
                checked_at=datetime.utcnow() - timedelta(days=20) if checked else None,
                due_date=alice_emp.start_date + timedelta(days=t.days_to_complete),
                status="completed" if checked else ("pending" if idx != 1 else "overdue"),
                item_type="document" if "NDA" in t.title else "general"
            )
            db.session.add(item)
            
        # Bob (completed all)
        for t in templates:
            item = PersonOnboardingItem(
                person_id=bob.id, template_item_id=t.id, checked=True,
                checked_at=datetime.utcnow() - timedelta(days=40),
                due_date=bob_emp.start_date + timedelta(days=t.days_to_complete),
                status="completed",
                item_type="general"
            )
            db.session.add(item)
        db.session.commit()

        # 7. Seed Biweekly Reviews
        # John: 3 reviews (4/5, 4/5, 5/5)
        for i in range(3):
            days_ago = 45 - (i * 14)
            rev = BiweeklyReview(
                person_id=john.id, reviewer_id=mgr_user.id,
                period_start=date.today() - timedelta(days=days_ago + 14),
                period_end=date.today() - timedelta(days=days_ago),
                status="completed",
                intern_responses={"accomplishments": f"Accomplished sprint milestone #{i+1}."},
                manager_questions=["Is the intern making progress?", "Are code reviews approved?"],
                manager_responses={"notes": f"Excellent output for sprint #{i+1}."},
                score_progress=4 if i < 2 else 5,
                blockers="None", strengths="Good clean code practices",
                action_items=[{"task": "Prepare for UI deployment", "due": "2026-08-01"}],
                ai_summary=f"[DRAFT AI Summary] Intern completed frontend tasks. Score {4 if i < 2 else 5}/5.",
                created_at=datetime.utcnow() - timedelta(days=days_ago),
                completed_at=datetime.utcnow() - timedelta(days=days_ago)
            )
            db.session.add(rev)

        # Alice: 2 reviews (3/5, 2/5 - showing downward trend/risk)
        for i in range(2):
            days_ago = 28 - (i * 14)
            rev = BiweeklyReview(
                person_id=alice.id, reviewer_id=mgr_user.id,
                period_start=date.today() - timedelta(days=days_ago + 14),
                period_end=date.today() - timedelta(days=days_ago),
                status="completed",
                intern_responses={"accomplishments": f"Worked on Docker setups. Blocked by AWS credential mounts."},
                manager_questions=["Is the intern responding in MM?", "Are there technical gaps?"],
                manager_responses={"notes": f"Requires technical coaching. Stuck on environment setups."},
                score_progress=3 if i == 0 else 2,
                blockers="AWS WIF provider routing errors", strengths="Eager to learn",
                action_items=[{"task": "Pair programming session with mentor", "due": "2026-07-15"}],
                ai_summary=f"[DRAFT AI Summary] Intern has significant blockers on DevOps config. Score {3 if i == 0 else 2}/5.",
                created_at=datetime.utcnow() - timedelta(days=days_ago),
                completed_at=datetime.utcnow() - timedelta(days=days_ago)
            )
            db.session.add(rev)

        # Bob: 5 reviews (all completed, average 4.8)
        for i in range(5):
            days_ago = 70 - (i * 14)
            rev = BiweeklyReview(
                person_id=bob.id, reviewer_id=mgr_user.id,
                period_start=date.today() - timedelta(days=days_ago + 14),
                period_end=date.today() - timedelta(days=days_ago),
                status="completed",
                intern_responses={"accomplishments": "Refactored security scanning logic, audited JWT configuration."},
                manager_questions=["Is security compliance met?", "Are runbooks updated?"],
                manager_responses={"notes": "Outperforming expectations. Bob acts independently."},
                score_progress=5 if i % 2 == 0 else 4,
                blockers="None", strengths="Expert security mindset",
                action_items=[{"task": "Prepare project presentation", "due": "2026-06-30"}],
                ai_summary="[DRAFT AI Summary] Bob completed runbooks audits. Score 5/5.",
                created_at=datetime.utcnow() - timedelta(days=days_ago),
                completed_at=datetime.utcnow() - timedelta(days=days_ago)
            )
            db.session.add(rev)

        # Create one pending biweekly review for Alice to show active action items
        pending_rev = BiweeklyReview(
            person_id=alice.id,
            period_start=date.today() - timedelta(days=1),
            period_end=date.today() + timedelta(days=13),
            status="pending_intern",
            manager_questions=["How to overcome AWS WIF blocker?"],
            intern_responses={},
            manager_responses={}
        )
        db.session.add(pending_rev)
        
        # 8. Seed Milestone Reviews
        # Bob has a completed 3-month review and a draft 6-month review
        bob_3m = MilestoneReview(
            person_id=bob.id, review_type="3_month", status="released",
            compiled_score=4.6, onboarding_progress=100.00,
            taiga_activity_summary={"completed_tasks": 24, "participation_score": 92},
            mattermost_activity_summary={"posts_count": 89, "active_days": 42},
            disciplinary_summary="No warnings or issues logged.",
            ai_recommendations="[DRAFT APPROVED] Intern is exceeding performance criteria. Onboarding checklist complete. Suggest full conversion.",
            ai_recommendations_approved=True,
            final_decision="extend", # extended to 6-month
            decision_by_id=mgr_user.id,
            decision_date=date.today() - timedelta(days=60),
            report_card_json={"competencies": {"technical": 4.8, "communication": 4.5, "velocity": 4.2}}
        )
        db.session.add(bob_3m)
        
        bob_6m = MilestoneReview(
            person_id=bob.id, review_type="6_month", status="draft",
            compiled_score=4.8, onboarding_progress=100.00,
            taiga_activity_summary={"completed_tasks": 58, "participation_score": 96},
            mattermost_activity_summary={"posts_count": 172, "active_days": 89},
            disciplinary_summary="No warnings or issues logged.",
            ai_recommendations="[DRAFT AI RECOMMENDATION] Highly capable candidate. Solid contribution to SIEM integrations. Strongly recommend converting to a Full-Time Software Engineer I.",
            ai_recommendations_approved=False,
            report_card_json={"competencies": {"technical": 5.0, "communication": 4.8, "velocity": 4.6, "collaboration": 4.8, "problem_solving": 4.8}}
        )
        db.session.add(bob_6m)

        db.session.commit()
        print("Demo data seeded successfully!")

if __name__ == "__main__":
    seed_demo_data()
