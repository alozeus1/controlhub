from app.models import Secret, Policy
from app.extensions import db


def test_secret_create_masks_value_and_encrypts(client, create_user, auth_header):
    admin = create_user("admin@acme.test", role="admin")
    viewer = create_user("viewer@acme.test", role="viewer")

    create_resp = client.post(
        "/admin/secrets",
        json={
            "name": "DB_PASSWORD",
            "value": "super-secret-value",
            "project": "controlhub",
            "environment": "prod",
        },
        headers=auth_header(admin),
    )
    assert create_resp.status_code == 201
    payload = create_resp.get_json()
    assert payload["secret"]["name"] == "DB_PASSWORD"
    assert "value" not in payload["secret"]

    secret_id = payload["secret"]["id"]
    secret = Secret.query.get(secret_id)
    assert secret.value_encrypted.startswith("fernet:v1:")
    assert "super-secret-value" not in secret.value_encrypted

    list_resp = client.get("/admin/secrets", headers=auth_header(viewer))
    assert list_resp.status_code == 200
    assert "value" not in list_resp.get_json()["items"][0]

    detail_resp = client.get(f"/admin/secrets/{secret_id}", headers=auth_header(viewer))
    assert detail_resp.status_code == 200
    assert "value" not in detail_resp.get_json()

    blocked_reveal = client.post(f"/admin/secrets/{secret_id}/reveal", headers=auth_header(viewer))
    assert blocked_reveal.status_code == 403

    reveal_resp = client.post(f"/admin/secrets/{secret_id}/reveal", headers=auth_header(admin))
    assert reveal_resp.status_code == 200
    assert reveal_resp.get_json()["value"] == "super-secret-value"


def test_secret_reveal_can_be_policy_gated(client, create_user, auth_header):
    admin = create_user("admin2@acme.test", role="admin")
    approver = create_user("approver@acme.test", role="superadmin")

    secret_resp = client.post(
        "/admin/secrets",
        json={"name": "API_TOKEN", "value": "token-123"},
        headers=auth_header(admin),
    )
    secret_id = secret_resp.get_json()["secret"]["id"]

    policy = Policy(
        name="Approve secret reveal",
        action="secret.reveal",
        requires_approval=True,
        approvals_required=1,
        approver_role="admin",
        is_active=True,
        created_by=approver.id,
    )
    db.session.add(policy)
    db.session.commit()

    pending = client.post(f"/admin/secrets/{secret_id}/reveal", headers=auth_header(admin))
    assert pending.status_code == 202
    pending_payload = pending.get_json()
    assert pending_payload["code"] == "APPROVAL_REQUIRED"
    approval_id = pending_payload["approval_request"]["id"]

    approve = client.post(f"/admin/approvals/{approval_id}/approve", headers=auth_header(approver))
    assert approve.status_code == 200

    reveal = client.post(
        f"/admin/secrets/{secret_id}/reveal?approval_request_id={approval_id}",
        headers=auth_header(admin),
    )
    assert reveal.status_code == 200
    assert reveal.get_json()["value"] == "token-123"

