"""Encrypt existing EnvConfig secret values at rest (audit A-7).

Backfills legacy plaintext values for rows where is_secret is true, wrapping
them with the application's Fernet encryption ('fernet:v1:' sentinel). The
operation is idempotent: rows already carrying the sentinel are skipped, so the
migration is safe to re-run and safe to run after new code has begun writing
encrypted values.

No schema change — the `value` column already stores text; only its contents
are transformed for secret rows. Non-secret rows are left untouched.

Revision ID: w3x4y5z6a7b8
Revises: v2w3x4y5z6a7
"""
from alembic import op
import sqlalchemy as sa

revision = "w3x4y5z6a7b8"
down_revision = "v2w3x4y5z6a7"
branch_labels = None
depends_on = None


def _encrypt(plaintext: str) -> str:
    # Import inside the function so the migration works within the Flask-Migrate
    # app context (SECRET_ENCRYPTION_KEYS / SECRET_KEY are available there).
    from app.services.secret_crypto import encrypt_secret
    return encrypt_secret(plaintext)


def upgrade():
    conn = op.get_bind()
    rows = conn.execute(
        sa.text("SELECT id, value FROM env_config WHERE is_secret = true AND value IS NOT NULL")
    ).fetchall()
    for row in rows:
        value = row[1]
        if value is None or (isinstance(value, str) and value.startswith("fernet:v1:")):
            continue  # already encrypted / nothing to do
        conn.execute(
            sa.text("UPDATE env_config SET value = :v WHERE id = :id"),
            {"v": _encrypt(value), "id": row[0]},
        )


def downgrade():
    # Decrypt back to plaintext so the schema is symmetric. Only affects rows
    # carrying the sentinel; anything else is left as-is.
    from app.services.secret_crypto import decrypt_secret
    conn = op.get_bind()
    rows = conn.execute(
        sa.text("SELECT id, value FROM env_config WHERE is_secret = true AND value IS NOT NULL")
    ).fetchall()
    for row in rows:
        value = row[1]
        if isinstance(value, str) and value.startswith("fernet:v1:"):
            try:
                conn.execute(
                    sa.text("UPDATE env_config SET value = :v WHERE id = :id"),
                    {"v": decrypt_secret(value), "id": row[0]},
                )
            except Exception:
                # Leave undecryptable rows untouched rather than lose data.
                continue
