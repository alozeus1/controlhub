"""
Inbound SNS/SES webhook trust boundary.

`POST /email/webhooks/ses` is one of the few routes reachable with no
authenticated principal, and acting on a forged event lets an attacker add
arbitrary addresses to the suppression list — a denial of email delivery to any
recipient, including password resets. These tests pin the properties that make
the endpoint safe to expose: the signing certificate must come from SNS itself,
messages must be fresh, the topic must be the configured one, the subscription
handshake must not be an SSRF primitive, and a replay must not error.
"""
import json
from datetime import datetime, timedelta, timezone

import pytest

from app.services import email_ses


@pytest.fixture
def email_env(monkeypatch):
    """Mirror of the campaigns fixture: feature on, SES dry-run, sync send."""
    monkeypatch.setenv("FEATURE_EMAIL_CAMPAIGNS", "true")
    monkeypatch.setenv("SES_SENDING_ENABLED", "false")
    monkeypatch.setenv("CAMPAIGN_SEND_SYNC", "true")
    monkeypatch.setenv("EMAIL_PROVIDER", "localstack")
    monkeypatch.setenv("FLASK_ENV", "development")
    monkeypatch.delenv("SNS_TOPIC_ARN", raising=False)


def _iso(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _notification(**over):
    payload = {
        "Type": "Notification",
        "MessageId": "11111111-2222-3333-4444-555555555555",
        "TopicArn": "arn:aws:sns:us-east-1:000000000000:controlhub-ses-events",
        "Timestamp": _iso(datetime.now(timezone.utc)),
        "SignatureVersion": "1",
        "Signature": "AAAA",
        "SigningCertURL": "https://sns.us-east-1.amazonaws.com/SimpleNotificationService-abc.pem",
        "Message": json.dumps({"eventType": "Delivery", "mail": {"messageId": "m-1"}}),
    }
    payload.update(over)
    return payload


# ── Signing certificate host pinning ─────────────────────────────────────────

@pytest.mark.parametrize("url", [
    # The bug this replaces: a suffix test accepts any *.amazonaws.com host, so
    # an attacker serves their own certificate from S3 and forges every event.
    "https://attacker-bucket.s3.amazonaws.com/cert.pem",
    "https://s3.amazonaws.com/attacker-bucket/cert.pem",
    "https://sns.us-east-1.amazonaws.com.evil.com/cert.pem",
    "https://evil.com/?x=sns.us-east-1.amazonaws.com",
    # TLS is required: a plaintext fetch lets the certificate be swapped in transit.
    "http://sns.us-east-1.amazonaws.com/cert.pem",
    "",
    "not-a-url",
])
def test_non_sns_signing_cert_urls_are_refused(url):
    with pytest.raises(ValueError):
        email_ses.assert_sns_owned_url(url)


@pytest.mark.parametrize("url", [
    "https://sns.us-east-1.amazonaws.com/SimpleNotificationService-abc.pem",
    "https://sns.eu-west-2.amazonaws.com/SimpleNotificationService-abc.pem",
    "https://sns.cn-north-1.amazonaws.com.cn/SimpleNotificationService-abc.pem",
])
def test_genuine_sns_urls_are_accepted(url):
    assert email_ses.assert_sns_owned_url(url) == url


def test_forged_cert_host_fails_verification_outside_localstack(monkeypatch):
    """End-to-end: a fully-formed message with an attacker cert host is rejected."""
    monkeypatch.setenv("EMAIL_PROVIDER", "aws")
    monkeypatch.delenv("SNS_TOPIC_ARN", raising=False)
    monkeypatch.setenv("FLASK_ENV", "development")

    def _boom(*a, **kw):  # pragma: no cover - must never be reached
        raise AssertionError("attacker-controlled URL was fetched")

    monkeypatch.setattr(email_ses, "_fetch_sns_url", _boom)
    payload = _notification(SigningCertURL="https://evil.s3.amazonaws.com/cert.pem")
    assert email_ses.verify_sns_message(payload) is False


# ── Replay / freshness ────────────────────────────────────────────────────────

def test_stale_message_is_rejected(monkeypatch):
    monkeypatch.setenv("EMAIL_PROVIDER", "localstack")
    monkeypatch.delenv("SNS_TOPIC_ARN", raising=False)
    monkeypatch.setenv("FLASK_ENV", "development")
    monkeypatch.setenv("SNS_MAX_MESSAGE_AGE_SECONDS", "900")
    stale = _notification(Timestamp=_iso(datetime.now(timezone.utc) - timedelta(hours=6)))
    assert email_ses.verify_sns_message(stale) is False


def test_fresh_message_passes_freshness(monkeypatch):
    monkeypatch.setenv("EMAIL_PROVIDER", "localstack")
    monkeypatch.delenv("SNS_TOPIC_ARN", raising=False)
    monkeypatch.setenv("FLASK_ENV", "development")
    assert email_ses.verify_sns_message(_notification()) is True


def test_unparseable_timestamp_is_rejected(monkeypatch):
    monkeypatch.setenv("EMAIL_PROVIDER", "localstack")
    monkeypatch.setenv("FLASK_ENV", "development")
    monkeypatch.delenv("SNS_TOPIC_ARN", raising=False)
    assert email_ses.verify_sns_message(_notification(Timestamp="whenever")) is False


def test_missing_timestamp_is_rejected_in_production(monkeypatch):
    monkeypatch.setenv("EMAIL_PROVIDER", "localstack")
    monkeypatch.setenv("FLASK_ENV", "production")
    monkeypatch.setenv("SNS_TOPIC_ARN", "arn:aws:sns:us-east-1:000000000000:controlhub-ses-events")
    payload = _notification()
    payload.pop("Timestamp")
    assert email_ses.verify_sns_message(payload) is False


# ── Topic binding fails closed ────────────────────────────────────────────────

def test_unset_topic_arn_fails_closed_in_production(monkeypatch):
    """
    Anyone can create an SNS topic and subscribe this endpoint, so a valid AWS
    signature alone proves nothing about origin. With no ARN configured there is
    nothing to bind to, so a deployed environment must refuse.
    """
    monkeypatch.setenv("EMAIL_PROVIDER", "aws")
    monkeypatch.setenv("FLASK_ENV", "production")
    monkeypatch.delenv("SNS_TOPIC_ARN", raising=False)
    assert email_ses.verify_sns_message(_notification()) is False


def test_wrong_topic_arn_is_rejected(monkeypatch):
    monkeypatch.setenv("EMAIL_PROVIDER", "localstack")
    monkeypatch.setenv("FLASK_ENV", "development")
    monkeypatch.setenv("SNS_TOPIC_ARN", "arn:aws:sns:us-east-1:111:expected")
    assert email_ses.verify_sns_message(_notification(TopicArn="arn:aws:sns:us-east-1:999:evil")) is False


def test_localstack_skip_does_not_apply_in_production(monkeypatch):
    """A mis-set EMAIL_PROVIDER must not silently disable signature checking."""
    monkeypatch.setenv("EMAIL_PROVIDER", "localstack")
    monkeypatch.setenv("FLASK_ENV", "production")
    monkeypatch.setenv("SNS_TOPIC_ARN", "arn:aws:sns:us-east-1:000000000000:controlhub-ses-events")

    def _boom(*a, **kw):
        raise AssertionError("should have failed before fetching")

    monkeypatch.setattr(email_ses, "_fetch_sns_url", _boom)
    # Signature is bogus, so verification must fail rather than short-circuit true.
    assert email_ses.verify_sns_message(_notification()) is False


# ── Signature version handling ────────────────────────────────────────────────

def test_unknown_signature_version_is_refused(monkeypatch):
    monkeypatch.setenv("EMAIL_PROVIDER", "aws")
    monkeypatch.setenv("FLASK_ENV", "development")
    monkeypatch.delenv("SNS_TOPIC_ARN", raising=False)

    def _boom(*a, **kw):
        raise AssertionError("fetched a cert for an unsupported signature version")

    monkeypatch.setattr(email_ses, "_fetch_sns_url", _boom)
    assert email_ses.verify_sns_message(_notification(SignatureVersion="99")) is False


def test_sha256_signature_version_is_supported():
    assert set(email_ses._SNS_SIGNATURE_HASHES) == {"1", "2"}


# ── Subscription handshake is not an SSRF primitive ──────────────────────────

@pytest.mark.parametrize("url", [
    "http://169.254.169.254/latest/meta-data/",
    "https://127.0.0.1:8080/admin",
    "https://evil.com/subscribe",
    "https://attacker.s3.amazonaws.com/subscribe",
    "file:///etc/passwd",
])
def test_subscribe_url_must_be_an_sns_host(monkeypatch, url):
    def _boom(*a, **kw):  # pragma: no cover - must never be reached
        raise AssertionError(f"SSRF: fetched {url}")

    monkeypatch.setattr(email_ses, "_fetch_sns_url", _boom)
    assert email_ses.confirm_sns_subscription(url) is False


def test_subscribe_url_on_sns_host_is_confirmed(monkeypatch):
    seen = {}

    def _fake(url):
        seen["url"] = url
        return b"<ConfirmSubscriptionResponse/>"

    monkeypatch.setattr(email_ses, "_fetch_sns_url", _fake)
    url = "https://sns.us-east-1.amazonaws.com/?Action=ConfirmSubscription&Token=t"
    assert email_ses.confirm_sns_subscription(url) is True
    assert seen["url"] == url


def test_confirmation_route_refuses_a_forged_subscribe_url(client, email_env, monkeypatch):
    monkeypatch.setenv("EMAIL_PROVIDER", "aws")  # skip the localstack short-circuit
    monkeypatch.setattr(email_ses, "verify_sns_message", lambda payload: True)
    resp = client.post("/email/webhooks/ses", json={
        "Type": "SubscriptionConfirmation",
        "TopicArn": "arn:aws:sns:us-east-1:000000000000:controlhub-ses-events",
        "SubscribeURL": "https://evil.example.com/steal",
    })
    assert resp.status_code == 400
    assert resp.get_json()["confirmed"] is False


# ── Replay of a legitimate event must not error ──────────────────────────────

def test_replayed_transient_bounce_dedupes_instead_of_500(app, client, email_env):
    sns = {
        "Type": "Notification",
        "TopicArn": "arn:aws:sns:us-east-1:000000000000:controlhub-ses-events",
        "Timestamp": _iso(datetime.now(timezone.utc)),
        "Message": json.dumps({
            "eventType": "Bounce",
            "mail": {"messageId": "replay-me", "destination": ["soft@example.com"]},
            "bounce": {"bounceType": "Transient",
                       "bouncedRecipients": [{"emailAddress": "soft@example.com"}]},
        }),
    }
    first = client.post("/email/webhooks/ses", json=sns)
    assert first.status_code == 200

    second = client.post("/email/webhooks/ses", json=sns)
    assert second.status_code == 200, second.get_data(as_text=True)
    assert second.get_json().get("deduped") is True

    # A transient bounce must never suppress the address.
    from app.services.campaigns import SuppressionService
    with app.app_context():
        assert SuppressionService.is_suppressed("soft@example.com") is False
