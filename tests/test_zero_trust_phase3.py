"""
Zero-trust Phase 3: just-in-time privilege elevation.

The property under test throughout: holding a valid admin session is not enough.
An attacker with a stolen token must also defeat a live second factor, and even
then only from the session that elevated.
"""
from datetime import datetime, timedelta

import pytest

from app.extensions import db
from app.models import AuditLog, PrivilegeGrant
from app.services import privilege


PASSWORD = "correct-horse-battery"


@pytest.fixture
def jit(app):
    """Elevation enabled for manage_secrets and manage_roles."""
    app.config["JIT_ELEVATED_PERMISSIONS"] = "manage_secrets,manage_roles"
    app.config["JIT_DUAL_APPROVAL_PERMISSIONS"] = ""
    app.config["JIT_ELEVATION_TTL_MINUTES"] = 15
    app.config["JIT_REQUIRE_MFA"] = False
    return app


@pytest.fixture
def admin(create_user):
    return create_user("jit-admin@x.com", role="admin", password=PASSWORD)  # secret-scan:allow - test fixture / parameter name, not a credential


def _login(client, email="jit-admin@x.com", password=PASSWORD):  # secret-scan:allow - test fixture / parameter name, not a credential
    resp = client.post("/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()


def _bearer(tokens):
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def _elevate(client, headers, key="manage_secrets", reason="rotating the prod db password"):
    return client.post("/admin/elevation/request", headers=headers,
                       json={"permission_key": key, "reason": reason, "password": PASSWORD})


# ─── Feature is off by default ────────────────────────────────────────────────

def test_disabled_by_default_changes_nothing(app, client, admin, auth_header):
    """An existing deployment must be unaffected until it opts in."""
    assert app.config.get("JIT_ELEVATED_PERMISSIONS", "") == ""
    assert privilege.elevation_required("manage_secrets") is False

    resp = client.get("/admin/roles", headers=auth_header(admin))
    assert resp.status_code == 200


# ─── Gating ───────────────────────────────────────────────────────────────────

def test_gated_endpoint_refuses_without_elevation(client, jit, admin, auth_header):
    """A full admin session alone is not sufficient once the permission is gated."""
    resp = client.get("/admin/roles", headers=auth_header(admin))
    assert resp.status_code == 403
    body = resp.get_json()
    assert body["code"] == "ELEVATION_REQUIRED"
    assert body["permission_key"] == "manage_roles"


def test_ungated_permission_still_works(client, jit, admin, auth_header):
    """Only listed keys are gated; everything else is untouched."""
    assert client.get("/admin/org-settings", headers=auth_header(admin)).status_code in (200, 404)


def test_elevation_unlocks_the_endpoint(client, jit, admin):
    tokens = _login(client)
    headers = _bearer(tokens)

    assert client.get("/admin/roles", headers=headers).status_code == 403

    resp = _elevate(client, headers, key="manage_roles", reason="auditing role definitions")
    assert resp.status_code == 201, resp.get_json()
    assert resp.get_json()["permission_key"] == "manage_roles"

    assert client.get("/admin/roles", headers=headers).status_code == 200


# ─── Requesting elevation ─────────────────────────────────────────────────────

def test_reason_is_required(client, jit, admin):
    headers = _bearer(_login(client))
    resp = client.post("/admin/elevation/request", headers=headers,
                       json={"permission_key": "manage_secrets", "reason": "x",
                             "password": PASSWORD})
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "REASON_REQUIRED"


def test_reauth_is_required(client, jit, admin):
    """The session alone must not be enough — that is the stolen artifact."""
    headers = _bearer(_login(client))
    resp = client.post("/admin/elevation/request", headers=headers,
                       json={"permission_key": "manage_secrets",
                             "reason": "need to read a credential"})
    assert resp.status_code == 401
    assert resp.get_json()["code"] == "PASSWORD_REQUIRED"


def test_wrong_password_is_rejected_and_audited(client, jit, admin):
    headers = _bearer(_login(client))
    resp = client.post("/admin/elevation/request", headers=headers,
                       json={"permission_key": "manage_secrets",
                             "reason": "need to read a credential",
                             "password": "wrong-password"})
    assert resp.status_code == 401
    assert resp.get_json()["code"] == "INVALID_PASSWORD"
    assert AuditLog.query.filter_by(action="privilege.reauth_failed").count() == 1


def test_elevation_requires_eligibility(client, jit, create_user):
    """Elevation activates a permission the role already implies — it never grants one."""
    create_user("viewer@x.com", role="viewer", password=PASSWORD)  # secret-scan:allow - test fixture / parameter name, not a credential
    headers = _bearer(_login(client, "viewer@x.com"))

    resp = client.post("/admin/elevation/request", headers=headers,
                       json={"permission_key": "manage_secrets",
                             "reason": "trying to read secrets", "password": PASSWORD})
    assert resp.status_code == 403
    assert resp.get_json()["code"] == "INSUFFICIENT_PERMISSIONS"
    assert AuditLog.query.filter_by(action="privilege.denied").count() == 1


def test_cannot_elevate_an_ungated_permission(client, jit, admin):
    headers = _bearer(_login(client))
    resp = client.post("/admin/elevation/request", headers=headers,
                       json={"permission_key": "view_dashboard",
                             "reason": "not a gated permission", "password": PASSWORD})
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "ELEVATION_NOT_APPLICABLE"


def test_mfa_code_required_when_enrolled(client, jit, admin, monkeypatch):
    """With MFA enrolled the password fallback must not be accepted."""
    import app.routes.mfa as mfa_module

    # Log in first, then simulate enrollment — patching earlier would change the
    # login path rather than the elevation path under test.
    headers = _bearer(_login(client))
    monkeypatch.setattr(mfa_module, "mfa_enabled_for", lambda _u: True)

    resp = client.post("/admin/elevation/request", headers=headers,
                       json={"permission_key": "manage_secrets",
                             "reason": "reading a production credential",
                             "password": PASSWORD})
    assert resp.status_code == 401
    assert resp.get_json()["code"] == "MFA_CODE_REQUIRED"


def test_mfa_failure_fails_closed(client, jit, admin, monkeypatch):
    """An MFA fault must not silently downgrade elevation to password-only."""
    import app.routes.mfa as mfa_module

    def _boom(_u):
        raise RuntimeError("mfa backend down")

    headers = _bearer(_login(client))
    monkeypatch.setattr(mfa_module, "mfa_enabled_for", _boom)

    resp = client.post("/admin/elevation/request", headers=headers,
                       json={"permission_key": "manage_secrets",
                             "reason": "reading a production credential",
                             "password": PASSWORD})
    assert resp.status_code == 503
    assert resp.get_json()["code"] == "MFA_UNAVAILABLE"


# ─── Expiry, binding, revocation ──────────────────────────────────────────────

def test_grant_expires(client, jit, admin):
    headers = _bearer(_login(client))
    assert _elevate(client, headers, key="manage_roles",
                    reason="auditing role definitions").status_code == 201
    assert client.get("/admin/roles", headers=headers).status_code == 200

    grant = PrivilegeGrant.query.filter_by(user_id=admin.id).first()
    grant.expires_at = datetime.utcnow() - timedelta(seconds=1)
    db.session.commit()

    assert client.get("/admin/roles", headers=headers).status_code == 403


def test_grant_is_bound_to_the_session_that_requested_it(client, jit, admin):
    """
    The decisive control: an attacker holding a *different* stolen token for the
    same user must not inherit an elevation the real operator just activated.
    """
    operator = _bearer(_login(client))      # session A — the real operator
    attacker = _bearer(_login(client))      # session B — a separate stolen session

    assert _elevate(client, operator, key="manage_roles",
                    reason="auditing role definitions").status_code == 201

    assert client.get("/admin/roles", headers=operator).status_code == 200
    assert client.get("/admin/roles", headers=attacker).status_code == 403


def test_user_can_revoke_their_own_grant_early(client, jit, admin):
    headers = _bearer(_login(client))
    grant_id = _elevate(client, headers, key="manage_roles",
                        reason="auditing role definitions").get_json()["id"]

    assert client.get("/admin/roles", headers=headers).status_code == 200
    assert client.post(f"/admin/elevation/{grant_id}/revoke",
                       headers=headers).status_code == 200
    assert client.get("/admin/roles", headers=headers).status_code == 403


def test_role_change_revokes_active_grants(client, jit, admin, create_user, auth_header):
    """A demoted admin must not keep an elevation they are no longer eligible for."""
    superadmin = create_user("super@x.com", role="superadmin")
    headers = _bearer(_login(client))
    assert _elevate(client, headers, key="manage_roles",
                    reason="auditing role definitions").status_code == 201
    assert client.get("/admin/roles", headers=headers).status_code == 200

    resp = client.patch(f"/admin/users/{admin.id}",
                        headers=auth_header(superadmin), json={"role": "viewer"})
    assert resp.status_code == 200

    grant = PrivilegeGrant.query.filter_by(user_id=admin.id).first()
    assert grant.revoked_at is not None
    assert grant.revoked_reason == "role_or_status_change"


# ─── Auditing ─────────────────────────────────────────────────────────────────

def test_elevation_is_audited_with_its_reason(client, jit, admin):
    headers = _bearer(_login(client))
    _elevate(client, headers, key="manage_roles", reason="auditing role definitions")

    entry = AuditLog.query.filter_by(action="privilege.elevated").first()
    assert entry is not None
    assert entry.details["reason"] == "auditing role definitions"
    assert entry.target_label == "manage_roles"


def test_use_of_a_grant_is_counted(client, jit, admin):
    headers = _bearer(_login(client))
    _elevate(client, headers, key="manage_roles", reason="auditing role definitions")

    client.get("/admin/roles", headers=headers)
    client.get("/admin/roles", headers=headers)

    db.session.expire_all()
    grant = PrivilegeGrant.query.filter_by(user_id=admin.id).first()
    assert grant.used_count == 2
    assert grant.last_used_at is not None


# ─── Two-person rule ──────────────────────────────────────────────────────────

@pytest.fixture
def dual(jit):
    jit.config["JIT_DUAL_APPROVAL_PERMISSIONS"] = "manage_roles"
    return jit


def test_dual_approval_grant_is_inert_until_approved(client, dual, admin):
    headers = _bearer(_login(client))
    resp = _elevate(client, headers, key="manage_roles", reason="auditing role definitions")
    assert resp.status_code == 202
    assert resp.get_json()["active"] is False

    # Must not be usable in the window before approval.
    assert client.get("/admin/roles", headers=headers).status_code == 403


def test_second_approver_activates_the_grant(client, dual, admin, create_user, auth_header):
    peer = create_user("peer-admin@x.com", role="admin")
    headers = _bearer(_login(client))
    grant_id = _elevate(client, headers, key="manage_roles",
                        reason="auditing role definitions").get_json()["id"]

    assert client.post(f"/admin/elevation/{grant_id}/approve",
                       headers=auth_header(peer)).status_code == 200
    assert client.get("/admin/roles", headers=headers).status_code == 200


def test_self_approval_is_forbidden(client, dual, admin):
    """A two-person rule one person can satisfy is not a two-person rule."""
    headers = _bearer(_login(client))
    grant_id = _elevate(client, headers, key="manage_roles",
                        reason="auditing role definitions").get_json()["id"]

    resp = client.post(f"/admin/elevation/{grant_id}/approve", headers=headers)
    assert resp.status_code == 403
    assert resp.get_json()["code"] == "SELF_APPROVAL_FORBIDDEN"
    assert client.get("/admin/roles", headers=headers).status_code == 403


def test_approver_must_hold_the_permission(client, dual, admin, create_user, auth_header):
    viewer = create_user("weak-approver@x.com", role="viewer")
    headers = _bearer(_login(client))
    grant_id = _elevate(client, headers, key="manage_roles",
                        reason="auditing role definitions").get_json()["id"]

    resp = client.post(f"/admin/elevation/{grant_id}/approve", headers=auth_header(viewer))
    assert resp.status_code == 403
    assert resp.get_json()["code"] == "INSUFFICIENT_PERMISSIONS"


# ─── Discovery endpoint ───────────────────────────────────────────────────────

def test_config_endpoint_reports_what_is_gated(client, jit, admin, auth_header):
    body = client.get("/admin/elevation/config", headers=auth_header(admin)).get_json()
    assert body["enabled"] is True
    assert set(body["elevated_permissions"]) == {"manage_secrets", "manage_roles"}
    assert body["ttl_minutes"] == 15
    assert "manage_roles" in body["eligible"]


def test_config_endpoint_hides_ineligible_permissions(client, jit, create_user, auth_header):
    viewer = create_user("plain-viewer@x.com", role="viewer")
    body = client.get("/admin/elevation/config", headers=auth_header(viewer)).get_json()
    assert body["eligible"] == []


# ─── Secret vault gating ──────────────────────────────────────────────────────

def _secret_payload(name="db-password"):
    return {"name": name, "value": "s3cr3t-value", "project": "core", "environment": "prod"}


def test_all_secret_mutations_and_reveal_are_gated(client, jit, admin, auth_header):
    """
    Reveal leaks the secret; create/update/delete tamper with it. All four need
    elevation — gating only the read path would leave destruction wide open.
    """
    headers = auth_header(admin)
    created = client.post("/admin/secrets", headers=headers, json=_secret_payload())
    assert created.status_code == 403
    assert created.get_json()["code"] == "ELEVATION_REQUIRED"

    # Seed one directly so the mutating paths have a target.
    from app.models import Secret
    from app.services.secret_crypto import encrypt_secret
    secret = Secret(name="seeded", value_encrypted=encrypt_secret("v", purpose="vault_secret"),
                    created_by_id=admin.id)
    db.session.add(secret)
    db.session.commit()

    for method, path, payload in [
        ("post", f"/admin/secrets/{secret.id}/reveal", None),
        ("put", f"/admin/secrets/{secret.id}", {"description": "changed"}),
        ("delete", f"/admin/secrets/{secret.id}", None),
    ]:
        resp = getattr(client, method)(path, headers=headers, json=payload)
        assert resp.status_code == 403, f"{method} {path} was not gated"
        assert resp.get_json()["code"] == "ELEVATION_REQUIRED"


def test_reading_secret_metadata_is_not_gated(client, jit, admin, auth_header):
    """Listing secrets does not expose values, so it stays frictionless."""
    assert client.get("/admin/secrets", headers=auth_header(admin)).status_code == 200


def test_elevation_unlocks_the_secret_vault(client, jit, admin):
    headers = _bearer(_login(client))
    assert client.post("/admin/secrets", headers=headers,
                       json=_secret_payload()).status_code == 403

    assert _elevate(client, headers, key="manage_secrets",
                    reason="creating the prod database credential").status_code == 201

    resp = client.post("/admin/secrets", headers=headers, json=_secret_payload())
    assert resp.status_code == 201, resp.get_json()
