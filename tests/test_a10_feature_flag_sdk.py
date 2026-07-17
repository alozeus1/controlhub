"""A-10: feature-flag SDK endpoint requires a scoped, revocable SDK key."""
import pytest


@pytest.fixture
def seeded(app, create_user):
    from app.extensions import db
    from app.models import FeatureFlag
    admin = create_user("ffadmin@x.com", role="admin")
    db.session.add(FeatureFlag(project="webapp", name="New UI", key="new_ui",
                               is_enabled=True, created_by_id=admin.id))
    db.session.add(FeatureFlag(project="other", name="Secret", key="secret_thing",
                               is_enabled=True, created_by_id=admin.id))
    db.session.commit()
    return admin


def _make_key(db, project, creator_id, active=True):
    from app.models import FeatureFlagSdkKey
    from datetime import datetime
    plaintext, key_hash, prefix = FeatureFlagSdkKey.generate_key()
    k = FeatureFlagSdkKey(project=project, key_hash=key_hash, key_prefix=prefix,
                          is_active=active, created_by_id=creator_id,
                          revoked_at=None if active else datetime.utcnow())
    db.session.add(k)
    db.session.commit()
    return plaintext, k


def test_sdk_denies_without_key(client, seeded):
    resp = client.get("/admin/feature-flags/sdk/webapp")
    assert resp.status_code == 401


def test_sdk_denies_invalid_key(client, seeded):
    resp = client.get("/admin/feature-flags/sdk/webapp", headers={"X-SDK-Key": "chsdk_bogus"})
    assert resp.status_code == 403


def test_sdk_denies_wrong_project(app, client, seeded):
    from app.extensions import db
    plaintext, _ = _make_key(db, "webapp", seeded.id)
    # Key is scoped to 'webapp'; using it against 'other' must fail (no cross-project enum).
    resp = client.get("/admin/feature-flags/sdk/other", headers={"X-SDK-Key": plaintext})
    assert resp.status_code == 403


def test_sdk_denies_revoked_key(app, client, seeded):
    from app.extensions import db
    plaintext, _ = _make_key(db, "webapp", seeded.id, active=False)
    resp = client.get("/admin/feature-flags/sdk/webapp", headers={"X-SDK-Key": plaintext})
    assert resp.status_code == 403


def test_sdk_allows_valid_scoped_key(app, client, seeded):
    from app.extensions import db
    plaintext, _ = _make_key(db, "webapp", seeded.id)
    resp = client.get("/admin/feature-flags/sdk/webapp", headers={"X-SDK-Key": plaintext})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body.get("new_ui") is True
    assert "secret_thing" not in body  # only this project's flags


def test_admin_can_create_and_revoke_key(app, client, seeded, auth_header):
    created = client.post("/admin/feature-flags/sdk-keys",
                          headers=auth_header(seeded), json={"project": "webapp"})
    assert created.status_code == 201
    body = created.get_json()
    plaintext = body["key"]
    assert plaintext.startswith("chsdk_")
    # Works immediately...
    assert client.get("/admin/feature-flags/sdk/webapp",
                      headers={"X-SDK-Key": plaintext}).status_code == 200
    # ...then revoke and it stops working.
    kid = body["id"]
    assert client.delete(f"/admin/feature-flags/sdk-keys/{kid}",
                         headers=auth_header(seeded)).status_code == 200
    assert client.get("/admin/feature-flags/sdk/webapp",
                      headers={"X-SDK-Key": plaintext}).status_code == 403


def test_key_management_requires_admin(client, seeded, create_user, auth_header):
    viewer = create_user("ffviewer@x.com", role="viewer")
    assert client.get("/admin/feature-flags/sdk-keys",
                      headers=auth_header(viewer)).status_code in (401, 403)
