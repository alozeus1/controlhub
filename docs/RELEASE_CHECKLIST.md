# Release Checklist

A release is **GO** only when every mandatory gate is green **with evidence**.
CI enforces the gates (no `continue-on-error`); this checklist is the human
sign-off.

## Mandatory CI gates (must all pass)

- [ ] `backend-lint` — flake8 correctness (F401, E722, F811, F841, E999)
- [ ] `backend-test-sqlite` — full pytest (fast)
- [ ] `backend-postgres` — migrate empty DB → head, **single head**, drift check, pytest on Postgres
- [ ] `frontend` — eslint, **Vitest (fails on no-tests)**, production `vite build`
- [ ] `dependency-audit` — `pip-audit --strict` + `npm audit --audit-level=high`
- [ ] `secret-scan` — gitleaks (no secrets in tree/history diff)
- [ ] `repo-policy` — no tracked file > 5 MB, no banned archives (`check_large_files.py`)
- [ ] `container` — image builds, **runs as non-root**, HEALTHCHECK present, Trivy no HIGH/CRITICAL
- [ ] `deploy-config` — `docker compose config` valid; required deploy files present

## Security sign-off

- [ ] API-key scope enforcement verified (`test_api_key_scopes.py` green)
- [ ] API keys cannot reach secrets / users / roles / org / superadmin
- [ ] JWT revocation is **fail-closed** (`JWT_FAIL_OPEN=false`) — `test_jwt_revocation.py` green
- [ ] 500s return safe JSON, no internals — `test_error_handlers.py` green
- [ ] Campaign HTML sanitized + preview sandboxed — `test_html_sanitizer.py` green
- [ ] CSP present and app verified under it in staging
- [ ] **`code.zip` purged from history AND leaked secrets rotated** (destructive; see runbook)

## Operational readiness

- [ ] DB backup configured; a **restore test** has succeeded
- [ ] Worker service provisioned (same image/commit as web); queue processing verified
- [ ] `/healthz` + `/readyz` wired to platform health checks
- [ ] Prod env vars set (incl. `ENVIRONMENT=production`, `JWT_FAIL_OPEN=false`, no `*` CORS)
- [ ] Observability: at minimum structured logs + error tracking wired (Sentry fast-follow)

## Product acceptance (this cycle)

- [ ] Human login, MFA-enforced login, logout/revocation
- [ ] Redis-outage → protected access denied (fail-closed)
- [ ] Service-account in-scope succeeds; out-of-scope + human-only denied
- [ ] SSO initiation/callback (id_token JWKS/aud/iss/nonce verified) — with a real IdP
- [ ] Campaign create → safe sandboxed preview → queued send processed by worker
- [ ] Audit records written (incl. service-account attribution)

## Verdict

- [ ] **GO** — all mandatory gates green + operator actions complete
- [ ] **CONDITIONAL GO** — code complete + tested; external CI/infra gates pending
- [ ] **NO-GO** — one or more mandatory gates failing

_Current status (2026-07-17): **CONDITIONAL GO** — see
`PRODUCTION_READINESS_REMEDIATION.md`._
