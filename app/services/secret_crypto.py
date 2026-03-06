"""
Secret encryption helpers.

Uses Fernet/MultiFernet for authenticated encryption at rest.
Encryption keys are sourced from SECRET_ENCRYPTION_KEYS (comma-separated Fernet keys).
"""
from __future__ import annotations

import base64
import hashlib
from typing import List

from cryptography.fernet import Fernet, MultiFernet, InvalidToken
from flask import current_app


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


def encrypt_secret(plaintext: str) -> str:
    if plaintext is None:
        raise ValueError("Secret value cannot be null")
    token = _cipher().encrypt(plaintext.encode("utf-8")).decode("utf-8")
    return f"fernet:v1:{token}"


def decrypt_secret(ciphertext: str) -> str:
    """
    Decrypt stored secret values.
    Supports legacy 'enc:' records so old data remains readable.
    """
    if not ciphertext:
        return ""

    if ciphertext.startswith("enc:"):
        raw = base64.b64decode(ciphertext[4:])
        return raw.decode("utf-8")

    if not ciphertext.startswith("fernet:v1:"):
        raise ValueError("Unsupported secret ciphertext format")

    token = ciphertext[len("fernet:v1:"):]
    try:
        raw = _cipher().decrypt(token.encode("utf-8"))
    except InvalidToken as exc:
        raise ValueError("Unable to decrypt secret value") from exc
    return raw.decode("utf-8")

