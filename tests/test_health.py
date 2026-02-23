import pytest
import os
os.environ.setdefault("SQLALCHEMY_DATABASE_URI", "sqlite:///:memory:")
os.environ.setdefault("RATELIMIT_STORAGE_URL", "memory://")
from app import create_app


@pytest.fixture
def app():
    app = create_app()
    app.config["TESTING"] = True
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    return app


@pytest.fixture
def client(app):
    return app.test_client()


def test_healthz_returns_200(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json == {"status": "ok"}


def test_healthz_returns_request_id_header(client):
    response = client.get("/healthz")
    assert "X-Request-ID" in response.headers


def test_healthz_preserves_incoming_request_id(client):
    response = client.get("/healthz", headers={"X-Request-ID": "test-123"})
    assert response.headers["X-Request-ID"] == "test-123"
