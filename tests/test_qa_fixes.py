"""
Regression tests for the Operations-module QA fixes.
"""
import pytest


@pytest.fixture
def admin(create_user):
    return create_user("admin@x.com", role="admin")


# ─── Bug 1: workflow start-run must not 500 on empty-string ids ────────────────

def test_start_run_coerces_empty_subject_id(client, admin, auth_header):
    from app.extensions import db
    from app.models import WorkflowTemplate, WorkflowTemplateStep
    with client.application.app_context():
        t = WorkflowTemplate(name="Onb", workflow_type="onboarding", created_by_id=admin.id)
        db.session.add(t)
        db.session.flush()
        db.session.add(WorkflowTemplateStep(template_id=t.id, order=1, title="Step 1"))
        db.session.commit()
        tid = t.id
    # Empty-string subject_user_id used to insert "" into an int FK → 500.
    r = client.post("/admin/workflows/runs", headers=auth_header(admin),
                    json={"template_id": str(tid), "subject_user_id": "", "subject_name": "New Hire"})
    assert r.status_code == 201

    # No subject at all → clean 400, not 500.
    r2 = client.post("/admin/workflows/runs", headers=auth_header(admin), json={"template_id": tid})
    assert r2.status_code == 400
    assert "subject" in r2.get_json()["error"].lower()


# ─── Bug 3: approvals guard against a missing policy ───────────────────────────

def test_approve_missing_policy_returns_409_not_500(client, admin, create_user, auth_header):
    from app.extensions import db
    from app.models import Policy, ApprovalRequest
    requester = create_user("req@x.com", role="user")
    with client.application.app_context():
        pol = Policy(name="P", action="upload.delete", requires_approval=True,
                     approvals_required=1, approver_role="admin")
        db.session.add(pol)
        db.session.commit()
        ar = ApprovalRequest(policy_id=pol.id, requester_id=requester.id, action="upload.delete",
                             status="pending")
        db.session.add(ar)
        db.session.commit()
        arid = ar.id
        # Raw-delete the policy row (bypassing ORM cascade) to leave a dangling FK,
        # simulating a deleted policy so approval.policy resolves to None.
        from sqlalchemy import text
        db.session.execute(text("DELETE FROM policy WHERE id = :id"), {"id": pol.id})
        db.session.commit()
    r = client.post(f"/admin/approvals/{arid}/approve", headers=auth_header(admin), json={})
    assert r.status_code == 409
    assert "policy" in r.get_json()["error"].lower()


# ─── Bug 4: license cost stats keys + owner_email persistence ──────────────────

def test_license_stats_keys_and_owner_email(client, admin, auth_header):
    client.post("/admin/licenses", headers=auth_header(admin), json={
        "vendor": "GitHub", "product": "Enterprise", "cost_monthly": 100,
        "owner": "ops@webforx.tech", "renewal_date": "2026-09-15",
    })
    stats = client.get("/admin/licenses/stats", headers=auth_header(admin)).get_json()
    assert stats["total_monthly_cost"] == 100.0
    assert stats["total_annual_cost"] == 1200.0
    lic = client.get("/admin/licenses", headers=auth_header(admin)).get_json()["items"][0]
    assert lic["owner_email"] == "ops@webforx.tech"     # persisted, not discarded
    assert lic["owner"] == "ops@webforx.tech"


# ─── Bug 5: cost summary exposes total_spend as an array-safe shape ────────────

def test_cost_summary_total_spend(client, admin, auth_header):
    client.post("/admin/costs", headers=auth_header(admin), json={
        "cloud_provider": "aws", "period": "2026-07", "amount": 250, "service_name": "EC2",
    })
    client.post("/admin/costs", headers=auth_header(admin), json={
        "cloud_provider": "gcp", "period": "2026-07", "amount": 150, "service_name": "GKE",
    })
    s = client.get("/admin/costs/summary", headers=auth_header(admin)).get_json()
    assert s["total_spend"] == 400.0
    assert isinstance(s["by_provider"], list)          # array — frontend must not Object.entries it
    assert all("provider" in row and "total" in row for row in s["by_provider"])


# ─── Bug 6: People metadata exposes authoritative active_cohorts ───────────────

def test_people_metadata_active_cohorts(client, admin, auth_header):
    from app.extensions import db
    from app.models import InternshipCohort, InternshipProgram
    with client.application.app_context():
        prog = InternshipProgram(name="2026 Program", status="active", created_by_id=admin.id)
        db.session.add(prog)
        db.session.flush()
        common = dict(program_id=prog.id, track="Engineering", created_by_id=admin.id)
        db.session.add(InternshipCohort(name="Summer 26", status="active", **common))
        db.session.add(InternshipCohort(name="Winter 25", status="completed", **common))
        db.session.commit()
    meta = client.get("/admin/people/metadata", headers=auth_header(admin)).get_json()
    assert meta["active_cohorts"] == 1                 # only the 'active' one
