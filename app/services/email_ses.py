"""
Amazon SES sending layer (LocalStack in dev, real SES in prod).

Mirrors the provider-toggle pattern in app/storage/s3.py:
- provider == "localstack": talk to the LocalStack endpoint with test creds.
- provider == "aws": use the default boto3 credential chain (env keys on Railway,
  or an IAM role if ever hosted on AWS).

Also holds the SNS notification-signature verification used by the inbound
event webhook, so bounces/complaints can be trusted before we act on them.
"""
import os
import base64
import logging
import re
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from cryptography.hazmat.primitives import hashes

logger = logging.getLogger(__name__)

# Amazon SNS serves signing certificates and confirmation URLs only from
# sns.<region>.amazonaws.com (plus the .com.cn partition). Pinning the whole
# host — not just the suffix — is what stops an attacker-hosted certificate on
# some other *.amazonaws.com service from being accepted.
_SNS_HOST_RE = re.compile(r"^sns\.[a-z0-9-]+\.amazonaws\.com(\.cn)?$")

# SignatureVersion 1 is SHA1, 2 is SHA256. Anything else is refused rather than
# guessed at, so a future/unknown version cannot downgrade verification.
_SNS_SIGNATURE_HASHES = {"1": hashes.SHA1, "2": hashes.SHA256}

_SNS_MAX_FETCH_BYTES = 64 * 1024


def get_ses_config() -> dict:
    return {
        "provider": os.environ.get("EMAIL_PROVIDER", os.environ.get("STORAGE_PROVIDER", "localstack")),
        "region": os.environ.get("AWS_REGION", "us-east-1"),
        "endpoint_url": os.environ.get("AWS_ENDPOINT_URL"),
        "configuration_set": os.environ.get("SES_CONFIGURATION_SET"),
        "from_address": os.environ.get("SES_FROM_ADDRESS", "campaigns@controlhub.local"),
        "from_name": os.environ.get("SES_FROM_NAME", "Web Forx"),
        "sending_enabled": os.environ.get("SES_SENDING_ENABLED", "true").lower() == "true",
    }


def get_transactional_config() -> dict:
    """
    Sender identity for transactional mail (password resets, notifications).

    Kept separate from the campaign identity on purpose: marketing volume and
    transactional delivery should not share a reputation or a configuration set,
    so a campaign complaint spike cannot stop password-reset email going out.
    Falls back to the campaign identity when the transactional vars are unset.
    """
    cfg = get_ses_config()
    return {
        **cfg,
        "from_address": os.environ.get("SES_TRANSACTIONAL_FROM_ADDRESS") or cfg["from_address"],
        "from_name": os.environ.get("SES_TRANSACTIONAL_FROM_NAME") or "Web Forx ControlHub",
        "configuration_set": (
            os.environ.get("SES_TRANSACTIONAL_CONFIGURATION_SET") or cfg["configuration_set"]
        ),
        "reply_to": os.environ.get("SES_REPLY_TO_ADDRESS") or None,
    }


# ─── Sender identity allowlist ────────────────────────────────────────────────

def get_allowed_sender_domains() -> set:
    """
    Domains this deployment is permitted to send as, from
    SES_ALLOWED_SENDER_DOMAINS (comma-separated).

    An empty value means "no local restriction" — SES still rejects unverified
    identities, but the app will not pre-screen. Set it in production so a bad
    SES_FROM_ADDRESS fails loudly here rather than as an opaque SES error.
    """
    raw = os.environ.get("SES_ALLOWED_SENDER_DOMAINS", "")
    return {d.strip().lower().lstrip("@") for d in raw.split(",") if d.strip()}


def sender_domain_allowed(address: str) -> bool:
    """Exact-match the From domain against the allowlist (no implicit subdomains)."""
    allowed = get_allowed_sender_domains()
    if not allowed:
        return True
    domain = (address or "").rsplit("@", 1)[-1].strip().lower()
    return bool(domain) and domain in allowed


def build_ses_client():
    """Build a boto3 SESv2 client honoring the provider toggle."""
    cfg = get_ses_config()
    kwargs = {
        "service_name": "sesv2",
        "region_name": cfg["region"],
        "config": Config(retries={"max_attempts": 3, "mode": "standard"}),
    }
    if cfg["provider"] == "localstack" and cfg["endpoint_url"]:
        kwargs["endpoint_url"] = cfg["endpoint_url"]
        kwargs["aws_access_key_id"] = os.environ.get("AWS_ACCESS_KEY_ID", "test")
        kwargs["aws_secret_access_key"] = os.environ.get("AWS_SECRET_ACCESS_KEY", "test")
    return boto3.client(**kwargs)


def build_ses_v1_client():
    """SESv1 client — used only for verifying identities in LocalStack dev."""
    cfg = get_ses_config()
    kwargs = {"service_name": "ses", "region_name": cfg["region"]}
    if cfg["provider"] == "localstack" and cfg["endpoint_url"]:
        kwargs["endpoint_url"] = cfg["endpoint_url"]
        kwargs["aws_access_key_id"] = os.environ.get("AWS_ACCESS_KEY_ID", "test")
        kwargs["aws_secret_access_key"] = os.environ.get("AWS_SECRET_ACCESS_KEY", "test")
    return boto3.client(**kwargs)


def ensure_identity_verified(email_or_domain: str) -> None:
    """
    Dev helper: in LocalStack, SES will only 'send' from verified identities.
    Idempotent; a no-op failure is logged, not raised.
    """
    cfg = get_ses_config()
    if cfg["provider"] != "localstack":
        return
    try:
        build_ses_v1_client().verify_email_identity(EmailAddress=email_or_domain)
    except Exception as exc:  # pragma: no cover - dev convenience
        logger.warning("LocalStack identity verify skipped for %s: %s", email_or_domain, exc)


class SESResult:
    def __init__(self, message_id: Optional[str], error: Optional[str] = None):
        self.message_id = message_id
        self.error = error

    @property
    def ok(self):
        return self.message_id is not None and self.error is None


def send_email(to_address: str, subject: str, html_body: str,
               from_address: Optional[str] = None, from_name: Optional[str] = None,
               reply_to: Optional[str] = None, headers: Optional[dict] = None,
               text_body: Optional[str] = None,
               configuration_set: Optional[str] = None) -> SESResult:
    """
    Send a single email via SESv2. Attaches the configuration set (so SES emits
    delivery/open/click/bounce events) and List-Unsubscribe headers for
    one-click unsubscribe compliance.

    Returns SESResult(message_id) on success or SESResult(None, error) on failure.
    """
    cfg = get_ses_config()
    from_address = from_address or cfg["from_address"]
    from_name = from_name or cfg["from_name"]
    sender = f"{from_name} <{from_address}>" if from_name else from_address
    config_set = configuration_set or cfg["configuration_set"]

    # Fail before the API call if the sender is outside the verified-domain
    # allowlist — an unverified From is a configuration error, not a send error.
    if not sender_domain_allowed(from_address):
        msg = (f"Sender domain not allowed for {from_address}; "
               f"permitted: {sorted(get_allowed_sender_domains())}")
        logger.error(msg)
        return SESResult(None, f"SenderDomainNotAllowed: {msg}")

    if not cfg["sending_enabled"]:
        logger.info("SES_SENDING_ENABLED=false — dry run, not sending to %s", to_address)
        return SESResult(message_id=f"dryrun-{base64.urlsafe_b64encode(os.urandom(9)).decode()}")

    # LocalStack Community does not implement the SESv2 SendEmail API ("sesv2 not
    # yet implemented / pro feature"), but it DOES implement classic SESv1. Use v1
    # locally so the pipeline is verifiable end to end; production uses SESv2.
    if cfg["provider"] == "localstack":
        return _send_via_ses_v1(to_address, subject, html_body, sender, reply_to,
                                {**cfg, "configuration_set": config_set}, text_body)

    # SESv2 raw headers must be passed via the Content -> Simple -> Headers list.
    header_list = [{"Name": k, "Value": v} for k, v in (headers or {}).items()]

    body = {"Html": {"Data": html_body, "Charset": "UTF-8"}}
    if text_body:
        body["Text"] = {"Data": text_body, "Charset": "UTF-8"}

    request = {
        "FromEmailAddress": sender,
        "Destination": {"ToAddresses": [to_address]},
        "Content": {
            "Simple": {
                "Subject": {"Data": subject, "Charset": "UTF-8"},
                "Body": body,
            }
        },
    }
    if header_list:
        # Not all endpoints (older LocalStack) honor Headers; safe to include.
        request["Content"]["Simple"]["Headers"] = header_list
    if reply_to:
        request["ReplyToAddresses"] = [reply_to]
    if config_set:
        request["ConfigurationSetName"] = config_set

    try:
        client = build_ses_client()
        resp = client.send_email(**request)
        return SESResult(message_id=resp.get("MessageId"))
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code")
        # Retry once without Headers for LocalStack builds that reject them.
        if header_list:
            try:
                request["Content"]["Simple"].pop("Headers", None)
                resp = build_ses_client().send_email(**request)
                return SESResult(message_id=resp.get("MessageId"))
            except Exception as exc2:
                return SESResult(None, f"{code or 'ClientError'}: {exc2}")
        return SESResult(None, f"{code or 'ClientError'}: {exc}")
    except Exception as exc:  # pragma: no cover
        return SESResult(None, str(exc))


def _send_via_ses_v1(to_address, subject, html_body, sender, reply_to, cfg,
                     text_body=None) -> SESResult:
    """Send using the classic SESv1 API (LocalStack-compatible dev path)."""
    try:
        client = build_ses_v1_client()
        body = {"Html": {"Data": html_body, "Charset": "UTF-8"}}
        if text_body:
            body["Text"] = {"Data": text_body, "Charset": "UTF-8"}
        kwargs = {
            "Source": sender,
            "Destination": {"ToAddresses": [to_address]},
            "Message": {
                "Subject": {"Data": subject, "Charset": "UTF-8"},
                "Body": body,
            },
        }
        if reply_to:
            kwargs["ReplyToAddresses"] = [reply_to]
        if cfg.get("configuration_set"):
            kwargs["ConfigurationSetName"] = cfg["configuration_set"]
        resp = client.send_email(**kwargs)
        return SESResult(message_id=resp.get("MessageId"))
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code")
        return SESResult(None, f"{code or 'ClientError'}: {exc}")
    except Exception as exc:  # pragma: no cover
        return SESResult(None, str(exc))


def send_transactional_email(to_address: str, subject: str, html_body: str,
                             text_body: Optional[str] = None,
                             reply_to: Optional[str] = None) -> SESResult:
    """
    Send operational mail (password resets, account notifications) using the
    transactional sender identity and configuration set.

    Same failure contract as send_email(): never raises, returns SESResult.
    """
    cfg = get_transactional_config()
    return send_email(
        to_address=to_address,
        subject=subject,
        html_body=html_body,
        text_body=text_body,
        from_address=cfg["from_address"],
        from_name=cfg["from_name"],
        reply_to=reply_to or cfg["reply_to"],
        configuration_set=cfg["configuration_set"],
    )


def transactional_ses_configured() -> bool:
    """True when this deployment has an explicit SES transactional sender set."""
    return bool(os.environ.get("SES_TRANSACTIONAL_FROM_ADDRESS"))


def get_send_quota() -> dict:
    """Read-only SES quota/health for the dashboard. Never raises."""
    try:
        client = build_ses_client()
        acct = client.get_account()
        return {
            "max_24_hour_send": acct.get("SendQuota", {}).get("Max24HourSend"),
            "sent_last_24_hours": acct.get("SendQuota", {}).get("SentLast24Hours"),
            "max_send_rate": acct.get("SendQuota", {}).get("MaxSendRate"),
            "sending_enabled": acct.get("SendingEnabled", True),
            "production_access": not acct.get("ProductionAccessEnabled", False) is False,
        }
    except Exception as exc:
        logger.info("get_send_quota unavailable: %s", exc)
        return {"available": False, "detail": str(exc)}


# ─── SNS signature verification ───────────────────────────────────────────────

def _is_localstack() -> bool:
    return get_ses_config()["provider"] == "localstack"


def _is_production() -> bool:
    """True when this process believes it is running in a deployed environment."""
    return os.environ.get("FLASK_ENV", "").lower() in ("production", "prod", "staging")


def assert_sns_owned_url(url: str) -> str:
    """
    Validate that `url` points at an Amazon SNS endpoint, or raise ValueError.

    Two payload-supplied URLs are fetched by this service — the signing
    certificate and the subscription-confirmation URL — and both are attacker
    influenced until the signature has been checked. A suffix test such as
    ``host.endswith(".amazonaws.com")`` is not sufficient: an attacker can serve
    arbitrary bytes from ``their-bucket.s3.amazonaws.com``, which would let them
    supply their own signing certificate and forge any SES event. Pin the host
    to the exact SNS service pattern instead, and require TLS so the certificate
    cannot be swapped in transit.
    """
    parsed = urlparse(url or "")
    if parsed.scheme.lower() != "https":
        raise ValueError(f"SNS URL must use https, got {parsed.scheme or '(none)'!r}")
    host = (parsed.hostname or "").lower()
    if not _SNS_HOST_RE.match(host):
        raise ValueError(f"URL host is not an Amazon SNS endpoint: {host!r}")
    return url


def _sns_message_is_fresh(payload: dict) -> bool:
    """
    Reject a signed message older than the configured tolerance.

    A signature proves authenticity, not freshness. Without a timestamp bound, a
    single captured notification stays replayable forever — and the per-event
    uniqueness constraint only de-duplicates events that reach it, so a replay
    can still drive repeated side effects. AWS's own guidance is to bound
    message age; the default here matches their 15-minute recommendation.
    """
    try:
        tolerance = int(os.environ.get("SNS_MAX_MESSAGE_AGE_SECONDS", "900"))
    except ValueError:
        tolerance = 900
    if tolerance <= 0:
        return True

    raw = payload.get("Timestamp")
    if not raw:
        # A Notification without a Timestamp cannot be bounded. AWS always sends
        # one, so treat its absence as hostile in deployed environments.
        return not _is_production()
    try:
        stamp = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        logger.warning("SNS message has an unparseable Timestamp: %r", raw)
        return False
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    age = abs((datetime.now(timezone.utc) - stamp).total_seconds())
    if age > tolerance:
        logger.warning("Rejected SNS message %.0fs old (tolerance %ss)", age, tolerance)
        return False
    return True


def verify_sns_message(payload: dict) -> bool:
    """
    Verify an inbound SNS message: topic, freshness, then signature.

    In dev/LocalStack there are no real signing certs, so cryptographic
    verification is skipped — but only outside a deployed environment, so a
    mis-set ``EMAIL_PROVIDER`` in production cannot silently disable the check.
    """
    expected_topic = os.environ.get("SNS_TOPIC_ARN")
    topic = payload.get("TopicArn")
    if expected_topic:
        if topic != expected_topic:
            logger.warning("SNS TopicArn mismatch: %s", topic)
            return False
    elif _is_production():
        # Fail closed. Anyone can create an SNS topic and point it at this
        # endpoint, so a valid AWS signature alone does not mean the event came
        # from *our* topic. Without the ARN configured there is nothing to bind
        # the message to, so refuse rather than accept the world's SNS traffic.
        logger.error("SNS_TOPIC_ARN is not configured; refusing inbound SNS message")
        return False

    if not _sns_message_is_fresh(payload):
        return False

    if _is_localstack() and not _is_production():
        return True

    try:
        version = str(payload.get("SignatureVersion", "1"))
        if version not in _SNS_SIGNATURE_HASHES:
            logger.warning("Unsupported SNS SignatureVersion: %r", version)
            return False

        from cryptography.x509 import load_pem_x509_certificate
        from cryptography.hazmat.primitives.asymmetric import padding

        cert_url = assert_sns_owned_url(payload.get("SigningCertURL", ""))
        pem = _fetch_sns_url(cert_url)
        cert = load_pem_x509_certificate(pem)
        signing_string = _sns_signing_string(payload).encode("utf-8")
        signature = base64.b64decode(payload["Signature"])
        cert.public_key().verify(
            signature,
            signing_string,
            padding.PKCS1v15(),
            _SNS_SIGNATURE_HASHES[version](),
        )
        return True
    except Exception as exc:
        logger.warning("SNS signature verification failed: %s", exc)
        return False


def confirm_sns_subscription(subscribe_url: str) -> bool:
    """
    Complete the SNS subscription handshake by fetching the SubscribeURL.

    The URL arrives in the request body, so it is validated against the SNS host
    pattern before any request is made and redirects are refused — otherwise the
    handshake is a server-side request forgery primitive pointed at whatever the
    caller supplies.
    """
    try:
        url = assert_sns_owned_url(subscribe_url)
    except ValueError as exc:
        logger.warning("Refused SNS SubscribeURL: %s", exc)
        return False
    try:
        _fetch_sns_url(url)
        return True
    except Exception as exc:
        logger.warning("SNS subscription confirmation failed: %s", exc)
        return False


def _fetch_sns_url(url: str) -> bytes:
    """
    Fetch an already-validated SNS URL with no redirect following.

    Redirects are refused rather than re-validated: a 302 from an SNS host to an
    attacker host would otherwise defeat the host pin, and neither the signing
    certificate nor the confirmation endpoint legitimately redirects.
    """
    import requests

    resp = requests.get(url, timeout=5, allow_redirects=False)
    if resp.status_code >= 300:
        raise ValueError(f"SNS URL returned {resp.status_code} (redirects are not followed)")
    return resp.content[:_SNS_MAX_FETCH_BYTES]


def _sns_signing_string(payload: dict) -> str:
    """Build the canonical string SNS signs (Signature Version 1)."""
    if payload.get("Type") == "Notification":
        keys = ["Message", "MessageId", "Subject", "Timestamp", "TopicArn", "Type"]
    else:  # SubscriptionConfirmation / UnsubscribeConfirmation
        keys = ["Message", "MessageId", "SubscribeURL", "Timestamp", "Token", "TopicArn", "Type"]
    parts = []
    for k in keys:
        if k in payload and payload[k] is not None:
            parts.append(k)
            parts.append(str(payload[k]))
    return "\n".join(parts) + "\n"
