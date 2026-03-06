import pytest
from flask_jwt_extended import create_access_token


@pytest.fixture
def app(tmp_path, monkeypatch):
    db_path = tmp_path / "test.sqlite"
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("SQLALCHEMY_DATABASE_URI", f"sqlite:///{db_path}")
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("JWT_SECRET_KEY", "test-jwt-secret")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/15")
    monkeypatch.setenv("RATELIMIT_STORAGE_URL", "memory://")
    monkeypatch.setenv("FEATURE_SERVICE_ACCOUNTS", "true")
    monkeypatch.setenv("FEATURE_NOTIFICATIONS", "true")
    monkeypatch.setenv("FEATURE_INTEGRATIONS", "true")
    monkeypatch.setenv("FEATURE_ASSETS", "true")
    monkeypatch.setenv("FEATURE_PEOPLE", "true")
    monkeypatch.setenv("FEATURE_INTERNSHIP_PROGRAM", "true")
    monkeypatch.setenv("FEATURE_AGENT_SERVICE", "true")
    monkeypatch.setenv("AGENT_EXPORT_APPROVAL_ROW_THRESHOLD", "2")
    monkeypatch.setenv("AGENT_ARTIFACTS_DIR", str(tmp_path / "artifacts"))
    monkeypatch.setenv("AGENT_EXTERNAL_SHEET_ALLOWLIST", "sheet_approved")
    monkeypatch.setenv("SECRET_ENCRYPTION_KEYS", "R4wQ8z6KC8J65f7MsnfCh7yv8jGtvnCG2l9VmOAXo5Y=")

    from app import create_app
    from app.extensions import db

    app = create_app()
    app.config.update(TESTING=True)

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def create_user(app):
    from app.extensions import db
    from app.models import User

    def _create_user(email, role="user", is_active=True, password="Pass1234!"):
        user = User(email=email, role=role, is_active=is_active)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        return user

    return _create_user


@pytest.fixture
def auth_header(app):
    def _auth_header(user):
        with app.app_context():
            token = create_access_token(identity=str(user.id))
        return {"Authorization": f"Bearer {token}"}

    return _auth_header
