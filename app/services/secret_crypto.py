"""
Secret encryption helpers.

Two backends, selected by whether SECRET_KMS_KEY_ID is configured:

* **Fernet** (legacy/dev) — keys come from SECRET_ENCRYPTION_KEYS. Simple, but the
  key sits in the same process environment as the ciphertext's database
  credentials, so an attacker inside the API holds both halves. Adequate for
  local development; not a control against an assume-breach adversary.

* **KMS envelope** (production) — a data key is minted per write via
  kms:GenerateDataKey, used once with Fernet, and stored alongside the ciphertext
  in its KMS-encrypted form. The application never holds a master key, so reading
  a secret requires a live kms:Decrypt call that AWS logs to CloudTrail and IAM
  can gate. That out-of-band, attacker-inaccessible record is the point.

Every ciphertext is self-describing (`fernet:v1:` / `kms:v1:`), so both formats
coexist and existing rows keep decrypting after the switch. Use
`flask secrets rewrap` to migrate stored values onto KMS.

Encryption context
------------------
KMS binds each ciphertext to an encryption context that must match exactly on
decrypt. We scope it by *purpose* ("sso_client_secret", "mfa_totp", ...), so an
SSO client-secret blob cannot be moved into a Secret row and read back through a
different code path.

This is domain binding, not per-row binding. Per-row would be stronger, but
`encrypt_secret` is called during row construction — before an id exists — so a
row-scoped context could not be reproduced at decrypt time for newly created
records. Getting that wrong makes secrets permanently unreadable, so the
narrower, reliably reproducible scope is the right trade.
"""
from __future__ import annotations

import base64
import hashlib
import os
from typing import List, Optional

from cryptography.fernet import Fernet, MultiFernet, InvalidToken
from flask import current_app

FERNET_PREFIX = "fernet:v1:"
KMS_PREFIX = "kms:v1:"
LEGACY_PREFIX = "enc:"

DEFAULT_PURPOSE = "controlhub_secret"


# ─── Fernet backend ───────────────────────────────────────────────────────────

def _derive_dev_key() -> str:
    """
    Derive a deterministic dev key from SECRET_KEY when explicit keys are missing.
    This fallback is only intended for local development/testing.
    """
    secret_key = (current_app.config.get("SECRET_KEY") or "dev-secret-key-not-for-production").encode()
    digest = hashlib.sha256(secret_key).digest()
    return base64.urlsafe_b64encode(digest).decode()


def _configured_keys() -> List[str]:
    keys_raw = current_app.config.get("SECRET_ENCRYPTION_KEYS", "") or ""
    keys = [k.strip() for k in keys_raw.split(",") if k.strip()]
    if keys:
        return keys
    return [_derive_dev_key()]


def _cipher() -> MultiFernet:
    keys = _configured_keys()
    fernets = [Fernet(k.encode() if isinstance(k, str) else k) for k in keys]
    return MultiFernet(fernets)


# ─── KMS backend ──────────────────────────────────────────────────────────────

def kms_key_id() -> Optional[str]:
    """Configured CMK, or None when the Fernet backend should be used."""
    try:
        configured = current_app.config.get("SECRET_KMS_KEY_ID")
    except RuntimeError:  # outside an app context (e.g. migrations)
        configured = None
    return (configured or os.environ.get("SECRET_KMS_KEY_ID") or "").strip() or None


def kms_enabled() -> bool:
    return kms_key_id() is not None


def build_kms_client():
    """
    Build a boto3 KMS client, honoring the same provider toggle as storage/SES:
    LocalStack in dev via AWS_ENDPOINT_URL, the default credential chain in prod.
    """
    import boto3
    from botocore.config import Config as BotoConfig

    provider = os.environ.get("SECRET_KMS_PROVIDER") or os.environ.get(
        "STORAGE_PROVIDER", "localstack"
    )
    kwargs = {
        "service_name": "kms",
        "region_name": os.environ.get("AWS_REGION", "us-east-1"),
        "config": BotoConfig(retries={"max_attempts": 3, "mode": "standard"}),
    }
    endpoint = os.environ.get("AWS_ENDPOINT_URL")
    if provider == "localstack" and endpoint:
        kwargs["endpoint_url"] = endpoint
        kwargs["aws_access_key_id"] = os.environ.get("AWS_ACCESS_KEY_ID", "test")
        kwargs["aws_secret_access_key"] = os.environ.get("AWS_SECRET_ACCESS_KEY", "test")
    return boto3.client(**kwargs)


def _encryption_context(purpose: Optional[str]) -> dict:
    return {"purpose": purpose or DEFAULT_PURPOSE, "app": "controlhub"}


def _kms_encrypt(plaintext: str, purpose: Optional[str]) -> str:
    """
    Envelope-encrypt with a single-use data key.

    The plaintext data key is used once and dropped; only its KMS-encrypted form
    is persisted, so recovering the secret always costs a kms:Decrypt call.
    """
    client = build_kms_client()
    resp = client.generate_data_key(
        KeyId=kms_key_id(),
        KeySpec="AES_256",
        EncryptionContext=_encryption_context(purpose),
    )
    data_key = base64.urlsafe_b64encode(resp["Plaintext"])
    wrapped = base64.b64encode(resp["CiphertextBlob"]).decode("ascii")
    token = Fernet(data_key).encrypt(plaintext.encode("utf-8")).decode("utf-8")
    return f"{KMS_PREFIX}{wrapped}:{token}"


def _kms_decrypt(ciphertext: str, purpose: Optional[str]) -> str:
    body = ciphertext[len(KMS_PREFIX):]
    wrapped, _, token = body.partition(":")
    if not wrapped or not token:
        raise ValueError("Malformed KMS secret ciphertext")

    client = build_kms_client()
    try:
        resp = client.decrypt(
            CiphertextBlob=base64.b64decode(wrapped),
            EncryptionContext=_encryption_context(purpose),
        )
    except Exception as exc:
        # A context mismatch lands here: KMS refuses rather than returning the
        # wrong plaintext, which is exactly the cross-domain replay defense.
        raise ValueError("Unable to decrypt secret value") from exc

    data_key = base64.urlsafe_b64encode(resp["Plaintext"])
    try:
        return Fernet(data_key).decrypt(token.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("Unable to decrypt secret value") from exc


# ─── Public API ───────────────────────────────────────────────────────────────

def encrypt_secret(plaintext: str, purpose: str = None) -> str:
    """
    Encrypt a secret for storage.

    Uses KMS envelope encryption when SECRET_KMS_KEY_ID is set, else Fernet.
    `purpose` scopes the KMS encryption context; pass the same value to
    decrypt_secret or the read will fail.
    """
    if plaintext is None:
        raise ValueError("Secret value cannot be null")

    if kms_enabled():
        return _kms_encrypt(plaintext, purpose)

    token = _cipher().encrypt(plaintext.encode("utf-8")).decode("utf-8")
    return f"{FERNET_PREFIX}{token}"


def decrypt_secret(ciphertext: str, purpose: str = None) -> str:
    """
    Decrypt a stored secret.

    Dispatches on the ciphertext's own prefix, so KMS and Fernet records coexist
    and pre-KMS rows keep working after the backend is switched on.
    """
    if not ciphertext:
        return ""

    if ciphertext.startswith(LEGACY_PREFIX):
        return base64.b64decode(ciphertext[len(LEGACY_PREFIX):]).decode("utf-8")

    if ciphertext.startswith(KMS_PREFIX):
        return _kms_decrypt(ciphertext, purpose)

    if not ciphertext.startswith(FERNET_PREFIX):
        raise ValueError("Unsupported secret ciphertext format")

    token = ciphertext[len(FERNET_PREFIX):]
    try:
        raw = _cipher().decrypt(token.encode("utf-8"))
    except InvalidToken as exc:
        raise ValueError("Unable to decrypt secret value") from exc
    return raw.decode("utf-8")


def is_encrypted(value: str) -> bool:
    """
    True if a stored value already carries one of our ciphertext sentinels.

    Callers must use this rather than testing for a single prefix — a hardcoded
    'fernet:v1:' check silently re-encrypts KMS values on every update and hands
    raw ciphertext back on read once the backend changes.
    """
    return bool(value) and isinstance(value, str) and value.startswith(
        (FERNET_PREFIX, KMS_PREFIX, LEGACY_PREFIX)
    )


def needs_rewrap(ciphertext: str) -> bool:
    """True when a stored value is not on the currently configured backend."""
    if not ciphertext:
        return False
    if kms_enabled():
        return not ciphertext.startswith(KMS_PREFIX)
    return ciphertext.startswith(LEGACY_PREFIX)
