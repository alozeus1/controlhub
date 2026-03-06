from datetime import datetime, timedelta

from app.extensions import db
from app.models import AgentRequest, AuditLog, Employment, ExternalDestination, GeneratedArtifact, Person
import app.services.agent_tools as agent_tools


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


def _approve(client, auth_header, approver, approval_id):
    return client.post(f"/admin/approvals/{approval_id}/approve", headers=auth_header(approver))


def _create_people_seed(manager, approver):
    manager_person = _make_person(manager.id, "Mira", "Manager", "mira.manager@acme.test", user_id=manager.id)
    direct = _make_person(approver.id, "Dana", "Direct", "dana.direct@acme.test", team="Platform")
    _make_employment(approver.id, direct.id, manager_person_id=manager_person.id, title="Engineer")
    db.session.commit()


def _create_and_approve_request(client, auth_header, requester, approver, payload):
    create_resp = client.post("/admin/agent-requests", json=payload, headers=auth_header(requester))
    assert create_resp.status_code == 202

    data = create_resp.get_json()
    request_id = data["request"]["id"]
    approval_id = data["approval_request"]["id"]

    approve_resp = _approve(client, auth_header, approver, approval_id)
    assert approve_resp.status_code == 200

    request_record = AgentRequest.query.get(request_id)
    assert request_record.status == "completed"

    artifact = GeneratedArtifact.query.filter_by(agent_request_id=request_id).order_by(GeneratedArtifact.id.desc()).first()
    assert artifact is not None
    return request_record, artifact


def test_agent_template_field_allowlist_enforced(client, create_user, auth_header):
    manager = create_user("manager-fields@acme.test", role="people_manager")
    approver = create_user("approver-fields@acme.test", role="admin")
    _create_people_seed(manager, approver)

    resp = client.post(
        "/admin/agent-requests",
        json={
            "module_scope": "people",
            "template_id": "employee_directory",
            "output_type": "csv",
            "destination_type": "download",
            "filters_json": {"fields": ["email", "password_hash"]},
        },
        headers=auth_header(manager),
    )
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "VALIDATION_ERROR"


def test_external_destination_allowlist_enforced(client, create_user, auth_header):
    admin = create_user("admin-destination@acme.test", role="admin")

    destination_resp = client.post(
        "/admin/external-destinations",
        json={
            "name": "Intern Sheet",
            "destination_type": "google_sheet_range",
            "config": {
                "spreadsheet_id": "sheet_1",
                "sheet_name": "Interns",
                "a1_range": "A1:Z500",
            },
            "allowed_template_ids": ["intern_roster_by_track"],
        },
        headers=auth_header(admin),
    )
    assert destination_resp.status_code == 201
    destination_id = destination_resp.get_json()["destination"]["id"]

    req_resp = client.post(
        "/admin/agent-requests",
        json={
            "module_scope": "people",
            "template_id": "employee_directory",
            "output_type": "csv",
            "destination_type": "google_sheet_range",
            "destination_ref": str(destination_id),
        },
        headers=auth_header(admin),
    )
    assert req_resp.status_code == 400
    assert req_resp.get_json()["code"] == "VALIDATION_ERROR"


def test_presign_requires_policy_approval_and_audit_logs(client, create_user, auth_header):
    manager = create_user("manager-presign@acme.test", role="people_manager")
    approver = create_user("approver-presign@acme.test", role="admin")
    _create_people_seed(manager, approver)

    _request, artifact = _create_and_approve_request(
        client,
        auth_header,
        manager,
        approver,
        {
            "module_scope": "people",
            "template_id": "employee_directory",
            "output_type": "csv",
            "destination_type": "download",
        },
    )

    presign_needs_approval = client.post(
        f"/admin/generated-artifacts/{artifact.id}/presign",
        json={"ttl_minutes": 10},
        headers=auth_header(manager),
    )
    assert presign_needs_approval.status_code == 202
    approval_id = presign_needs_approval.get_json()["approval_request"]["id"]

    approve_resp = _approve(client, auth_header, approver, approval_id)
    assert approve_resp.status_code == 200

    presign_ok = client.post(
        f"/admin/generated-artifacts/{artifact.id}/presign",
        json={"ttl_minutes": 10},
        headers=auth_header(manager),
    )
    assert presign_ok.status_code == 200
    payload = presign_ok.get_json()
    assert payload["expires_in_seconds"] == 600
    assert payload["download_url"]

    audit = (
        AuditLog.query
        .filter_by(action="agent.artifact.presign_requested", target_id=artifact.id, actor_id=manager.id)
        .order_by(AuditLog.created_at.desc())
        .first()
    )
    assert audit is not None


def test_presign_ttl_bounds_and_download_expiry(client, create_user, auth_header):
    admin = create_user("admin-ttl@acme.test", role="admin")
    approver = create_user("approver-ttl@acme.test", role="superadmin")
    _create_people_seed(admin, approver)

    _request, artifact = _create_and_approve_request(
        client,
        auth_header,
        admin,
        approver,
        {
            "module_scope": "people",
            "template_id": "employee_directory",
            "output_type": "csv",
            "destination_type": "download",
        },
    )

    too_short = client.post(
        f"/admin/generated-artifacts/{artifact.id}/presign",
        json={"ttl_minutes": 3},
        headers=auth_header(admin),
    )
    assert too_short.status_code == 400

    too_long = client.post(
        f"/admin/generated-artifacts/{artifact.id}/presign",
        json={"ttl_minutes": 31},
        headers=auth_header(admin),
    )
    assert too_long.status_code == 400

    # Approve presign policy and then generate url.
    approval_id = client.post(
        f"/admin/generated-artifacts/{artifact.id}/presign",
        json={"ttl_minutes": 5},
        headers=auth_header(admin),
    ).get_json()["approval_request"]["id"]
    _approve(client, auth_header, approver, approval_id)

    valid = client.post(
        f"/admin/generated-artifacts/{artifact.id}/presign",
        json={"ttl_minutes": 5},
        headers=auth_header(admin),
    )
    assert valid.status_code == 200

    artifact.expires_at = datetime.utcnow() - timedelta(seconds=1)
    db.session.commit()

    expired = client.get(f"/admin/generated-artifacts/{artifact.id}/download", headers=auth_header(admin))
    assert expired.status_code == 410
    assert expired.get_json()["code"] == "LINK_EXPIRED"


def test_google_publish_flow_mocked_with_policy_and_audit(client, create_user, auth_header, monkeypatch):
    admin = create_user("admin-publish@acme.test", role="admin")
    approver = create_user("approver-publish@acme.test", role="superadmin")
    _create_people_seed(admin, approver)

    destination = ExternalDestination(
        name="People Drive Folder",
        destination_type="google_drive_folder",
        config={"folder_id": "folder_123"},
        allowed_template_ids=["employee_directory"],
        is_active=True,
        created_by_id=admin.id,
    )
    db.session.add(destination)
    db.session.commit()

    monkeypatch.setattr(
        agent_tools,
        "google_publish_to_drive",
        lambda **kwargs: {"drive_file_id": "drv_123", "name": kwargs.get("filename")},
    )

    request_record, artifact = _create_and_approve_request(
        client,
        auth_header,
        admin,
        approver,
        {
            "module_scope": "people",
            "template_id": "employee_directory",
            "output_type": "csv",
            "destination_type": "download",
        },
    )

    publish_needs_approval = client.post(
        f"/admin/generated-artifacts/{artifact.id}/publish/drive",
        json={"destination_id": destination.id},
        headers=auth_header(admin),
    )
    assert publish_needs_approval.status_code == 202
    publish_approval_id = publish_needs_approval.get_json()["approval_request"]["id"]

    approve_resp = _approve(client, auth_header, approver, publish_approval_id)
    assert approve_resp.status_code == 200

    published_audit = (
        AuditLog.query
        .filter_by(action="agent.artifact.published_external", target_id=artifact.id)
        .order_by(AuditLog.created_at.desc())
        .first()
    )
    assert published_audit is not None
    assert published_audit.details["destination_type"] == "google_drive_folder"
    assert published_audit.details["result"]["drive_file_id"] == "drv_123"
    assert request_record.id is not None
