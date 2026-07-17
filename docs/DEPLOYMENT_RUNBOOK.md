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
