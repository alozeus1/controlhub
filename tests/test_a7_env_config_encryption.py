"""A-7: EnvConfig secret values are encrypted at rest, masked, and reveal-gated."""
import pytest


@pytest.fixture
def project(app, create_user):
    from app.extensions import db
    from app.models import EnvProject
    admin = create_user("envadmin@x.com", role="admin")
    p = EnvProject(name="proj", created_by_id=admin.id)
    db.session.add(p)
    db.session.commit()
    return p, admin


def _make_config(db, project_id, key, value, is_secret, creator_id):
    from app.models import EnvConfig
    c = EnvConfig(project_id=project_id, environment="prod", key=key,
                  value=value, is_secret=is_secret, created_by_id=creator_id)
    db.session.add(c)
    db.session.commit()
    return c


def test_secret_value_encrypted_at_rest(app, project):
    from app.extensions import db
    from app.models import EnvConfig
    p, admin = project
    c = _make_config(db, p.id, "API_TOKEN", "super-secret-123", True, admin.id)
    cid = c.id
    db.session.expire_all()
    raw = db.session.get(EnvConfig, cid).value
    assert raw.startswith("fernet:v1:"), "secret must be stored as ciphertext"
    assert "super-secret-123" not in raw
    # ...but the decrypted view round-trips.
    assert db.session.get(EnvConfig, cid).decrypted_value == "super-secret-123"


def test_non_secret_value_stored_plaintext(app, project):
    from app.extensions import db
    from app.models import EnvConfig
    p, admin = project
    c = _make_config(db, p.id, "LOG_LEVEL", "info", False, admin.id)
    db.session.expire_all()
    assert db.session.get(EnvConfig, c.id).value == "info"


def test_to_dict_masks_secret_without_show(app, project):
    from app.extensions import db
    p, admin = project
    c = _make_config(db, p.id, "DB_PASS", "hunter2", True, admin.id)
    assert c.to_dict(show_secrets=False)["value"] == "***"
    assert c.to_dict(show_secrets=True)["value"] == "hunter2"


def test_legacy_plaintext_is_readable(app, project):
    # Rows written before encryption existed have no sentinel; they must still
    # read back as plaintext (backward compatibility) until the backfill runs.
    from app.extensions import db
    from app.models import EnvConfig
    p, admin = project
    c = EnvConfig(project_id=p.id, environment="prod", key="OLD", is_secret=True,
                  created_by_id=admin.id)
    db.session.add(c)
    db.session.commit()
    # Simulate a legacy plaintext row by writing the column directly (bypassing
    # the flush encryption via a raw UPDATE).
    db.session.execute(
        db.text("UPDATE env_config SET value='legacy-plain' WHERE id=:i"), {"i": c.id})
    db.session.commit()
    db.session.expire_all()
    assert db.session.get(EnvConfig, c.id).decrypted_value == "legacy-plain"


def test_invalid_ciphertext_returns_none(app, project):
    from app.extensions import db
    from app.models import EnvConfig
    p, admin = project
    c = _make_config(db, p.id, "BROKEN", "x", True, admin.id)
    db.session.execute(
        db.text("UPDATE env_config SET value='fernet:v1:not-a-valid-token' WHERE id=:i"),
        {"i": c.id})
    db.session.commit()
    db.session.expire_all()
    assert db.session.get(EnvConfig, c.id).decrypted_value is None


def test_reveal_requires_privileged_role(app, client, project, create_user, auth_header):
    from app.extensions import db
    p, admin = project
    _make_config(db, p.id, "SECRET_KEY", "abc123", True, admin.id)
    viewer = create_user("viewer@x.com", role="viewer")
    # A viewer sees masked values, not plaintext.
    resp = client.get(f"/admin/env-projects/{p.id}/configs", headers=auth_header(viewer))
    assert resp.status_code == 200
    items = resp.get_json()["items"]
    secret_item = next(i for i in items if i["key"] == "SECRET_KEY")
    assert secret_item["value"] == "***"
