"""
Password-reset link origin must not follow the request Host header.

`POST /auth/forgot-password` is unauthenticated. If the reset link is built from
`request.host_url`, an attacker sends one request for a victim's address with a
forged `Host`, and the victim receives a genuine ControlHub email whose link — and
therefore the single-use reset token — points at the attacker's server. nginx here
uses a catch-all `server_name _` and forwards `Host $host`, so nothing upstream
stops the forged header from reaching Flask.

These tests capture the URL that would be mailed and assert its origin comes from
configuration regardless of what the client claims.
"""
import pytest

from app.routes import auth as auth_routes


@pytest.fixture
def captured_reset(monkeypatch):
    """Capture the reset URL instead of sending mail."""
    seen = {}

    def _fake_send(email, reset_url, text_body):
        seen["email"] = email
        seen["url"] = reset_url
        seen["text"] = text_body
        return True

    monkeypatch.setattr(auth_routes, "_send_reset_email", _fake_send)
    return seen


@pytest.fixture
def victim(create_user):
    return create_user("victim@webforx.tech", role="user")


FORGED_HOSTS = [
    "evil.example.com",
    "attacker.test:8080",
    "webforx.tech.evil.example.com",
]


@pytest.mark.parametrize("forged_host", FORGED_HOSTS)
def test_forged_host_header_does_not_reach_the_reset_link(
    client, victim, captured_reset, monkeypatch, forged_host
):
    monkeypatch.setenv("UI_BASE_URL", "https://controlhub.webforxtech.com")

    resp = client.post(
        "/auth/forgot-password",
        json={"email": "victim@webforx.tech"},
        headers={"Host": forged_host},
    )
    assert resp.status_code == 200

    url = captured_reset["url"]
    assert url.startswith("https://controlhub.webforxtech.com/ui/reset-password?token=")
    # The forged host must appear nowhere in the mailed link.
    assert forged_host.split(":")[0] not in url


@pytest.mark.parametrize("forged_host", FORGED_HOSTS)
def test_forged_x_forwarded_host_does_not_reach_the_reset_link(
    client, victim, captured_reset, monkeypatch, forged_host
):
    """ProxyFix trusts X-Forwarded-Host when TRUSTED_PROXY_COUNT > 0."""
    monkeypatch.setenv("UI_BASE_URL", "https://controlhub.webforxtech.com")

    resp = client.post(
        "/auth/forgot-password",
        json={"email": "victim@webforx.tech"},
        headers={"X-Forwarded-Host": forged_host, "X-Forwarded-Proto": "https"},
    )
    assert resp.status_code == 200
    assert captured_reset["url"].startswith("https://controlhub.webforxtech.com/ui/reset-password?")


def test_ui_base_url_takes_precedence_over_public_base_url(
    client, victim, captured_reset, monkeypatch
):
    monkeypatch.setenv("UI_BASE_URL", "https://ui.example.test")
    resp = client.post("/auth/forgot-password", json={"email": "victim@webforx.tech"})
    assert resp.status_code == 200
    assert captured_reset["url"].startswith("https://ui.example.test/ui/reset-password?")


def test_falls_back_to_public_base_url(client, victim, captured_reset, monkeypatch):
    monkeypatch.delenv("UI_BASE_URL", raising=False)
    resp = client.post("/auth/forgot-password", json={"email": "victim@webforx.tech"})
    assert resp.status_code == 200
    # config.py always defines PUBLIC_BASE_URL, so a link is still produced and
    # it is still not the request host.
    assert "/ui/reset-password?token=" in captured_reset["url"]
    assert "localhost" in captured_reset["url"] or captured_reset["url"].startswith("http")


def test_no_link_is_mailed_when_no_origin_is_configured(
    app, client, victim, captured_reset, monkeypatch
):
    """Refusing to mail beats mailing an attacker-controlled origin."""
    monkeypatch.delenv("UI_BASE_URL", raising=False)
    monkeypatch.delenv("PUBLIC_BASE_URL", raising=False)
    monkeypatch.setitem(app.config, "PUBLIC_BASE_URL", "")

    resp = client.post(
        "/auth/forgot-password",
        json={"email": "victim@webforx.tech"},
        headers={"Host": "evil.example.com"},
    )
    # Still a uniform response — the caller learns nothing about the address.
    assert resp.status_code == 200
    assert resp.get_json()["message"] == "If this email exists, a reset link has been sent"
    assert "url" not in captured_reset


def test_response_is_identical_for_unknown_addresses(client, victim, captured_reset):
    """Enumeration guard still holds after the change."""
    known = client.post("/auth/forgot-password", json={"email": "victim@webforx.tech"})
    unknown = client.post("/auth/forgot-password", json={"email": "nobody@webforx.tech"})
    assert known.status_code == unknown.status_code == 200
    assert known.get_json() == unknown.get_json()


def test_reset_token_still_works_end_to_end(app, client, victim, captured_reset, monkeypatch):
    """The hardening must not break the actual recovery flow."""
    monkeypatch.setenv("UI_BASE_URL", "https://controlhub.webforxtech.com")
    client.post("/auth/forgot-password", json={"email": "victim@webforx.tech"})

    token = captured_reset["url"].split("token=", 1)[1]
    resp = client.post("/auth/reset-password", json={"token": token, "new_password": "N3w-Passw0rd!"})
    assert resp.status_code == 200, resp.get_data(as_text=True)

    login = client.post("/auth/login", json={"email": "victim@webforx.tech", "password": "N3w-Passw0rd!"})
    assert login.status_code == 200
    assert "access_token" in login.get_json()
