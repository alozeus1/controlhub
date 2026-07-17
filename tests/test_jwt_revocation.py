"""
P1-2 regression: JWT revocation fails CLOSED when the revocation store (Redis)
cannot be reached, so revoked/compromised tokens cannot be used during an outage.
"""
import pytest


class _BrokenRedis:
    """Simulates Redis being unreachable — every op raises."""
    def get(self, *a, **k):
        raise ConnectionError("redis down")


class _OkRedis:
    """Simulates a healthy store that reports the token as NOT revoked."""
    def get(self, *a, **k):
        return None


@pytest.fixture
def admin(create_user):
    return create_user("admin@x.com", role="admin")


def test_fail_closed_denies_when_redis_unavailable(app, client, admin, auth_header):
    # Production policy: fail closed.
    app.config["JWT_FAIL_OPEN"] = False
    app._redis = _BrokenRedis()

    resp = client.get("/admin/users", headers=auth_header(admin))
    assert resp.status_code == 401
    assert resp.get_json()["code"] == "TOKEN_REVOKED"


def test_fail_open_allows_when_explicitly_configured(app, client, admin, auth_header):
    # Bounded degraded mode: operator opts into availability over strict revocation.
    app.config["JWT_FAIL_OPEN"] = True
    app._redis = _BrokenRedis()

    resp = client.get("/admin/users", headers=auth_header(admin))
    assert resp.status_code == 200


def test_healthy_store_allows_valid_token(app, client, admin, auth_header):
    app.config["JWT_FAIL_OPEN"] = False
    app._redis = _OkRedis()   # store reachable, token not revoked

    resp = client.get("/admin/users", headers=auth_header(admin))
    assert resp.status_code == 200


def test_no_store_configured_fails_closed(app, client, admin, auth_header):
    app.config["JWT_FAIL_OPEN"] = False
    app._redis = None

    resp = client.get("/admin/users", headers=auth_header(admin))
    assert resp.status_code == 401
    assert resp.get_json()["code"] == "TOKEN_REVOKED"
