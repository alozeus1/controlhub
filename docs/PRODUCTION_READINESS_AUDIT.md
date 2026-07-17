# ControlHub — Production Readiness Audit

**Reviewer roles:** Product Manager · Senior Platform Engineer · Senior QA
**Date:** 2026-07-17
**Verdict:** **NOT yet production-ready.** No showstoppers in core flows (auth, workflows, approvals, email all function and the 102-test suite is green), but there are **3 blockers and 5 high-severity issues** — mostly security and release-engineering — that must be resolved first. Details, evidence, and remediation below.

Severity key: **P0 = blocker (fix before prod)** · **P1 = high** · **P2 = medium** · **P3 = low/smell**.

---

## P0 — Blockers

### P0-1 · Service-account API keys are effectively root; scopes are never enforced
**Evidence:** `app/utils/rbac.py` — on any valid `X-API-Key`, the request is granted admin-level access and `request.current_user` is set to the service account's *creator*. `ApiKey.scopes` exists and `ApiKeyService.check_scope()` is defined (`app/services/service_accounts.py:242`) but is **never called** anywhere. So the n8n key — or any integration key — can call every admin endpoint: read/rotate **secrets**, change **user roles**, edit **org settings**, manage **roles/permissions**, etc.
**Impact:** A single leaked integration key = full tenant compromise. Unacceptable for a security/admin product.
**Remediation:**
- Enforce `scopes` in the API-key auth path: map each protected route (or blueprint) to a required scope and reject keys lacking it.
- Provision the n8n key with only `email:*` scopes (the provisioning script already sets these — they just aren't checked).
- Deny superadmin-only and secrets endpoints to API keys entirely.
- Add tests asserting a scoped key is 403'd on out-of-scope routes.

### P0-2 · An 88 MB `code.zip` is committed to the repository
**Evidence:** `git ls-files` shows `code.zip` tracked; `ls -lh code.zip` → 88M.
**Impact:** Repo bloat, slow clones/CI, and a real risk the archive contains source/secrets snapshots. Anything ever committed persists in history.
**Remediation:** `git rm --cached code.zip`, add to `.gitignore`, and purge from history (`git filter-repo` / BFG) before the repo is shared or made public. Scan history for other large/secret blobs.

### P0-3 · Database migrations are never validated (Postgres-only DDL; CI tests run on SQLite)
**Evidence:** CI (`.github/workflows/ci.yml`) runs pytest against `sqlite:///:memory:`, which uses `create_all` — **not** the migration chain. The migrations contain Postgres-only DDL (e.g. `ALTER TABLE user ALTER COLUMN role SET NOT NULL`) that fails on SQLite, and there is a prior `backfill_missing_model_columns` migration — evidence the two schemas have drifted before.
**Impact:** A broken or missing migration would only be discovered **at deploy time**, potentially bricking the release or corrupting the schema. (A static reconciliation done during this audit found no *current* column drift — the backfill migration is idempotent and covers the columns — but this is unverified on real Postgres.)
**Remediation:** Add a CI job with a Postgres service container that runs `flask db upgrade` on an empty DB and then runs the pytest suite against Postgres. Fail CI on any Alembic error or model/migration drift (`alembic check`).

---

## P1 — High

### P1-1 · Frontend test job in CI is non-functional
**Evidence:** `admin-ui/package.json` → `"test": "echo \"Error: no test specified\" && exit 1"`. CI invokes CRA-style `CI=true npm test -- --watchAll=false` on a **Vite** app with no Vitest/Jest configured, despite `@testing-library/*` deps and `src/utils/api.test.js`.
**Impact:** The "Run frontend tests" step fails (or is silently ignored); there is **no executable frontend test coverage**. CI is likely red on every run, eroding trust in the gate.
**Remediation:** Wire Vitest + jsdom, fix the `test` script, and make CI fail on test failure. Add smoke tests for the auth flow and the API client.

### P1-2 · JWT revocation "fails open" when Redis is unavailable
**Evidence:** `app/__init__.py` `check_if_token_revoked` returns `False` (token considered valid) if Redis errors — with an explicit "fail open" comment.
**Impact:** During any Redis blip, **revoked/logged-out/compromised tokens keep working**. For a security product this is the wrong default.
**Remediation:** Fail **closed** (treat as revoked / force re-auth) or, if availability is paramount, shorten access-token TTL and alert on Redis unavailability so the exposure window is bounded and observed.

### P1-3 · JWTs stored in `localStorage`
**Evidence:** `admin-ui/src/pages/Login.jsx` writes `access_token` to `localStorage`.
**Impact:** Any XSS (see P2-6) can exfiltrate a live admin token.
**Remediation:** Move tokens to httpOnly + Secure + SameSite cookies with CSRF protection; if that's too large a change now, tighten CSP and treat this as a known, tracked risk.

### P1-4 · No global JSON error handler
**Evidence:** No `errorhandler`/`register_error_handler` anywhere in `app/`. Unhandled exceptions return Flask's default HTML 500.
**Impact:** The SPA parses JSON and will show a generic failure; 500s aren't consistently logged with context; stack shapes are inconsistent across the API.
**Remediation:** Register handlers for 400/401/403/404/405/500 returning `{"error","code"}` JSON, log with the existing request id, and never leak internals in prod.

### P1-5 · Dependencies are essentially unpinned
**Evidence:** `requirements.txt` pins only `Flask-JWT-Extended==4.6.0`; everything else (Flask, SQLAlchemy, boto3, cryptography, pyotp, …) floats.
**Impact:** Non-reproducible builds; a bad upstream release can break prod or introduce a vuln silently.
**Remediation:** Pin all versions via a lockfile (pip-tools/`pip freeze` → `requirements.lock`), enable Dependabot/`pip-audit` in CI.

---

## P2 — Medium

- **P2-1 · Ops email alert channel is a stub.** `app/services/notifications.py:420` — email delivery is a "placeholder — would integrate with email service." Email NotificationChannels silently don't send. Wire to SES or hide the channel type.
- **P2-2 · Third-party integrations run in MOCK mode by default** (`app/utils/integrations_mock.py`: Taiga/Mattermost/etc.). Acceptable posture, but the UI should clearly flag "mock/disconnected" so operators aren't misled.
- **P2-3 · Container hardening.** `Dockerfile.api` runs as **root** and has **no HEALTHCHECK**. Add a non-root `USER` and a `HEALTHCHECK` against `/healthz`.
- **P2-4 · RQ worker not codified for prod.** The entrypoint starts only gunicorn; the campaign send worker is a separate compose service. On Railway this must be a **second service** (`rq worker campaigns default`) or **email sends never process in production**. Also: no retry/backoff/dead-letter on the queue.
- **P2-5 · Missing Content-Security-Policy.** `nginx.conf` sets HSTS/X-Frame/nosniff/Referrer-Policy but no CSP — the main defense against XSS (relevant given P1-3/P2-6).
- **P2-6 · Unsanitized `dangerouslySetInnerHTML` for campaign HTML** (`pages/campaigns/Campaigns.jsx`, `CampaignDetail.jsx`). Admin-authored HTML is rendered in the dashboard and stored for sending. Render previews in a sandboxed `<iframe sandbox>` and sanitize on save.
- **P2-7 · Thin tests on security-sensitive modules.** No/indirect coverage for `secrets`, `env_configs`, `service_accounts` scope logic, `incidents`, `deployments`, `feature_flags`, `runbooks`. Prioritize secrets-reveal gating and (post P0-1) API-key scope enforcement.
- **P2-8 · SSO CSRF state/nonce live in a signed JWT in the URL**, not an httpOnly cookie (already flagged as a hardening TODO in `app/routes/sso.py`). Acceptable but not best practice.
- **P2-9 · Audit log grows unbounded.** No retention/rotation/partitioning. Define a retention policy + archival job before the table becomes a hotspot.

---

## P3 — Low / smells

- **P3-1** `app/utils.py:17` uses a bare `except:`.
- **P3-2** Pervasive SQLAlchemy 1.x `Query.get()` legacy-deprecation warnings — migrate to `Session.get()` before any SQLAlchemy 2.0 upgrade.
- **P3-3** CI flake8 ignores `F401` (unused imports) and `E722` (bare except) — hides real smells; tighten once the tree is clean.
- **P3-4** `wsgi.py` has `app.run(host="0.0.0.0", port=80)` under `__main__` — dev-only; make sure prod uses gunicorn (it does via entrypoint).
- **P3-5** Several list endpoints are unpaginated or hard-capped (`workflows/runs` limit 50; roles/lists return all) — fine now, revisit at scale.
- **P3-6** Only the routed `<Outlet>` is wrapped in an ErrorBoundary; a crash in `TopNav`/`Sidebar` still white-screens (mitigated by recent guards, but no top-level boundary).
- **P3-7** Many stats/summaries aggregate in Python rather than SQL — fine at current volume; watch as data grows.

---

## Product-completeness gaps (PM lens)

- **MFA/SSO are foundational.** SSO needs a live IdP and has no end-to-end test; enforcement of org-level "require MFA" is soft.
- **Email editor** is a plain HTML editor; the planned GrapesJS drag-drop was documented as a drop-in but isn't wired. No dedicated-IP/warm-up automation (acceptable < 50k/mo).
- **Observability:** structured request logs exist, but no metrics/traces/APM, no alerting, no dashboards, no error tracking (Sentry) — you'll be flying blind on the first incident.
- **Resilience:** no documented DB backup/restore runbook; no rate limiting beyond login/MFA; no data-retention/GDPR delete for `people`/`subscribers` beyond unsubscribe.

---

## What could NOT be verified in this environment (call out explicitly)

- **Production `vite build`** — the mounted `node_modules` are arm64 (from the Mac); the Linux sandbox can't run them. Every changed file was validated by AST parse, but a real `npm run build` in CI is the true check.
- **Migrations on real Postgres** — no Postgres available here (static reconciliation only).
- **Live SES/SNS, OIDC, and n8n round-trips** — no external services in the sandbox.

---

## Recommended go / no-go path

**Before prod (must):** P0-1, P0-2, P0-3, P1-1, P1-2, P1-4. (P1-3, P1-5 strongly recommended.)
**Fast-follow (first week):** P2-3, P2-4, P2-5, P2-6, plus observability (Sentry + basic metrics) and a DB backup runbook.
**Backlog:** remaining P2/P3 and the product-completeness items.

Estimated effort to clear the must-fix set: roughly 3–5 focused engineering days, the bulk of it P0-1 (scope enforcement + tests) and P0-3/P1-1 (CI on Postgres + real frontend tests).
