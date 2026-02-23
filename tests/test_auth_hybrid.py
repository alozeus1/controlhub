from datetime import datetime, timedelta
import os
os.environ.setdefault("SQLALCHEMY_DATABASE_URI", "sqlite:////tmp/controlhub_test_auth.db")
os.environ.setdefault("RATELIMIT_STORAGE_URL", "memory://")
os.environ.setdefault("REDIS_URL", "redis://localhost:0/0")

import pytest
from flask_jwt_extended import create_access_token

from app import create_app
from app.extensions import db
from app.models import User, PasswordResetToken


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
    user = User(email=email, role=role, auth_provider="local", email_verified=True, **kwargs)
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
