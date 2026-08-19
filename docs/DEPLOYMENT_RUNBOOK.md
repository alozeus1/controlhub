# Deployment Runbook

## Topology

- **Frontend (admin-ui):** static Vite build on a CDN/host (e.g. Vercel).
- **API (Flask + gunicorn):** container on Railway (or ECS/Fly). Runs migrations
  on release, then serves via gunicorn (non-root, healthchecked).
- **Worker (RQ):** SEPARATE service, same image/commit, runs `rq worker`.
- **PostgreSQL:** managed (Neon/Railway/RDS).
- **Redis:** managed (Upstash/Railway) — sessions, JWT blocklist, RQ queue.
- **Amazon SES + SNS:** email delivery + events. **n8n:** orchestration.

## Processes (`Procfile`)

| Process | Command |
|---|---|
| `web` | `flask db upgrade && gunicorn wsgi:app -b 0.0.0.0:$PORT --workers 4 --timeout 120` |
| `worker` | `rq worker --url $REDIS_URL --with-scheduler $CAMPAIGN_QUEUE default` |
| `release` | `flask db upgrade` |

Web and worker MUST use the same image/commit. Scale workers horizontally by
running more `worker` instances.

## Required environment (production)

Set in the platform secret store — **never** in git. See `.env.example` for the
full annotated list. Mandatory:

- `ENVIRONMENT=production`
- `SECRET_KEY`, `JWT_SECRET_KEY` (≥ 32 bytes each), `SECRET_ENCRYPTION_KEYS`
- `SQLALCHEMY_DATABASE_URI` (Postgres, `sslmode=require`), `REDIS_URL`
- `CORS_ORIGINS` (exact SPA origins; no `*`)
- `JWT_FAIL_OPEN=false` (fail-closed revocation — the secure default)
- Email: `EMAIL_PROVIDER=aws`, `SES_FROM_ADDRESS`, `SES_CONFIGURATION_SET`,
  `SNS_TOPIC_ARN`, `AWS_*` (scoped SES key)
- SSO (if used): configured via the admin UI (encrypted at rest)

Config self-validates on boot (`config.py::validate`): missing prod secrets,
weak keys (<32 bytes), or `*` in CORS aborts startup.

## Deploy sequence

1. CI green on all mandatory gates (see `RELEASE_CHECKLIST.md`).
2. Back up the DB.
3. Deploy API image → release step runs migrations.
4. Deploy worker (same image).
5. Deploy frontend build.
6. Verify: `/healthz` (liveness) 200, `/readyz` (DB+Redis) 200, smoke flows.
7. Watch error rate / logs for 15 min.

## Zero-trust AWS infrastructure (Phase 5)

`infra/terraform/` provisions the AWS side: the secrets CMK, the audit mirror log group,
split API/worker IAM identities, SES configuration sets, and the security alarms. It also
creates the two things the steps below say you must supply.

```bash
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars   # set alert_email
terraform init && terraform plan && terraform apply
terraform output app_env                       # paste into the Railway secret store
```

Read `infra/terraform/README.md` first — it documents what Phase 5 **cannot** do here:
ControlHub's compute is on Railway, so there is no VPC for default-deny egress and no IMDS
to block. The IAM split is delivered; the network controls are not achievable without
moving compute into a VPC.

Access keys are created out of band on purpose (they would otherwise sit in Terraform
state in plaintext):

```bash
aws iam create-access-key --user-name "$(terraform output -raw api_user_name)"
aws iam create-access-key --user-name "$(terraform output -raw worker_user_name)"
```

Put the API key on the API service and the worker key on the worker service. **Using the
same key for both defeats the split entirely.**

## Zero-trust controls (Phases 1–2) — operator steps

Design and rationale: `ZERO_TRUST_ASSUME_BREACH_DESIGN.md`. These are the steps
that are **not** automatic on deploy.

### One-time, in order

1. **`TRUSTED_PROXY_COUNT=1`** — required behind nginx. Without it `remote_addr` is
   nginx's IP, so the login rate limit becomes one global bucket (a bypass *and* a
   self-DoS at 10 logins/min org-wide) and audit source IPs are meaningless.

2. **KMS for secrets at rest.**
   - Create a CMK (e.g. `alias/controlhub-secrets`).
   - Grant the app role `kms:GenerateDataKey` and `kms:Decrypt` on that key only.
   - Set `SECRET_KMS_KEY_ID`. Existing `fernet:v1:` values keep working immediately —
     the switch needs no downtime.
   - Migrate stored values when convenient:
     ```bash
     flask secrets rewrap --dry-run   # report first
     flask secrets rewrap
     ```
   - Keep `SECRET_ENCRYPTION_KEYS` set until the rewrap reports `failed: 0`; it is what
     decrypts the not-yet-migrated rows.

3. **Audit mirror.**
   - `AUDIT_MIRROR_SINK=cloudwatch`, `AUDIT_MIRROR_LOG_GROUP=/controlhub/audit`.
   - Attach a resource policy to that log group denying `logs:DeleteLogGroup` and
     `logs:DeleteLogStream` to the application role. **Without this the mirror is only a
     convenience copy** — the same credential that rewrites the DB can erase it.

4. **Append-only audit table.** Requires the app to connect as a **non-owner** role —
   check first, because ownership implies full DML regardless of grants:
   ```bash
   psql "$SQLALCHEMY_DATABASE_URI" -c "SELECT tableowner FROM pg_tables WHERE tablename='audit_log';"
   ```
   If that is not your app role, apply the script (run as owner/superuser, never as the
   app role):
   ```bash
   psql "$SQLALCHEMY_DATABASE_URI" -v app_role=controlhub_app -f scripts/sql/audit_log_append_only.sql
   ```
   Migrations must then run as the owner, not the app role.

### 5. Just-in-time privilege elevation (Phase 3) — opt-in

Off until `JIT_ELEVATED_PERMISSIONS` is non-empty, so the migration alone changes nothing.

Recommended rollout, one permission at a time:

```bash
JIT_ELEVATED_PERMISSIONS=manage_secrets
# then, once operators are used to it:
JIT_ELEVATED_PERMISSIONS=manage_secrets,manage_roles,manage_sso,manage_org_settings
```

- **Do not gate `manage_users`.** It is routine work for `hr_admin`/`people_manager`.
  Gating routine work is how the whole control ends up switched off.
- **Before setting `JIT_DUAL_APPROVAL_PERMISSIONS`,** confirm at least two people hold the
  permission. A single-holder permission with dual approval is a permission nobody can use
  (self-approval is refused by design).
- **Before setting `JIT_REQUIRE_MFA=true`,** confirm every eligible operator is enrolled —
  otherwise they cannot elevate at all. Check with `GET /admin/elevation/config` per user.
- Grants last `JIT_ELEVATION_TTL_MINUTES` (default 15) and are revoked automatically on
  role change or disable.

Operators do not need training: any gated action opens the elevation prompt in the UI and
retries automatically once granted. Review usage at `GET /admin/elevation/grants`.

### 6. Agent egress allowlist (Phase 4) — set this if the agent service is on

Destination records validate only the *shape* of a target, so until you set these,
**anyone who can create a destination chooses where company data goes** — including
someone who has taken over an admin account. Approval does not help: it authorizes the
export, not the target.

```bash
AGENT_EGRESS_DRIVE_FOLDERS=<real folder id>,<real folder id>
AGENT_EGRESS_SHEETS=<real spreadsheet id>
```

To find the ids of destinations already in use:

```sql
SELECT id, name, destination_type, config FROM external_destination WHERE is_active;
```

Empty = permissive with a startup warning, so upgrading does not break a working
deployment. Once set, publishing to anything else returns `403
EGRESS_TARGET_NOT_ALLOWLISTED`.

The allowlist deliberately lives in env rather than the database: adding an egress target
should require a deploy, not an API call.

**Also note:** repointing a destination after a request was approved now returns `403
EGRESS_DESTINATION_CHANGED` — the request pins where it was approved to send. Renaming a
destination or editing its allowed templates is fine; changing the folder/spreadsheet id
invalidates already-approved requests, which must be re-submitted.

### Scheduled jobs

| Command | Frequency | On failure |
|---|---|---|
| `flask audit mirror` | every minute | exit 2 — retries next run, no data loss (high-water mark only advances on confirmed delivery) |
| `flask audit verify` | hourly | **exit 2 = audit tampering.** Page someone. |

> Route the `audit verify` alarm somewhere that is **not** ControlHub. An alert an
> attacker can silence from inside the app they just compromised is not an alert.

### Client compatibility note

Refresh-token rotation is enforced: replaying a spent refresh token revokes the whole
token family. `admin-ui` is updated. **Any other client that stores tokens — mobile,
scripts, integrations — must persist the rotated `refresh_token` from `/auth/refresh`**
or it will be logged out on its second refresh.

## Security headers / CSP

`nginx.conf` sets HSTS, X-Frame-Options DENY, nosniff, Referrer-Policy,
Permissions-Policy, and a **Content-Security-Policy** (`script-src 'self'`, no
unsafe-inline/eval; `frame-ancestors 'none'`). If the API is served from a
different origin than the SPA, add that origin to `connect-src`.

## Observability (baseline — partially implemented, expand before scale)

- Structured JSON logs with `request_id` across web + worker (implemented).
- `/healthz` (liveness) + `/readyz` (DB+Redis readiness) (implemented).
- **TODO (fast-follow):** error tracking (Sentry), request rate/error/latency
  metrics, auth-failure + API-key-denial counters, Redis/PG/queue-depth/failed-job
  gauges, and alerts (owners + thresholds). Redact secrets/PII in all telemetry.

## Auth-cookie migration (P1-3, planned)

Interim: tokens are in `localStorage` (XSS-exfiltratable; CSP added to reduce
reach). Target: httpOnly + Secure + SameSite=Lax cookies with CSRF tokens on
state-changing requests, credentialed CORS to approved origins only, cookies
cleared on logout/invalid refresh. Service-account `X-API-Key` auth is separate
and unaffected.

## Rollback

App rollback = redeploy previous image (migrations here are additive/backward
compatible). See `MIGRATION_AND_ROLLBACK_RUNBOOK.md` for schema/data rollback and
the `code.zip` history purge.
