from datetime import datetime, timedelta
import os
os.environ.setdefault("SQLALCHEMY_DATABASE_URI", "sqlite:////tmp/controlhub_test_auth.db")
os.environ.setdefault("RATELIMIT_STORAGE_URL", "memory://")
os.environ.setdefault("REDIS_URL", "redis://localhost:0/0")

import pytest
from flask_jwt_extended import create_access_token

from app import create_app
from app.extensions import db
from app.models import User, PasswordResetToken, AuditLog


@pytest.fixture
def app():
    try:
        os.remove("/tmp/controlhub_test_auth.db")
    except FileNotFoundError:
        pass
    app = create_app()
    app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        AUTH_MODE="hybrid",
        MAX_FAILED_LOGIN_ATTEMPTS=3,
        ACCOUNT_LOCKOUT_MINUTES=15,
        COGNITO_APP_CLIENT_ID="client",
        COGNITO_ISSUER="https://issuer",
        COGNITO_JWKS_URL="https://issuer/.well-known/jwks.json",
        RATELIMIT_ENABLED=False,
    )
    app._redis = None
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()
    try:
        os.remove("/tmp/controlhub_test_auth.db")
    except FileNotFoundError:
        pass


@pytest.fixture
def client(app):
    return app.test_client()


def create_user(email="user@example.com", password="StrongPass!123", role="user", **kwargs):
    auth_provider = kwargs.pop("auth_provider", "local")
    email_verified = kwargs.pop("email_verified", True)
    user = User(email=email, role=role, auth_provider=auth_provider, email_verified=email_verified, **kwargs)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return user


def test_local_login_success(client, app):
    with app.app_context():
        create_user()

    res = client.post("/auth/login", json={"email": "user@example.com", "password": "StrongPass!123"})
    assert res.status_code == 200
    assert res.json["access_token"]
    assert res.json["refresh_token"]


def test_local_login_lockout(client, app):
    with app.app_context():
        create_user()

    for _ in range(3):
        res = client.post("/auth/login", json={"email": "user@example.com", "password": "wrong"})
        assert res.status_code == 401

    locked = client.post("/auth/login", json={"email": "user@example.com", "password": "StrongPass!123"})
    assert locked.status_code == 423


def test_password_policy_enforced_on_reset(client, app):
    with app.app_context():
        user = create_user()
        raw, token_obj = PasswordResetToken.generate(user.id, expires_minutes=60)
        db.session.add(token_obj)
        db.session.commit()

    res = client.post("/auth/reset-password", json={"token": raw, "new_password": "short"})
    assert res.status_code == 400
    assert "Password must be at least 12" in res.json["error"]


def test_password_policy_enforced_on_change(client, app):
    with app.app_context():
        user = create_user()
        token = create_access_token(identity=str(user.id), additional_claims={"provider": "local"})

    res = client.post(
        "/auth/change-password",
        headers={"Authorization": f"Bearer {token}"},
        json={"current_password": "StrongPass!123", "new_password": "weakpass"},
    )
    assert res.status_code == 400


def test_cognito_login_links_existing_user_by_email(client, app, monkeypatch):
    with app.app_context():
        create_user(email="linkme@example.com")

    class Identity:
        sub = "sub-123"
        email = "linkme@example.com"
        claims = {"email_verified": True}

    class Verifier:
        def verify(self, _):
            return Identity()

    monkeypatch.setattr("app.routes.auth.get_cognito_verifier", lambda: Verifier())

    res = client.post("/auth/cognito/login", json={"id_token": "token"})
    assert res.status_code == 200

    with app.app_context():
        user = User.query.filter_by(email="linkme@example.com").first()
        assert user.cognito_sub == "sub-123"


def test_cognito_login_finds_user_by_sub(client, app, monkeypatch):
    with app.app_context():
        create_user(email="sub@example.com", cognito_sub="known-sub")

    class Identity:
        sub = "known-sub"
        email = "other@example.com"
        claims = {"email_verified": True}

    class Verifier:
        def verify(self, _):
            return Identity()

    monkeypatch.setattr("app.routes.auth.get_cognito_verifier", lambda: Verifier())

    res = client.post("/auth/cognito/login", json={"id_token": "token"})
    assert res.status_code == 200
    assert res.json["user"]["email"] == "sub@example.com"


def test_cognito_login_failure_bad_token(client, monkeypatch):
    class Verifier:
        def verify(self, _):
            raise Exception("bad")

    monkeypatch.setattr("app.routes.auth.get_cognito_verifier", lambda: Verifier())
    res = client.post("/auth/cognito/login", json={"id_token": "bad"})
    assert res.status_code == 401


def test_hybrid_middleware_accepts_local_and_cognito_token(client, app, monkeypatch):
    with app.app_context():
        viewer = create_user(email="viewer@example.com", role="viewer")
        local_token = create_access_token(identity=str(viewer.id), additional_claims={"provider": "local"})

    local_res = client.get("/admin/users", headers={"Authorization": f"Bearer {local_token}"})
    assert local_res.status_code == 200

    class Identity:
        sub = "sub-viewer"
        email = "viewer@example.com"
        claims = {"email_verified": True}

    class Verifier:
        def verify(self, _):
            return Identity()

    monkeypatch.setattr("app.utils.rbac.get_cognito_verifier", lambda: Verifier())
    cognito_res = client.get("/admin/users", headers={"Authorization": "Bearer opaque-cognito-token"})
    assert cognito_res.status_code == 200


def test_rbac_uses_local_db_roles_for_cognito(client, app, monkeypatch):
    with app.app_context():
        create_user(email="basic@example.com", role="user")

    class Identity:
        sub = "sub-basic"
        email = "basic@example.com"
        claims = {"email_verified": True}

    class Verifier:
        def verify(self, _):
            return Identity()

    monkeypatch.setattr("app.utils.rbac.get_cognito_verifier", lambda: Verifier())
    res = client.get("/admin/users", headers={"Authorization": "Bearer opaque"})
    assert res.status_code == 403



def test_cognito_login_linked_user_matching_sub_success(client, app, monkeypatch):
    with app.app_context():
        create_user(email="linked@example.com", cognito_sub="sub-ok")

    class Identity:
        sub = "sub-ok"
        email = "linked@example.com"
        claims = {"email_verified": True}

    class Verifier:
        def verify(self, _):
            return Identity()

    monkeypatch.setattr("app.routes.auth.get_cognito_verifier", lambda: Verifier())
    res = client.post("/auth/cognito/login", json={"id_token": "token"})
    assert res.status_code == 200


def test_cognito_login_linked_user_mismatched_sub_denied(client, app, monkeypatch):
    with app.app_context():
        user = create_user(email="linked2@example.com", cognito_sub="sub-expected")

    class Identity:
        sub = "sub-other"
        email = "linked2@example.com"
        claims = {"email_verified": True}

    class Verifier:
        def verify(self, _):
            return Identity()

    monkeypatch.setattr("app.routes.auth.get_cognito_verifier", lambda: Verifier())
    res = client.post("/auth/cognito/login", json={"id_token": "token"})
    assert res.status_code == 401

    with app.app_context():
        mismatch = AuditLog.query.filter_by(action="auth.cognito_sub_mismatch_denied", target_label="linked2@example.com").first()
        assert mismatch is not None
        u = User.query.filter_by(email="linked2@example.com").first()
        assert u.cognito_sub == "sub-expected"


def test_cognito_login_unlinked_user_unverified_email_denied(client, app, monkeypatch):
    with app.app_context():
        create_user(email="unverified@example.com", cognito_sub=None)

    class Identity:
        sub = "sub-unverified"
        email = "unverified@example.com"
        claims = {"email_verified": False}

    class Verifier:
        def verify(self, _):
            return Identity()

    monkeypatch.setattr("app.routes.auth.get_cognito_verifier", lambda: Verifier())
    res = client.post("/auth/cognito/login", json={"id_token": "token"})
    assert res.status_code == 401

    with app.app_context():
        u = User.query.filter_by(email="unverified@example.com").first()
        assert u.cognito_sub is None


def test_logout_local_and_cognito_emit_audit(client, app, monkeypatch):
    with app.app_context():
        user = create_user(email="logout@example.com", role="viewer")
        local_token = create_access_token(identity=str(user.id), additional_claims={"provider": "local"})

    local_res = client.post("/auth/logout", headers={"Authorization": f"Bearer {local_token}"})
    assert local_res.status_code == 200

    class Identity:
        sub = "sub-logout"
        email = "logout@example.com"
        claims = {"email_verified": True}

    class Verifier:
        def verify(self, _):
            return Identity()

    monkeypatch.setattr("app.utils.rbac.get_cognito_verifier", lambda: Verifier())
    cognito_res = client.post("/auth/logout", headers={"Authorization": "Bearer opaque-cognito-token"})
    assert cognito_res.status_code == 200

    with app.app_context():
        events = AuditLog.query.filter_by(action="auth.logout", target_label="logout@example.com").all()
        assert len(events) >= 2


def test_me_endpoint_local_and_cognito(client, app, monkeypatch):
    with app.app_context():
        user = create_user(email="me@example.com", role="viewer", cognito_sub="sub-me")
        local_token = create_access_token(identity=str(user.id), additional_claims={"provider": "local"})

    local = client.get("/auth/me", headers={"Authorization": f"Bearer {local_token}"})
    assert local.status_code == 200
    assert local.json["email"] == "me@example.com"
    assert local.json["auth_provider"] == "local"

    class Identity:
        sub = "sub-me"
        email = "me@example.com"
        claims = {"email_verified": True}

    class Verifier:
        def verify(self, _):
            return Identity()

    monkeypatch.setattr("app.utils.rbac.get_cognito_verifier", lambda: Verifier())
    cognito = client.get("/auth/me", headers={"Authorization": "Bearer opaque-cognito-token"})
    assert cognito.status_code == 200
    assert cognito.json["auth_provider"] == "cognito"
    assert cognito.json["cognito_linked"] is True


def test_healthz_cognito_readiness_modes(client, app):
    app.config["AUTH_MODE"] = "local"
    local = client.get("/healthz")
    assert local.status_code == 200
    assert local.json["auth"]["readiness"] == "not_required"

    app.config["AUTH_MODE"] = "hybrid"
    app.config["COGNITO_ISSUER"] = ""
    app.config["COGNITO_APP_CLIENT_ID"] = ""
    app.config["COGNITO_JWKS_URL"] = ""
    mis = client.get("/healthz")
    assert mis.status_code == 200
    assert mis.json["auth"]["readiness"] == "misconfigured"


def test_admin_auth_links_and_audit_auth_filter(client, app):
    with app.app_context():
        viewer = create_user(email="viewer2@example.com", role="viewer")
        create_user(email="linked-view@example.com", role="user", cognito_sub="sub-linked", auth_provider="cognito")
        token = create_access_token(identity=str(viewer.id), additional_claims={"provider": "local"})
        db.session.add(AuditLog(action="auth.login_success", actor_id=viewer.id, actor_email=viewer.email))
        db.session.add(AuditLog(action="user.created", actor_id=viewer.id, actor_email=viewer.email))
        db.session.commit()

    auth_links = client.get("/admin/users/auth-links?linked=true", headers={"Authorization": f"Bearer {token}"})
    assert auth_links.status_code == 200
    assert all(item["cognito_linked"] for item in auth_links.json["items"])

    auth_logs = client.get("/admin/audit-logs?auth_only=true", headers={"Authorization": f"Bearer {token}"})
    assert auth_logs.status_code == 200
    assert all(item["action"].startswith("auth.") for item in auth_logs.json["items"])


def test_me_preserves_jwt_provider_claim_for_first_party_cognito_token(client, app):
    with app.app_context():
        user = create_user(email="claim-provider@example.com", role="viewer")
        token = create_access_token(identity=str(user.id), additional_claims={"provider": "cognito"})

    res = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    assert res.json["auth_provider"] == "cognito"


def test_logout_audit_uses_jwt_provider_claim(client, app):
    with app.app_context():
        user = create_user(email="logout-claim@example.com", role="viewer")
        token = create_access_token(identity=str(user.id), additional_claims={"provider": "cognito"})

    res = client.post("/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200

    with app.app_context():
        evt = AuditLog.query.filter_by(action="auth.logout", target_label="logout-claim@example.com").order_by(AuditLog.id.desc()).first()
        assert evt is not None
        assert evt.details.get("provider") == "cognito"


def test_logout_blocklists_any_first_party_jwt_regardless_of_provider(client, app):
    class FakeRedis:
        def __init__(self):
            self.calls = []

        def setex(self, key, ttl, value):
            self.calls.append((key, ttl, value))

    fake_redis = FakeRedis()
    app._redis = fake_redis

    with app.app_context():
        user = create_user(email="logout-blocklist@example.com", role="viewer")
        token = create_access_token(identity=str(user.id), additional_claims={"provider": "cognito"})

    res = client.post("/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    assert len(fake_redis.calls) == 1
    key, ttl, value = fake_redis.calls[0]
    assert key.startswith("blocklist:")
    assert value == "1"
    assert ttl > 0
