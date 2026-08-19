"""
Tests for the SES sender-identity controls: the verified-domain allowlist, the
separate transactional identity, and the fail-closed production config gate.
"""
import pytest

from app.services import email_ses
from config import Config


# ─── Verified-domain allowlist ────────────────────────────────────────────────

def test_allowlist_empty_permits_any_sender(monkeypatch):
    monkeypatch.delenv("SES_ALLOWED_SENDER_DOMAINS", raising=False)
    assert email_ses.sender_domain_allowed("anyone@example.com") is True


def test_allowlist_permits_verified_domains(monkeypatch):
    monkeypatch.setenv("SES_ALLOWED_SENDER_DOMAINS", "webforxtech.com,dev.webforxtech.com")
    assert email_ses.sender_domain_allowed("noreply@webforxtech.com") is True
    assert email_ses.sender_domain_allowed("noreply@dev.webforxtech.com") is True


def test_allowlist_rejects_unverified_domain(monkeypatch):
    monkeypatch.setenv("SES_ALLOWED_SENDER_DOMAINS", "webforxtech.com,dev.webforxtech.com")
    assert email_ses.sender_domain_allowed("noreply@attacker.com") is False


def test_allowlist_does_not_imply_subdomains(monkeypatch):
    """Subdomains need their own SES verification, so they need their own entry."""
    monkeypatch.setenv("SES_ALLOWED_SENDER_DOMAINS", "webforxtech.com")
    assert email_ses.sender_domain_allowed("noreply@mail.webforxtech.com") is False


def test_allowlist_is_case_and_whitespace_tolerant(monkeypatch):
    monkeypatch.setenv("SES_ALLOWED_SENDER_DOMAINS", " WebForxTech.com , @dev.webforxtech.com ")
    assert email_ses.sender_domain_allowed("noreply@WEBFORXTECH.COM") is True
    assert email_ses.sender_domain_allowed("noreply@dev.webforxtech.com") is True


def test_send_email_blocks_disallowed_sender_before_calling_ses(monkeypatch):
    """A bad From must fail locally — no SES client is built, nothing is sent."""
    monkeypatch.setenv("SES_ALLOWED_SENDER_DOMAINS", "webforxtech.com")
    monkeypatch.setenv("SES_SENDING_ENABLED", "true")
    monkeypatch.setenv("EMAIL_PROVIDER", "aws")

    def _explode():  # pragma: no cover - must never run
        raise AssertionError("SES client must not be built for a disallowed sender")

    monkeypatch.setattr(email_ses, "build_ses_client", _explode)

    result = email_ses.send_email("to@x.com", "s", "<p>b</p>", from_address="evil@attacker.com")
    assert not result.ok
    assert "SenderDomainNotAllowed" in result.error


# ─── Transactional identity ───────────────────────────────────────────────────

def test_transactional_config_falls_back_to_campaign_identity(monkeypatch):
    monkeypatch.delenv("SES_TRANSACTIONAL_FROM_ADDRESS", raising=False)
    monkeypatch.setenv("SES_FROM_ADDRESS", "campaigns@webforxtech.com")
    assert email_ses.get_transactional_config()["from_address"] == "campaigns@webforxtech.com"
    assert email_ses.transactional_ses_configured() is False


def test_transactional_config_overrides_identity_and_config_set(monkeypatch):
    monkeypatch.setenv("SES_FROM_ADDRESS", "campaigns@webforxtech.com")
    monkeypatch.setenv("SES_CONFIGURATION_SET", "campaigns-set")
    monkeypatch.setenv("SES_TRANSACTIONAL_FROM_ADDRESS", "noreply@webforxtech.com")
    monkeypatch.setenv("SES_TRANSACTIONAL_CONFIGURATION_SET", "transactional-set")

    cfg = email_ses.get_transactional_config()
    assert cfg["from_address"] == "noreply@webforxtech.com"
    assert cfg["configuration_set"] == "transactional-set"
    assert email_ses.transactional_ses_configured() is True


def test_transactional_send_uses_transactional_identity(monkeypatch):
    monkeypatch.setenv("SES_ALLOWED_SENDER_DOMAINS", "webforxtech.com")
    monkeypatch.setenv("SES_TRANSACTIONAL_FROM_ADDRESS", "noreply@webforxtech.com")
    monkeypatch.setenv("SES_TRANSACTIONAL_CONFIGURATION_SET", "transactional-set")
    monkeypatch.setenv("SES_SENDING_ENABLED", "true")
    monkeypatch.setenv("EMAIL_PROVIDER", "aws")

    captured = {}

    class _FakeClient:
        def send_email(self, **kwargs):
            captured.update(kwargs)
            return {"MessageId": "msg-1"}

    monkeypatch.setattr(email_ses, "build_ses_client", lambda: _FakeClient())

    result = email_ses.send_transactional_email(
        "user@x.com", "Reset", "<p>link</p>", text_body="link",
    )
    assert result.ok
    assert captured["FromEmailAddress"] == "Web Forx ControlHub <noreply@webforxtech.com>"
    assert captured["ConfigurationSetName"] == "transactional-set"
    # Both parts present so the message is not text-less (a spam signal).
    body = captured["Content"]["Simple"]["Body"]
    assert body["Html"]["Data"] == "<p>link</p>"
    assert body["Text"]["Data"] == "link"


# ─── Fail-closed production config gate ───────────────────────────────────────

def _prod_env(monkeypatch, **overrides):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("SECRET_KEY", "x" * 32)
    monkeypatch.setenv("JWT_SECRET_KEY", "y" * 32)
    monkeypatch.setenv("SQLALCHEMY_DATABASE_URI", "postgresql://localhost/db")
    monkeypatch.setenv("SECRET_ENCRYPTION_KEYS", "v1:" + "z" * 32)
    monkeypatch.setenv("CORS_ORIGINS", "https://controlhub.webforxtech.com")
    monkeypatch.setenv("EMAIL_PROVIDER", "aws")
    for key, value in overrides.items():
        monkeypatch.setenv(key, value)


def test_prod_requires_sender_allowlist_when_provider_is_aws(monkeypatch):
    _prod_env(monkeypatch)
    monkeypatch.delenv("SES_ALLOWED_SENDER_DOMAINS", raising=False)
    with pytest.raises(SystemExit):
        Config().validate()


def test_prod_rejects_sender_outside_allowlist(monkeypatch):
    _prod_env(monkeypatch,
              SES_ALLOWED_SENDER_DOMAINS="webforxtech.com",
              SES_FROM_ADDRESS="campaigns@somewhere-else.com")
    with pytest.raises(SystemExit):
        Config().validate()


def test_prod_accepts_verified_senders(monkeypatch):
    _prod_env(monkeypatch,
              SES_ALLOWED_SENDER_DOMAINS="webforxtech.com,dev.webforxtech.com",
              SES_FROM_ADDRESS="campaigns@webforxtech.com",
              SES_TRANSACTIONAL_FROM_ADDRESS="noreply@dev.webforxtech.com")
    Config().validate()  # must not raise


def test_localstack_provider_skips_the_gate(monkeypatch):
    """Dev on LocalStack must keep booting without SES domain config."""
    _prod_env(monkeypatch, EMAIL_PROVIDER="localstack")
    monkeypatch.delenv("SES_ALLOWED_SENDER_DOMAINS", raising=False)
    Config().validate()  # must not raise


# ─── Password reset delivery ──────────────────────────────────────────────────

def test_password_reset_sends_via_ses_when_configured(client, create_user, monkeypatch):
    """Password reset must go out over SES once a transactional sender is set."""
    monkeypatch.setenv("SES_ALLOWED_SENDER_DOMAINS", "webforxtech.com")
    monkeypatch.setenv("SES_TRANSACTIONAL_FROM_ADDRESS", "noreply@webforxtech.com")
    monkeypatch.setenv("SES_SENDING_ENABLED", "true")
    monkeypatch.setenv("EMAIL_PROVIDER", "aws")
    create_user("reset-me@x.com")

    sent = {}

    class _FakeClient:
        def send_email(self, **kwargs):
            sent.update(kwargs)
            return {"MessageId": "msg-reset"}

    monkeypatch.setattr(email_ses, "build_ses_client", lambda: _FakeClient())

    resp = client.post("/auth/forgot-password", json={"email": "reset-me@x.com"})
    assert resp.status_code == 200
    assert sent["FromEmailAddress"] == "Web Forx ControlHub <noreply@webforxtech.com>"
    assert sent["Destination"]["ToAddresses"] == ["reset-me@x.com"]
    assert "/ui/reset-password?token=" in sent["Content"]["Simple"]["Body"]["Text"]["Data"]


def test_password_reset_without_ses_still_returns_generic_response(client, create_user, monkeypatch):
    """No SES configured: the endpoint must not leak that delivery did not happen."""
    monkeypatch.delenv("SES_TRANSACTIONAL_FROM_ADDRESS", raising=False)
    create_user("no-ses@x.com")

    resp = client.post("/auth/forgot-password", json={"email": "no-ses@x.com"})
    assert resp.status_code == 200
    assert resp.get_json()["message"] == "If this email exists, a reset link has been sent"
