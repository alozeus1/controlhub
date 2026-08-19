"""
Operational CLI commands.

These are the scheduled jobs behind the assume-breach controls:

    flask audit verify     # recompute the hash chain, non-zero exit on divergence
    flask audit mirror     # ship sealed rows to the out-of-band sink
    flask secrets rewrap   # migrate stored secrets onto the KMS backend

`audit verify` exits non-zero on tampering specifically so cron/systemd/an
ECS scheduled task can alarm on it. Route that alarm somewhere that is not
ControlHub — an alert the attacker can silence from inside the app they just
compromised is not an alert.
"""
import json
import sys

import click
from flask.cli import AppGroup

audit_cli = AppGroup("audit", help="Audit-log integrity and mirroring.")
secrets_cli = AppGroup("secrets", help="Secret encryption maintenance.")


@audit_cli.command("verify")
@click.option("--start-id", default=0, type=int, help="Verify rows with id greater than this.")
@click.option("--limit", default=None, type=int, help="Stop after this many rows.")
def audit_verify(start_id, limit):
    """Recompute the audit hash chain and report the first divergence."""
    from app.services.audit_chain import verify_chain

    result = verify_chain(start_id=start_id, limit=limit)
    click.echo(json.dumps(result))
    if not result["ok"]:
        click.echo(
            f"AUDIT CHAIN DIVERGENCE at id={result['first_bad_id']}: {result['reason']}",
            err=True,
        )
        sys.exit(2)
    click.echo(f"audit chain OK ({result['checked']} rows verified)")


@audit_cli.command("mirror")
@click.option("--batch-size", default=500, type=int, help="Rows to ship per run.")
def audit_mirror(batch_size):
    """Ship pending audit rows to the configured out-of-band sink."""
    from app.services.audit_sink import mirror_pending, mirror_enabled

    if not mirror_enabled():
        click.echo("AUDIT_MIRROR_SINK is not configured — nothing to do.", err=True)
        sys.exit(1)

    result = mirror_pending(batch_size=batch_size)
    click.echo(json.dumps(result))
    if result["error"]:
        sys.exit(2)


@secrets_cli.command("rewrap")
@click.option("--dry-run", is_flag=True, help="Report what would change without writing.")
def secrets_rewrap(dry_run):
    """
    Re-encrypt stored secrets onto the currently configured backend.

    Reads each value through the existing backend and writes it back through the
    new one, so switching to KMS does not require downtime or a data migration.
    Idempotent — values already on the target backend are skipped.
    """
    from app.extensions import db
    from app.models import Secret, SsoConfig, UserMfa, EnvConfig
    from app.services.secret_crypto import (
        decrypt_secret, encrypt_secret, needs_rewrap, kms_enabled,
    )

    click.echo(f"target backend: {'kms' if kms_enabled() else 'fernet'}")

    # (model, ciphertext attribute, purpose) — purpose must match what the
    # application passes at read time or the rewrapped value becomes unreadable.
    targets = [
        (Secret, "value_encrypted", "vault_secret"),
        (SsoConfig, "client_secret_enc", "sso_client_secret"),
        (UserMfa, "secret_enc", "mfa_totp"),
        (EnvConfig, "value", "env_config"),
    ]

    total, changed, failed = 0, 0, 0
    for model, attr, purpose in targets:
        for row in model.query.all():
            value = getattr(row, attr, None)
            if not value:
                continue
            # EnvConfig stores plaintext for non-secret rows; leave those alone.
            if model is EnvConfig and not getattr(row, "is_secret", False):
                continue
            total += 1
            if not needs_rewrap(value):
                continue
            try:
                plaintext = decrypt_secret(value, purpose=purpose)
            except Exception as exc:
                click.echo(f"  FAILED read {model.__name__}#{row.id}: {exc}", err=True)
                failed += 1
                continue
            if dry_run:
                changed += 1
                continue
            try:
                setattr(row, attr, encrypt_secret(plaintext, purpose=purpose))
                changed += 1
            except Exception as exc:
                click.echo(f"  FAILED write {model.__name__}#{row.id}: {exc}", err=True)
                failed += 1

    if dry_run:
        db.session.rollback()
    else:
        db.session.commit()

    click.echo(json.dumps({"scanned": total, "rewrapped": changed,
                           "failed": failed, "dry_run": bool(dry_run)}))
    if failed:
        sys.exit(2)


def register_cli(app):
    app.cli.add_command(audit_cli)
    app.cli.add_command(secrets_cli)
