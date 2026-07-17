# Backup & Restore Runbook

Covers the PostgreSQL database (system of record) and Redis (ephemeral —
sessions/blocklist/queue; not backed up, treated as reconstructible).

## Objectives (proposed — confirm with the business)

| Metric | Target |
|---|---|
| RPO (max data loss) | ≤ 15 min (via PITR / frequent snapshots) |
| RTO (max downtime to restore) | ≤ 1 hour |
| Backup retention | 7 daily, 4 weekly, 12 monthly |
| Restore test cadence | Monthly (restore to a scratch DB + smoke test) |

## Backups

- **Managed Postgres (Neon/Railway/RDS):** enable automated daily snapshots +
  point-in-time recovery (WAL). This is the primary mechanism — configure in the
  provider console; capture the schedule + retention there.
- **Logical backup (portable, off-provider):** nightly
  ```
  pg_dump --format=custom --no-owner "$DATABASE_URL" > controlhub-$(date +%F).dump
  ```
  Encrypt at rest (KMS/age) and store in object storage with restricted access.
  Do **not** commit dumps to git (blocked by `.gitignore` + CI `repo-policy`).
- Encryption: at rest (provider KMS) and in transit (`sslmode=require`).
- Access control: backups readable only by the ops role; audit access.

## Restore

1. Provision a fresh Postgres instance (or a scratch DB for a test restore).
2. Restore:
   ```
   pg_restore --clean --no-owner --dbname "$TARGET_DATABASE_URL" controlhub-YYYY-MM-DD.dump
   # or provider PITR to a chosen timestamp
   ```
3. Point the app at the restored DB, run `flask db current` (confirm head), then
   `python scripts/check_migration_drift.py`.
4. `curl -fsS $URL/readyz` and run the smoke suite (login, workflows, approvals,
   email send, audit write).
5. Redis is rebuilt automatically: sessions require re-login; the blocklist is
   empty (acceptable — fail-closed policy means unverifiable tokens are already
   denied); re-enqueue any in-flight campaigns if needed.

## Restore test (monthly, non-prod)

Automate a scheduled job that restores the latest dump to a scratch DB, runs the
drift check + a read-only smoke test, and alerts on failure. A backup that has
never been restored is not a backup.

## Legal hold / retention interaction

- Audit-log retention (P2-9, backlog) must exclude records under legal hold.
- Subscriber/people deletion requests (GDPR) must still preserve unsubscribe
  suppression (a suppressed email is retained as a hash to honor opt-out).
