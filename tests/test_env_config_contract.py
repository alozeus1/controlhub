from app.models import AuditLog


def test_env_config_update_contract_and_audit_redaction(client, create_user, auth_header):
    admin = create_user("admin-env@acme.test", role="admin")

    project_resp = client.post(
        "/admin/env-projects",
        json={"name": "payments", "description": "payments service"},
        headers=auth_header(admin),
    )
    assert project_resp.status_code == 201
    project_id = project_resp.get_json()["project"]["id"]

    create_resp = client.post(
        f"/admin/env-projects/{project_id}/configs",
        json={
            "environment": "prod",
            "key": "DATABASE_URL",
            "value": "postgres://old",
            "is_secret": True,
            "description": "primary db",
        },
        headers=auth_header(admin),
    )
    assert create_resp.status_code == 201
    create_payload = create_resp.get_json()
    assert create_payload["message"] == "Config created"
    config_id = create_payload["config"]["id"]

    update_resp = client.put(
        f"/admin/env-projects/{project_id}/configs/{config_id}",
        json={
            "value": "postgres://new",
            "description": "rotated",
        },
        headers=auth_header(admin),
    )
    assert update_resp.status_code == 200
    payload = update_resp.get_json()
    assert payload["message"] == "Config updated"
    assert payload["config"]["value"] == "postgres://new"
    assert payload["changes"]["value"]["from"] == "***redacted***"
    assert payload["changes"]["value"]["to"] == "***redacted***"

    audit = (
        AuditLog.query
        .filter_by(action="env_config.updated", target_id=config_id)
        .order_by(AuditLog.created_at.desc())
        .first()
    )
    assert audit is not None
    assert audit.details["changes"]["value"]["from"] == "***redacted***"
    assert audit.details["changes"]["value"]["to"] == "***redacted***"


def test_env_config_validation_and_permissions(client, create_user, auth_header):
    admin = create_user("admin-env2@acme.test", role="admin")
    viewer = create_user("viewer-env2@acme.test", role="viewer")

    project_resp = client.post(
        "/admin/env-projects",
        json={"name": "search"},
        headers=auth_header(admin),
    )
    project_id = project_resp.get_json()["project"]["id"]

    create_resp = client.post(
        f"/admin/env-projects/{project_id}/configs",
        json={"environment": "dev", "key": "FLAG", "value": "1"},
        headers=auth_header(admin),
    )
    config_id = create_resp.get_json()["config"]["id"]

    invalid_update = client.put(
        f"/admin/env-projects/{project_id}/configs/{config_id}",
        json={"unknown_field": "x"},
        headers=auth_header(admin),
    )
    assert invalid_update.status_code == 400
    assert invalid_update.get_json()["code"] == "VALIDATION_ERROR"

    forbidden = client.put(
        f"/admin/env-projects/{project_id}/configs/{config_id}",
        json={"value": "2"},
        headers=auth_header(viewer),
    )
    assert forbidden.status_code == 403
