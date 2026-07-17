"""
P0-1 regression: service-account API-key scope enforcement (deny-by-default).

Proves API keys:
  * are authorized only by scope on scoped email endpoints,
  * are denied on human-only endpoints (secrets, users, roles, org settings,
    superadmin) regardless of scope, including wildcards,
  * reject expired / revoked / disabled / malformed keys,
  * attribute audit records to the service account,
  * do not change human-user behavior.
"""
from datetime import datetime, timedelta

import pytest


@pytest.fixture
def email_env(monkeypatch):
    monkeypatch.setenv("FEATURE_EMAIL_CAMPAIGNS", "true")
    monkeypatch.setenv("FEATURE_SERVICE_ACCOUNTS", "true")
    monkeypatch.setenv("SES_SENDING_ENABLED", "false")
    monkeypatch.setenv("CAMPAIGN_SEND_SYNC", "true")


@pytest.fixture
def admin(create_user):
    return create_user("admin@x.com", role="admin")


def _make_key(app, admin, scopes, expires_days=None, revoked=False, sa_active=True):
    from app.extensions import db
    from app.services.service_accounts import ServiceAccountService, ApiKeyService
    with app.app_context():
        sa = ServiceAccountService.create_account(name=f"svc-{scopes}", description="t", actor=admin)
        expires = datetime.utcnow() + timedelta(days=expires_days) if expires_days is not None else None
        key, plaintext = ApiKeyService.create_key(sa, "k", admin, scopes=scopes, expires_at=expires)
        if revoked:
            key.revoked_at = datetime.utcnow()
        if not sa_active:
            sa.is_active = False
        db.session.commit()
        return plaintext


def H(key):
    return {"X-API-Key": key}


# ─── scope satisfaction unit ──────────────────────────────────────────────────

def test_scope_matching_unit():
    from app.api_scopes import scope_satisfies
    assert scope_satisfies(["email:read"], "email:read")
    assert not scope_satisfies(["email:read"], "email:write")
    assert scope_satisfies(["email:*"], "email:send")          # namespace wildcard
    assert not scope_satisfies(["*"], "email:send")            # bare * grants nothing
    assert not scope_satisfies(["bogus:thing"], "email:read")  # unknown scope
    assert not scope_satisfies([], "email:read")               # no scopes
    assert not scope_satisfies(["email:read"], "email:unknown")  # unregistered requirement


# ─── in-scope allowed ─────────────────────────────────────────────────────────

def test_read_scope_allows_get(app, client, email_env, admin):
    key = _make_key(app, admin, ["email:read"])
    assert client.get("/admin/email/subscribers", headers=H(key)).status_code == 200


def test_write_scope_allows_create(app, client, email_env, admin):
    key = _make_key(app, admin, ["email:write"])
    r = client.post("/admin/email/lists", headers=H(key), json={"name": "Beta"})
    assert r.status_code == 201


def test_send_scope_allows_transactional(app, client, email_env, admin):
    key = _make_key(app, admin, ["email:send"])
    r = client.post("/admin/email/transactional", headers=H(key),
                    json={"email": "a@b.com", "subject": "Hi", "html": "<p>hi</p>"})
    assert r.status_code in (200, 202)


def test_wildcard_scope_allows_all(app, client, email_env, admin):
    key = _make_key(app, admin, ["email:*"])
    assert client.get("/admin/email/lists", headers=H(key)).status_code == 200
    assert client.post("/admin/email/lists", headers=H(key), json={"name": "W"}).status_code == 201


# ─── out-of-scope / missing / unknown denied ──────────────────────────────────

def test_read_key_denied_on_write(app, client, email_env, admin):
    key = _make_key(app, admin, ["email:read"])
    r = client.post("/admin/email/lists", headers=H(key), json={"name": "X"})
    assert r.status_code == 403
    assert r.get_json()["code"] == "INSUFFICIENT_SCOPE"


def test_no_scopes_denied(app, client, email_env, admin):
    key = _make_key(app, admin, [])
    assert client.get("/admin/email/subscribers", headers=H(key)).status_code == 403


def test_unknown_scope_denied(app, client, email_env, admin):
    key = _make_key(app, admin, ["totally:bogus"])
    assert client.get("/admin/email/subscribers", headers=H(key)).status_code == 403


def test_bare_wildcard_grants_nothing(app, client, email_env, admin):
    key = _make_key(app, admin, ["*"])
    assert client.get("/admin/email/subscribers", headers=H(key)).status_code == 403


# ─── invalid keys ─────────────────────────────────────────────────────────────

def test_expired_key_rejected(app, client, email_env, admin):
    key = _make_key(app, admin, ["email:read"], expires_days=-1)
    assert client.get("/admin/email/subscribers", headers=H(key)).status_code == 401


def test_revoked_key_rejected(app, client, email_env, admin):
    key = _make_key(app, admin, ["email:read"], revoked=True)
    assert client.get("/admin/email/subscribers", headers=H(key)).status_code == 401


def test_disabled_service_account_rejected(app, client, email_env, admin):
    key = _make_key(app, admin, ["email:read"], sa_active=False)
    assert client.get("/admin/email/subscribers", headers=H(key)).status_code in (401, 403)


def test_malformed_key_rejected(app, client, email_env, admin):
    assert client.get("/admin/email/subscribers", headers=H("not-a-real-key")).status_code == 401


# ─── human-only endpoint denial (even with a broad wildcard key) ───────────────

@pytest.mark.parametrize("method,path", [
    ("get", "/admin/secrets"),
    ("get", "/admin/users"),
    ("get", "/admin/roles"),
    ("put", "/admin/org-settings"),
])
def test_api_key_denied_on_human_only_endpoints(app, client, email_env, admin, method, path):
    key = _make_key(app, admin, ["email:*", "*"])  # deliberately over-broad
    resp = getattr(client, method)(path, headers=H(key), json={})
    assert resp.status_code == 403
    assert resp.get_json()["code"] == "API_KEY_NOT_PERMITTED"


def test_api_key_cannot_reach_superadmin_route(app, client, email_env, admin):
    # /admin/users/<id> role change etc. are require_role("admin"/"superadmin")
    key = _make_key(app, admin, ["email:*"])
    assert client.get("/admin/audit-logs", headers=H(key)).status_code == 403


# ─── audit attribution ────────────────────────────────────────────────────────

def test_denied_scope_is_audited_to_service_account(app, client, email_env, admin):
    key = _make_key(app, admin, ["email:read"])
    client.post("/admin/email/lists", headers=H(key), json={"name": "X"})  # out of scope
    from app.models import AuditLog
    with app.app_context():
        row = AuditLog.query.filter_by(action="api_key.denied_scope").first()
        assert row is not None
        assert row.target_label == "email:write"


def test_service_account_write_attributed_in_audit(app, client, email_env, admin):
    key = _make_key(app, admin, ["email:write"])
    client.post("/admin/email/lists", headers=H(key), json={"name": "Attrib"})
    from app.models import AuditLog
    with app.app_context():
        row = AuditLog.query.filter_by(action="email.list.created").order_by(AuditLog.id.desc()).first()
        assert row is not None
        assert row.actor_email and row.actor_email.startswith("service-account:")


# ─── human behavior unchanged ─────────────────────────────────────────────────

def test_human_admin_unchanged(client, email_env, admin, auth_header):
    assert client.get("/admin/email/subscribers", headers=auth_header(admin)).status_code == 200
    assert client.post("/admin/email/lists", headers=auth_header(admin), json={"name": "H"}).status_code == 201


def test_human_viewer_read_only(client, email_env, create_user, auth_header):
    viewer = create_user("v@x.com", role="viewer")
    assert client.get("/admin/email/subscribers", headers=auth_header(viewer)).status_code == 200
    r = client.post("/admin/email/lists", headers=auth_header(viewer), json={"name": "V"})
    assert r.status_code == 403
    assert r.get_json()["code"] == "INSUFFICIENT_PERMISSIONS"
