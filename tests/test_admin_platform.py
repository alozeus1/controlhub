"""
Tests for the admin platform: roles & permissions, org settings, MFA, SSO
config, global search, and audit export — including permission gating.
"""
import pyotp
import pytest


@pytest.fixture
def admin(create_user):
    return create_user("admin@x.com", role="admin")


@pytest.fixture
def viewer(create_user):
    return create_user("viewer@x.com", role="viewer")


# ─── Roles & permissions ──────────────────────────────────────────────────────

def test_roles_gated(client, admin, viewer, auth_header):
    assert client.get("/admin/roles", headers=auth_header(admin)).status_code == 200
    r = client.get("/admin/roles", headers=auth_header(viewer))
    assert r.status_code == 403
    assert r.get_json()["code"] == "INSUFFICIENT_PERMISSIONS"


def test_roles_seeded_and_catalog(client, admin, auth_header):
    roles = client.get("/admin/roles", headers=auth_header(admin)).get_json()["roles"]
    names = {r["name"] for r in roles}
    assert {"superadmin", "admin", "viewer", "user"}.issubset(names)
    cat = client.get("/admin/permissions/catalog", headers=auth_header(admin)).get_json()
    assert any(p["key"] == "manage_users" for p in cat["permissions"])


def test_create_update_delete_custom_role(client, admin, auth_header):
    created = client.post("/admin/roles", headers=auth_header(admin),
                          json={"name": "ops_x", "label": "Ops X", "permissions": ["global_search"]})
    assert created.status_code == 201
    rid = created.get_json()["id"]

    upd = client.patch(f"/admin/roles/{rid}", headers=auth_header(admin),
                       json={"permissions": ["global_search", "view_audit_logs"]})
    assert set(upd.get_json()["permissions"]) == {"global_search", "view_audit_logs"}

    assert client.delete(f"/admin/roles/{rid}", headers=auth_header(admin)).status_code == 200


def test_superadmin_role_immutable(client, admin, auth_header):
    roles = client.get("/admin/roles", headers=auth_header(admin)).get_json()["roles"]
    sa = next(r for r in roles if r["name"] == "superadmin")
    r = client.patch(f"/admin/roles/{sa['id']}", headers=auth_header(admin), json={"permissions": []})
    assert r.status_code == 403


def test_system_role_not_deletable(client, admin, auth_header):
    roles = client.get("/admin/roles", headers=auth_header(admin)).get_json()["roles"]
    viewer_role = next(r for r in roles if r["name"] == "viewer")
    assert client.delete(f"/admin/roles/{viewer_role['id']}", headers=auth_header(admin)).status_code == 403


# ─── Organization settings ────────────────────────────────────────────────────

def test_org_settings_read_any_write_admin(client, admin, viewer, auth_header):
    assert client.get("/admin/org-settings", headers=auth_header(viewer)).status_code == 200
    assert client.put("/admin/org-settings", headers=auth_header(admin),
                      json={"org_name": "WF", "allowed_signup_domains": "webforx.tech, x.com"}).status_code == 200
    got = client.get("/admin/org-settings", headers=auth_header(admin)).get_json()
    assert got["org_name"] == "WF"
    assert "webforx.tech" in got["allowed_signup_domains"]
    assert client.put("/admin/org-settings", headers=auth_header(viewer), json={"org_name": "x"}).status_code == 403


# ─── MFA ──────────────────────────────────────────────────────────────────────

def _enroll_mfa(client, user, auth_header):
    setup = client.post("/auth/mfa/setup", headers=auth_header(user)).get_json()
    secret = setup["secret"]
    code = pyotp.TOTP(secret).now()
    res = client.post("/auth/mfa/verify", headers=auth_header(user), json={"code": code})
    return secret, res


def test_mfa_enroll_and_backup_codes(client, admin, auth_header):
    secret, res = _enroll_mfa(client, admin, auth_header)
    assert res.status_code == 200
    body = res.get_json()
    assert body["enabled"] is True
    assert len(body["backup_codes"]) == 10
    status = client.get("/auth/mfa/status", headers=auth_header(admin)).get_json()
    assert status["enabled"] is True


def test_mfa_verify_rejects_bad_code(client, admin, auth_header):
    client.post("/auth/mfa/setup", headers=auth_header(admin))
    r = client.post("/auth/mfa/verify", headers=auth_header(admin), json={"code": "000000"})
    assert r.status_code == 400


def test_login_requires_second_factor(client, create_user, auth_header):
    user = create_user("mfa@x.com", role="admin", password="Pass1234!")  # secret-scan:allow
    _enroll_mfa(client, user, auth_header)
    # Log in with password → expect a challenge, not tokens.
    login = client.post("/auth/login", json={"email": "mfa@x.com", "password": "Pass1234!"})
    data = login.get_json()
    assert data.get("mfa_required") is True
    assert "access_token" not in data
    assert data.get("mfa_token")


def test_mfa_login_verify_completes(client, create_user, auth_header):
    user = create_user("mfa2@x.com", role="admin", password="Pass1234!")  # secret-scan:allow
    secret, _ = _enroll_mfa(client, user, auth_header)
    login = client.post("/auth/login", json={"email": "mfa2@x.com", "password": "Pass1234!"}).get_json()
    code = pyotp.TOTP(secret).now()
    done = client.post("/auth/mfa/login-verify",
                       json={"mfa_token": login["mfa_token"], "code": code})
    assert done.status_code == 200
    assert done.get_json().get("access_token")


def test_mfa_login_verify_rejects_bad_code(client, create_user, auth_header):
    user = create_user("mfa3@x.com", role="admin", password="Pass1234!")  # secret-scan:allow
    _enroll_mfa(client, user, auth_header)
    login = client.post("/auth/login", json={"email": "mfa3@x.com", "password": "Pass1234!"}).get_json()
    bad = client.post("/auth/mfa/login-verify", json={"mfa_token": login["mfa_token"], "code": "000000"})
    assert bad.status_code == 401


def test_mfa_lockout_after_repeated_failures(client, create_user, auth_header):
    user = create_user("mfa4@x.com", role="admin", password="Pass1234!")  # secret-scan:allow
    _enroll_mfa(client, user, auth_header)
    login = client.post("/auth/login", json={"email": "mfa4@x.com", "password": "Pass1234!"}).get_json()
    tok = login["mfa_token"]
    statuses = [client.post("/auth/mfa/login-verify",
                            json={"mfa_token": tok, "code": "000000"}).status_code for _ in range(6)]
    # After MAX_FAILED (5) bad codes the account is temporarily locked (429).
    assert 429 in statuses


# ─── SSO config ───────────────────────────────────────────────────────────────

def test_sso_config_gated_and_status_public(client, admin, viewer, auth_header):
    assert client.get("/admin/sso/config", headers=auth_header(admin)).status_code == 200
    assert client.get("/admin/sso/config", headers=auth_header(viewer)).status_code == 403
    # Public status endpoint needs no auth.
    st = client.get("/auth/sso/status")
    assert st.status_code == 200
    assert st.get_json()["enabled"] is False  # nothing configured


def test_sso_login_disabled_returns_400(client):
    assert client.get("/auth/sso/login").status_code == 400


def test_sso_config_update_encrypts_secret(client, admin, auth_header):
    r = client.put("/admin/sso/config", headers=auth_header(admin), json={
        "enabled": True, "discovery_url": "https://idp/.well-known/openid-configuration",
        "client_id": "abc", "client_secret": "shhh",
        "claim_role_map": {"admins": "admin"}, "allowed_domains": "webforx.tech",
    })
    assert r.status_code == 200
    body = r.get_json()
    assert body["has_client_secret"] is True
    assert "client_secret" not in body  # never returned in the clear


# ─── Global search + audit export ─────────────────────────────────────────────

def test_search_min_length_and_scoping(client, admin, viewer, create_user, auth_header):
    create_user("findme@x.com", role="user")
    assert client.get("/admin/search?q=a", headers=auth_header(admin)).get_json()["groups"] == []
    admin_res = client.get("/admin/search?q=findme", headers=auth_header(admin)).get_json()
    assert any(g["category"] == "Users" for g in admin_res["groups"])
    # Viewer lacks manage_users → no Users group leaked.
    viewer_res = client.get("/admin/search?q=findme", headers=auth_header(viewer)).get_json()
    assert not any(g["category"] == "Users" for g in viewer_res["groups"])


def test_audit_export_csv(client, viewer, auth_header):
    r = client.get("/admin/audit-logs/export", headers=auth_header(viewer))
    assert r.status_code == 200
    assert "text/csv" in r.headers["Content-Type"]
    assert r.data.decode().splitlines()[0].startswith("timestamp,actor_email,action")
