from app.extensions import db
from app.models import FileUpload, AuditLog
import app.routes.uploads as uploads_routes


def test_upload_download_is_authorized_and_audited(client, create_user, auth_header, monkeypatch):
    admin = create_user("admin-dl@acme.test", role="admin")
    viewer = create_user("viewer-dl@acme.test", role="viewer")

    upload = FileUpload(
        user_id=admin.id,
        original_filename="report.csv",
        filename="report.csv",
        content_type="text/csv",
        size_bytes=128,
        s3_bucket="controlhub-uploads",
        s3_key="uploads/2026/03/report.csv",
    )
    db.session.add(upload)
    db.session.commit()

    monkeypatch.setattr(uploads_routes, "generate_presigned_download_url", lambda **kwargs: "https://signed.example/report")
    monkeypatch.setattr(
        uploads_routes,
        "get_storage_config",
        lambda: {"provider": "localstack", "bucket_name": "controlhub-uploads", "region": "us-east-1", "presigned_url_expiry": 120},
    )

    resp = client.get(f"/admin/uploads/{upload.id}/download", headers=auth_header(viewer))
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["download_url"] == "https://signed.example/report"
    assert payload["expires_in"] == 120

    audit = (
        AuditLog.query
        .filter_by(action="upload.downloaded", target_id=upload.id, actor_id=viewer.id)
        .order_by(AuditLog.created_at.desc())
        .first()
    )
    assert audit is not None
    assert audit.ip_address is not None


def test_audit_export_download_returns_file_and_audits(client, create_user, auth_header):
    admin = create_user("admin-export@acme.test", role="admin")

    # Seed at least one audit event for export output
    log = AuditLog(
        actor_id=admin.id,
        actor_email=admin.email,
        action="user.login",
        target_type="user",
        target_id=admin.id,
        target_label=admin.email,
        details={"seed": True},
    )
    db.session.add(log)
    db.session.commit()

    create_job = client.post(
        "/admin/audit-exports",
        json={"name": "Compliance Export", "format": "csv", "destination_type": "download"},
        headers=auth_header(admin),
    )
    assert create_job.status_code == 201
    job_id = create_job.get_json()["job"]["id"]

    run = client.post(f"/admin/audit-exports/{job_id}/run", headers=auth_header(admin))
    assert run.status_code == 200
    assert "text/csv" in run.headers["Content-Type"]
    assert "attachment; filename=" in run.headers["Content-Disposition"]
    assert "action" in run.get_data(as_text=True)

    exec_audit = (
        AuditLog.query
        .filter_by(action="audit_export.executed", actor_id=admin.id, target_id=job_id)
        .order_by(AuditLog.created_at.desc())
        .first()
    )
    assert exec_audit is not None

