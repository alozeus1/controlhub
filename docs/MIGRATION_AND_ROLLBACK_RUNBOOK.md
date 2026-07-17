# Migration & Rollback Runbook

Database: PostgreSQL. Migrations: Alembic via Flask-Migrate. Current head:
`v2w3x4y5z6a7`.

> **Rule:** the `web`/`release` process owns schema changes (`flask db upgrade`).
> Workers never run migrations. Web and worker deploy from the same image/commit.

## Standard upgrade

1. **Back up first** (see `BACKUP_AND_RESTORE_RUNBOOK.md`) — take a snapshot and
   confirm it succeeded before applying migrations.
2. Deploy the new image. The release step runs `flask db upgrade`.
3. Validate:
   ```
   flask db current      # should equal the new head
   flask db heads         # must be exactly ONE head
   python scripts/check_migration_drift.py   # models == schema, exit 0
   curl -fsS $URL/readyz  # DB + Redis healthy
   ```
4. Smoke-test the critical flows (login, workflows, approvals, email send).

CI validates this exact path on a real Postgres service (`backend-postgres` job)
on every PR — a broken migration fails the build before it can ship.

## Rollback

Alembic downgrades exist but **data migrations are not always reversible**.
Preferred rollback order:

1. **App rollback:** redeploy the previous image. If the new migration is
   backward-compatible (additive columns/tables — the pattern used here), the
   old code runs against the new schema safely. This is the fast path.
2. **Schema downgrade (only if required and known-safe):**
   `flask db downgrade -1`. Do NOT downgrade across a migration that dropped or
   transformed data — restore from backup instead.
3. **Restore from backup** (last resort, data-loss window = time since snapshot):
   see `BACKUP_AND_RESTORE_RUNBOOK.md`.

## Irreversible / data migrations

- Ship destructive changes in **two phases**: (a) additive migration + dual-write
  code, deploy, backfill; (b) later migration removing the old column once no
  code reads it. Never drop-and-recreate in a single release.
- Guard long backfills to run in bounded batches; make them idempotent and
  re-runnable (the existing `backfill_missing_model_columns` migration is a good
  template — it checks existing columns before adding).

## Git history purge — `code.zip` (destructive; operator-run only)

`code.zip` was removed from the working tree (`git rm --cached`) and ignored, but
it **remains in history** at commit `8cd13a9` and **embeds a `.env`**. Treat all
secrets in that `.env` (`SECRET_KEY`, `JWT_SECRET_KEY`, DB credentials, any AWS
keys) as **compromised**.

**Impact assessment:** rewriting history changes every commit SHA after the first
introduction of the blob; all branches/tags that contain it are affected; every
collaborator must re-clone or hard-reset. Open PRs will need rebasing.

**Procedure (run by a human, with team coordination):**
```
# 0. Announce a freeze; ensure everyone has pushed.
# 1. Full backup of the remote (mirror clone).
git clone --mirror git@host:org/controlhub.git controlhub-backup.git

# 2. Purge the blob (git-filter-repo preferred over BFG).
pip install git-filter-repo
git filter-repo --path code.zip --invert-paths

# 3. Verify it's gone from history.
git log --all --oneline -- code.zip   # must be empty
git rev-list --objects --all | grep code.zip   # must be empty

# 4. Rotate ALL secrets that were in the embedded .env BEFORE force-pushing:
#    - regenerate SECRET_KEY, JWT_SECRET_KEY (invalidates existing sessions)
#    - rotate DB credentials
#    - rotate/rekey any AWS/SES keys
#    - update the secret store (Railway/host), NOT the repo

# 5. Coordinated force-push.
git push --force --all
git push --force --tags

# 6. Every developer re-clones (or: git fetch && git reset --hard origin/main).
```
**Rollback for the purge:** if anything goes wrong, restore from the mirror
backup (`controlhub-backup.git`) and re-push.

Going forward, `scripts/check_large_files.py` + the CI `secret-scan` (gitleaks)
and `repo-policy` gates block re-introduction of archives/large blobs.
