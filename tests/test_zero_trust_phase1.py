"""
Zero-trust Phase 1 controls.

Covers the assume-breach hardening: MFA failing closed, real client IPs behind
the proxy, refresh-token rotation with reuse detection, the session revocation
epoch, the tamper-evident audit chain, and the agent export budget.
"""
import pytest

from app.extensions import db
from app.models import AuditLog, User
from app.services import audit_chain, session_security


class FakeRedis:
    """Minimal Redis stand-in: enough for the blocklist and refresh-family keys."""

    def __init__(self):
        self.store = {}

    def get(self, key):
        return self.store.get(key)

    def setex(self, key, ttl, value):
        self.store[key] = value
        return True

    def set(self, key, value, nx=False, ex=None):
        if nx and key in self.store:
            return None
        self.store[key] = value
        return True


@pytest.fixture
def redis_app(app):
    """App with a working revocation store, so fail-open cannot mask a result."""
    app.config["JWT_FAIL_OPEN"] = False
    app._redis = FakeRedis()
    return app


# ─── MFA must fail closed ─────────────────────────────────────────────────────

def test_login_denied_when_mfa_layer_errors(client, app, create_user, monkeypatch):
    """
    A fault in the MFA layer must not fall through to a password-only session.

    This is the regression guard for the previous `except Exception: pass`,
    which silently downgraded every MFA-protected account during a fault.
    """
    create_user("mfa-user@x.com", password="password123")  # secret-scan:allow - test fixture / parameter name, not a credential

    import app.routes.mfa as mfa_module

    def _boom(_user):
        raise RuntimeError("mfa backend down")

    monkeypatch.setattr(mfa_module, "mfa_enabled_for", _boom)

    resp = client.post("/auth/login", json={"email": "mfa-user@x.com",
                                            "password": "password123"})
    assert resp.status_code == 503
    assert resp.get_json()["code"] == "MFA_UNAVAILABLE"
    # Critically: no tokens were handed out.
    assert "access_token" not in resp.get_json()


# ─── Client IP attribution ────────────────────────────────────────────────────

def test_audit_ip_ignores_forged_forwarded_header(client, app, create_user):
    """
    With no trusted proxy configured, a client-supplied X-Forwarded-For must not
    become the audit source IP — otherwise attribution is attacker-controlled.
    """
    create_user("ip-test@x.com", password="password123")  # secret-scan:allow - test fixture / parameter name, not a credential

    client.post("/auth/login",
                json={"email": "ip-test@x.com", "password": "password123"},
                headers={"X-Forwarded-For": "1.2.3.4"})

    entry = (AuditLog.query.filter(AuditLog.action.like("%login%"))
             .order_by(AuditLog.id.desc()).first())
    assert entry is not None
    assert entry.ip_address != "1.2.3.4"


def test_proxyfix_applied_when_trusted_proxy_count_set(monkeypatch, tmp_path):
    """With TRUSTED_PROXY_COUNT=1, remote_addr comes from the proxy's XFF hop."""
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("SQLALCHEMY_DATABASE_URI", f"sqlite:///{tmp_path}/proxy.sqlite")
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("JWT_SECRET_KEY", "test-jwt-secret")
    monkeypatch.setenv("RATELIMIT_STORAGE_URL", "memory://")
    monkeypatch.setenv("TRUSTED_PROXY_COUNT", "1")

    from app import create_app
    proxied = create_app()

    seen = {}

    @proxied.route("/__ip")
    def _ip():
        from flask import request
        seen["remote_addr"] = request.remote_addr
        return "ok"

    proxied.test_client().get("/__ip", headers={"X-Forwarded-For": "9.9.9.9"})
    assert seen["remote_addr"] == "9.9.9.9"


# ─── Refresh rotation + reuse detection ───────────────────────────────────────

def _login(client, email="rot@x.com", password="password123"):  # secret-scan:allow - test fixture / parameter name, not a credential
    resp = client.post("/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()


def test_refresh_rotates_the_refresh_token(client, redis_app, create_user):
    create_user("rot@x.com", password="password123")  # secret-scan:allow - test fixture / parameter name, not a credential
    tokens = _login(client)

    resp = client.post("/auth/refresh",
                       headers={"Authorization": f"Bearer {tokens['refresh_token']}"})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["refresh_token"] != tokens["refresh_token"], "refresh token must rotate"


def test_replaying_a_consumed_refresh_token_kills_the_family(client, redis_app, create_user):
    """
    The core session-theft control: a replayed refresh token revokes the whole
    family, so neither the attacker nor the legitimate holder keeps the session.
    """
    create_user("replay@x.com", password="password123")  # secret-scan:allow - test fixture / parameter name, not a credential
    tokens = _login(client, "replay@x.com")
    old_refresh = tokens["refresh_token"]

    first = client.post("/auth/refresh", headers={"Authorization": f"Bearer {old_refresh}"})
    assert first.status_code == 200
    rotated = first.get_json()["refresh_token"]

    # Attacker replays the captured (already-spent) token.
    replay = client.post("/auth/refresh", headers={"Authorization": f"Bearer {old_refresh}"})
    assert replay.status_code == 401
    assert replay.get_json()["code"] == "TOKEN_REUSE_DETECTED"

    # And the legitimate rotated token is dead too — the family was revoked.
    after = client.post("/auth/refresh", headers={"Authorization": f"Bearer {rotated}"})
    assert after.status_code == 401

    assert AuditLog.query.filter_by(action="auth.refresh_token_reuse").count() == 1


def test_reuse_check_fails_closed_without_redis(app):
    """No revocation store means we cannot tell first use from replay — deny."""
    app.config["JWT_FAIL_OPEN"] = False
    app._redis = None
    assert session_security.consume_refresh_token("jti-1", "fam-1") is False


# ─── Session revocation epoch ─────────────────────────────────────────────────

def test_bumping_epoch_invalidates_existing_access_token(client, redis_app, create_user):
    user = create_user("epoch@x.com", password="password123")  # secret-scan:allow - test fixture / parameter name, not a credential
    tokens = _login(client, "epoch@x.com")
    auth = {"Authorization": f"Bearer {tokens['access_token']}"}

    assert client.get("/auth/me", headers=auth).status_code == 200

    session_security.bump_session_epoch(user, "test")

    assert client.get("/auth/me", headers=auth).status_code == 401


def test_disabling_a_user_kills_their_live_tokens(client, redis_app, create_user, auth_header):
    """Disable must take effect on tokens already issued, not just at next login."""
    admin = create_user("admin-epoch@x.com", role="superadmin")
    victim = create_user("victim@x.com", password="password123")  # secret-scan:allow - test fixture / parameter name, not a credential
    tokens = _login(client, "victim@x.com")
    victim_auth = {"Authorization": f"Bearer {tokens['access_token']}"}

    assert client.get("/auth/me", headers=victim_auth).status_code == 200

    resp = client.patch(f"/admin/users/{victim.id}",
                        headers=auth_header(admin), json={"is_active": False})
    assert resp.status_code == 200

    assert client.get("/auth/me", headers=victim_auth).status_code in (401, 403)


def test_password_change_returns_fresh_tokens(client, redis_app, create_user):
    """All sessions die, but the caller's own tab keeps working via the new pair."""
    create_user("pw@x.com", password="password123")  # secret-scan:allow - test fixture / parameter name, not a credential
    tokens = _login(client, "pw@x.com")
    auth = {"Authorization": f"Bearer {tokens['access_token']}"}

    resp = client.post("/auth/change-password", headers=auth,
                       json={"current_password": "password123",
                             "new_password": "newpassword456"})
    assert resp.status_code == 200
    new_tokens = resp.get_json()
    assert "access_token" in new_tokens

    # Old token retired, new one works.
    assert client.get("/auth/me", headers=auth).status_code == 401
    assert client.get("/auth/me", headers={
        "Authorization": f"Bearer {new_tokens['access_token']}"}).status_code == 200


# ─── Tamper-evident audit chain ───────────────────────────────────────────────

def _write_entries(app, count=3):
    from app.utils.audit import log_action
    for i in range(count):
        log_action(action=f"test.event.{i}", target_type="test", target_label=str(i))


def test_audit_entries_are_chained(app):
    _write_entries(app, 3)
    rows = AuditLog.query.order_by(AuditLog.id.asc()).all()
    assert all(r.row_hash for r in rows)
    for earlier, later in zip(rows, rows[1:]):
        assert later.prev_hash == earlier.row_hash


def test_chain_verifies_clean(app):
    _write_entries(app, 4)
    result = audit_chain.verify_chain()
    assert result["ok"] is True
    assert result["checked"] == 4


def test_chain_detects_a_modified_row(app):
    _write_entries(app, 4)
    victim = AuditLog.query.order_by(AuditLog.id.asc()).offset(1).first()
    victim.action = "test.event.tampered"
    db.session.commit()

    result = audit_chain.verify_chain()
    assert result["ok"] is False
    assert result["first_bad_id"] == victim.id
    assert "modified" in result["reason"]


def test_chain_detects_a_deleted_row(app):
    """Deleting the evidence is the attack this exists to catch."""
    _write_entries(app, 4)
    rows = AuditLog.query.order_by(AuditLog.id.asc()).all()
    db.session.delete(rows[1])
    db.session.commit()

    result = audit_chain.verify_chain()
    assert result["ok"] is False
    assert result["first_bad_id"] == rows[2].id
    assert "deleted" in result["reason"]


def test_unsealed_legacy_rows_do_not_false_positive(app):
    """Pre-migration rows carry no hash and must not be reported as tampering."""
    db.session.add(AuditLog(action="legacy.event", actor_email="old@x.com"))
    db.session.commit()
    _write_entries(app, 2)

    assert audit_chain.verify_chain()["ok"] is True


# ─── Agent daily export budget ────────────────────────────────────────────────

def test_budget_allows_within_limit(app, create_user):
    from app.services.agent_service import check_daily_export_budget
    user = create_user("budget-ok@x.com")
    allowed, detail = check_daily_export_budget(user.id, row_count=100, budget=5000)
    assert allowed is True
    assert detail["rows_last_24h"] == 0


def test_budget_blocks_sliced_exfiltration(app, create_user):
    """
    Many small requests each pass the per-request approval threshold; the
    cumulative cap is what stops them.
    """
    from app.models import AgentRequest
    from app.services.agent_service import check_daily_export_budget

    user = create_user("budget-slice@x.com")
    for _ in range(5):
        db.session.add(AgentRequest(
            requester_user_id=user.id, module_scope="people", output_type="csv",
            template_id="t", destination_type="download", status="completed",
            row_count=180,
        ))
    db.session.commit()

    allowed, detail = check_daily_export_budget(user.id, row_count=180, budget=1000)
    assert allowed is False
    assert detail["code"] == "EXPORT_BUDGET_EXCEEDED"
    assert detail["rows_last_24h"] == 900


def test_budget_of_zero_disables_the_cap(app, create_user):
    from app.services.agent_service import check_daily_export_budget
    user = create_user("budget-off@x.com")
    allowed, _ = check_daily_export_budget(user.id, row_count=10**6, budget=0)
    assert allowed is True
