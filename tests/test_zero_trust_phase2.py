"""
Zero-trust Phase 2: KMS envelope encryption for secrets, and the out-of-band
audit mirror.

The KMS tests drive a fake client that reproduces the properties we actually
depend on: a data key that is only recoverable through Decrypt, and an
encryption context that must match exactly.
"""
import base64
import json

import pytest

from app.extensions import db
from app.models import AuditLog, SystemState
from app.services import audit_sink, secret_crypto


class FakeKMS:
    """
    Stand-in for AWS KMS.

    Wraps the data key with a reversible encoding that embeds the encryption
    context, so a context mismatch raises exactly as the real service would —
    that behavior is the cross-domain replay defense under test.
    """

    class _NotAuthorized(Exception):
        pass

    def __init__(self):
        self.decrypt_calls = 0
        self.generate_calls = 0

    def generate_data_key(self, KeyId, KeySpec, EncryptionContext):
        self.generate_calls += 1
        # Deterministic per-call key material is fine for a test double.
        raw = (f"{KeyId}:{self.generate_calls}".encode() + b"\x00" * 32)[:32]
        blob = json.dumps({"ctx": EncryptionContext,
                           "k": base64.b64encode(raw).decode()}).encode()
        return {"Plaintext": raw, "CiphertextBlob": blob}

    def decrypt(self, CiphertextBlob, EncryptionContext):
        self.decrypt_calls += 1
        payload = json.loads(CiphertextBlob.decode())
        if payload["ctx"] != EncryptionContext:
            raise self._NotAuthorized("InvalidCiphertextException: context mismatch")
        return {"Plaintext": base64.b64decode(payload["k"])}


@pytest.fixture
def kms(app, monkeypatch):
    """App configured to use the KMS backend with a fake client."""
    fake = FakeKMS()
    monkeypatch.setenv("SECRET_KMS_KEY_ID", "alias/controlhub-secrets")
    app.config["SECRET_KMS_KEY_ID"] = "alias/controlhub-secrets"
    monkeypatch.setattr(secret_crypto, "build_kms_client", lambda: fake)
    return fake


# ─── KMS envelope encryption ──────────────────────────────────────────────────

def test_kms_roundtrip(app, kms):
    ct = secret_crypto.encrypt_secret("hunter2", purpose="vault_secret")
    assert ct.startswith("kms:v1:")
    assert "hunter2" not in ct
    assert secret_crypto.decrypt_secret(ct, purpose="vault_secret") == "hunter2"


def test_plaintext_data_key_is_not_persisted(app, kms):
    """Only the KMS-wrapped data key may appear in the stored ciphertext."""
    ct = secret_crypto.encrypt_secret("topsecret", purpose="vault_secret")
    wrapped = ct[len("kms:v1:"):].split(":", 1)[0]
    blob = json.loads(base64.b64decode(wrapped).decode())
    # The fake stores the key inside the blob, mirroring how KMS holds it
    # server-side; what matters is that reading it back requires a Decrypt call.
    assert kms.decrypt_calls == 0
    secret_crypto.decrypt_secret(ct, purpose="vault_secret")
    assert kms.decrypt_calls == 1
    assert blob["ctx"]["purpose"] == "vault_secret"


def test_every_write_mints_a_fresh_data_key(app, kms):
    secret_crypto.encrypt_secret("a", purpose="vault_secret")
    secret_crypto.encrypt_secret("a", purpose="vault_secret")
    assert kms.generate_calls == 2


def test_ciphertext_cannot_be_read_under_a_different_purpose(app, kms):
    """
    An SSO client-secret blob moved into a Secret row must not decrypt.

    This is the property the encryption context buys: KMS refuses rather than
    returning plaintext to the wrong code path.
    """
    ct = secret_crypto.encrypt_secret("sso-client-secret", purpose="sso_client_secret")
    with pytest.raises(ValueError):
        secret_crypto.decrypt_secret(ct, purpose="vault_secret")


def test_malformed_kms_ciphertext_is_rejected(app, kms):
    with pytest.raises(ValueError):
        secret_crypto.decrypt_secret("kms:v1:garbage", purpose="vault_secret")


# ─── Backwards compatibility ──────────────────────────────────────────────────

def test_fernet_values_still_decrypt_after_switching_to_kms(app, monkeypatch):
    """Existing rows must keep working the moment KMS is switched on."""
    legacy = secret_crypto.encrypt_secret("old-value", purpose="vault_secret")
    assert legacy.startswith("fernet:v1:")

    fake = FakeKMS()
    monkeypatch.setenv("SECRET_KMS_KEY_ID", "alias/k")
    app.config["SECRET_KMS_KEY_ID"] = "alias/k"
    monkeypatch.setattr(secret_crypto, "build_kms_client", lambda: fake)

    assert secret_crypto.decrypt_secret(legacy, purpose="vault_secret") == "old-value"
    assert fake.decrypt_calls == 0, "legacy values must not hit KMS"


def test_fernet_is_used_when_no_kms_key_configured(app, monkeypatch):
    monkeypatch.delenv("SECRET_KMS_KEY_ID", raising=False)
    app.config["SECRET_KMS_KEY_ID"] = ""
    assert secret_crypto.encrypt_secret("x").startswith("fernet:v1:")


def test_needs_rewrap_flags_fernet_values_when_kms_active(app, kms):
    fernet_value = "fernet:v1:abc"
    kms_value = "kms:v1:abc:def"
    assert secret_crypto.needs_rewrap(fernet_value) is True
    assert secret_crypto.needs_rewrap(kms_value) is False


def test_is_encrypted_recognises_all_backends(app):
    assert secret_crypto.is_encrypted("fernet:v1:x") is True
    assert secret_crypto.is_encrypted("kms:v1:a:b") is True
    assert secret_crypto.is_encrypted("enc:x") is True
    assert secret_crypto.is_encrypted("plaintext") is False
    assert secret_crypto.is_encrypted(None) is False


def test_env_config_does_not_double_encrypt_under_kms(app, kms, create_user):
    """
    Regression guard: the EnvConfig flush hook used to test only for the
    'fernet:v1:' prefix, so a KMS value looked like plaintext and was
    re-encrypted on every update until it was unreadable.
    """
    from app.models import EnvConfig

    owner = create_user("envcfg@x.com")
    row = EnvConfig(project_id=1, environment="prod", key="API_KEY",
                    value="s3cret", is_secret=True, created_by_id=owner.id)
    db.session.add(row)
    db.session.commit()

    first = row.value
    assert first.startswith("kms:v1:")

    row.description = "touch"
    db.session.commit()

    assert row.value == first, "value was re-encrypted on update"
    assert row.decrypted_value == "s3cret"


# ─── Audit mirror ─────────────────────────────────────────────────────────────

def _write_audit(n):
    from app.utils.audit import log_action
    for i in range(n):
        log_action(action=f"mirror.test.{i}", target_type="test", target_label=str(i))


def test_mirror_disabled_by_default(app, monkeypatch):
    monkeypatch.delenv("AUDIT_MIRROR_SINK", raising=False)
    assert audit_sink.mirror_enabled() is False
    result = audit_sink.mirror_pending()
    assert result["shipped"] == 0


def test_mirror_ships_rows_to_file_sink(app, monkeypatch, tmp_path):
    target = tmp_path / "mirror.jsonl"
    monkeypatch.setenv("AUDIT_MIRROR_SINK", "file")
    monkeypatch.setenv("AUDIT_MIRROR_FILE", str(target))
    _write_audit(3)

    result = audit_sink.mirror_pending()
    assert result["shipped"] == 3
    assert result["error"] is None

    lines = target.read_text().strip().splitlines()
    assert len(lines) == 3
    # Chain hashes must travel with the record, or the mirror is not evidence.
    first = json.loads(lines[0])
    assert first["row_hash"] and first["prev_hash"]


def test_mirror_is_incremental(app, monkeypatch, tmp_path):
    target = tmp_path / "mirror.jsonl"
    monkeypatch.setenv("AUDIT_MIRROR_SINK", "file")
    monkeypatch.setenv("AUDIT_MIRROR_FILE", str(target))

    _write_audit(2)
    assert audit_sink.mirror_pending()["shipped"] == 2
    assert audit_sink.mirror_pending()["shipped"] == 0, "already-shipped rows resent"

    _write_audit(1)
    assert audit_sink.mirror_pending()["shipped"] == 1
    assert len(target.read_text().strip().splitlines()) == 3


def test_high_water_does_not_advance_when_the_sink_fails(app, monkeypatch, tmp_path):
    """
    A sink outage must cause replay, never a silent gap in the mirror.
    """
    monkeypatch.setenv("AUDIT_MIRROR_SINK", "file")
    _write_audit(2)

    def _explode(_lines):
        raise IOError("sink unreachable")

    monkeypatch.setitem(audit_sink.SINKS, "file", _explode)
    failed = audit_sink.mirror_pending()
    assert failed["shipped"] == 0
    assert failed["error"]
    assert audit_sink.get_high_water() == 0

    # Recovery ships everything that was pending.
    target = tmp_path / "mirror.jsonl"
    monkeypatch.setenv("AUDIT_MIRROR_FILE", str(target))
    monkeypatch.setitem(audit_sink.SINKS, "file", audit_sink._ship_file)
    assert audit_sink.mirror_pending()["shipped"] == 2


def test_unknown_sink_is_reported_not_silently_skipped(app, monkeypatch):
    monkeypatch.setenv("AUDIT_MIRROR_SINK", "nonsense")
    result = audit_sink.mirror_pending()
    assert result["error"] and "unknown" in result["error"]


def test_high_water_survives_as_a_row(app, monkeypatch, tmp_path):
    monkeypatch.setenv("AUDIT_MIRROR_SINK", "file")
    monkeypatch.setenv("AUDIT_MIRROR_FILE", str(tmp_path / "m.jsonl"))
    _write_audit(2)
    audit_sink.mirror_pending()

    row = SystemState.query.filter_by(key=audit_sink.MARK_KEY).first()
    assert row is not None
    assert int(row.value) == AuditLog.query.order_by(AuditLog.id.desc()).first().id
