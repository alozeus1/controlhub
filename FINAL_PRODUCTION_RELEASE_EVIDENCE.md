# ControlHub Final Production Release Evidence

Signed at: 2026-07-17 12:17:33 CDT  
Release owner: Codex release-gate automation  
Final verdict: **NO-GO**

## Release Identity

| Field | Value |
| --- | --- |
| Repository | `alozeus1/controlhub` |
| Branch | `prod-readiness-ci-operator-gates` |
| Code release-candidate SHA | `004309517f6dadbc3133c2e0bba7e8cfe8b29c20` |
| Baseline SHA | `c5d4df76317e9d7b587371d25ab2f79f02afe220` |
| Tag | Not created |
| Working tree state | Clean after evidence commit |
| Production decision | **NO-GO** because A-1 rotation/revocation and multiple live operational gates remain incomplete |

Note: this evidence file is committed after the code release-candidate commit. The final pushed branch head and CI run for that head are recorded in the release-owner final response after GitHub Actions completes.

## A-1 Through A-12 Status Matrix

| ID | Area | Status | Evidence |
| --- | --- | --- | --- |
| A-1 | Historical secret exposure | **FAILED** | `code.zip` is absent from current intended refs, but exposed credentials have not been verifiably rotated/revoked. |
| A-5 | Legacy UI removal | VERIFIED locally | `ui_bp` no longer registered; dead templates removed; `tests/test_a5_ui_blueprint_removed.py` passed. |
| A-6 | OIDC SSRF protection | VERIFIED locally | `app/services/safe_http.py`; SSO uses guarded GET/POST and validates JWKS URL; `tests/test_a6_ssrf_guard.py` passed. |
| A-7 | EnvConfig encryption | VERIFIED locally | model encrypt-on-flush, backfill migration, PostgreSQL fixture upgrade/backfill/decrypt/idempotency checks passed. |
| A-10 | Feature flag SDK protection | VERIFIED locally | project-scoped hashed SDK keys, admin key lifecycle, revoked/wrong-project denial; `tests/test_a10_feature_flag_sdk.py` passed. |
| Rate limiting | VERIFIED locally | send/test campaign, search, secret reveal, SDK endpoint limits added; backend suite passed. |
| Production mock protection | VERIFIED locally | production Taiga/Mattermost/email mock fallback now fails closed unless explicitly overridden; 3 regression tests added. |
| CI improvements | VERIFIED locally / CI pending | PostgreSQL tests now use external DSN; Trivy filesystem and SBOM jobs added. Remote CI pending after push. |
| PostgreSQL migrations | VERIFIED locally | Empty DB upgrade, single head, migration drift, production-shaped EnvConfig upgrade passed. |
| Container/supply chain | VERIFIED locally | Docker image built, Trivy image/fs scans passed, SBOM generated, non-root UID `10001`, healthcheck configured. |
| Worker | PARTIAL | Real RQ worker processed one synthetic dry-run campaign exactly once. Retry/timeout/permanent-failure/alerting still unverified. |
| Live integrations/ops/UI/perf | BLOCKED | Require authorized staging/prod-like environments, credentials, test IdP, SES/SNS/n8n/Taiga/Mattermost, monitoring, backup/restore, browser/perf tooling. |

## Credential Rotation Matrix

| Credential category | Provider/system | Current exposure | Rotation mechanism | Dependents | Validation | Status |
| --- | --- | --- | --- | --- | --- | --- |
| Flask session signing key | App secret manager | Present in historical archive | Generate new secret; update secret manager; redeploy; invalidate sessions | API/web sessions | Old signed cookies rejected; new sessions valid | **FAILED - operator required** |
| JWT signing key | App secret manager | Present in historical archive | Generate new secret; update secret manager; redeploy; revoke active tokens | API auth | Old JWTs rejected; login/refresh valid | **FAILED - operator required** |
| PostgreSQL credentials | DB provider | Potentially present in historical archive | Rotate DB user password or recreate least-privileged user | API, worker, migrations | New connectivity works; old password denied | **FAILED - operator required** |
| AWS/SES/SNS credentials | AWS IAM | Potentially present in historical archive | Revoke old IAM access key; create scoped replacement if needed | Email, SNS webhook, object/integration flows | New sender path works; old key denied | **FAILED - operator required** |
| Redis credentials | Redis provider | Potentially present in historical archive | Rotate Redis auth token/URL | API, RQ worker, rate limiter | API/worker ready; old token denied | **FAILED - operator required** |
| OIDC client secret | IdP | Potentially present in historical archive | Rotate client secret in IdP and secret manager | SSO login/callback | Test IdP login works; old secret denied | **FAILED - operator required** |
| Webhook/external API secrets | n8n/webhooks/providers | Potentially present in historical archive | Rotate provider tokens and webhook secrets | n8n, Taiga, Mattermost, Resend/webhooks | Signed/invalid webhook tests; old token denied | **FAILED - operator required** |
| EnvConfig encryption keys | App secret manager | Potentially present in historical archive | Add new primary, retain old only for decrypt window, re-encrypt/backfill, retire old | EnvConfig decrypt/encrypt | Ciphertext decrypts with new key; old key removed after rewrap | **FAILED - operator required** |

## Operator Checkpoint: Credential Rotation

- Action requiring approval: rotate/revoke every credential category listed above.
- Why it is required: historical `code.zip` exposure means purging Git history does not invalidate already-copied secrets.
- Exact target/environment: production and staging/prod-like secret managers, AWS IAM/SES/SNS, database provider, Redis provider, IdP, n8n/webhook providers.
- Expected impact: session/JWT invalidation; short restart/redeploy window for API and worker; possible integration credential refresh.
- Pre-checks completed: current intended refs no longer expose `code.zip` or `.env`; history-aware Gitleaks passed locally.
- Proposed commands or console actions: provider-specific key rotation through approved consoles/CLI; update secret manager references; redeploy/restart API and workers.
- Verification: new app health/readiness, SSO login, DB/Redis connectivity, SES/SNS test, old credentials denied, old sessions/JWTs rejected, audit/security logs reviewed.
- Rollback: restore last known-good secret versions only if new deployment fails before old credentials are revoked; do not restore exposed credentials after revocation.
- Evidence that will be recorded: sanitized timestamps, secret version IDs, provider key IDs/prefixes only, deployment IDs, safe negative-test results.
- Explicit approval requested: **Required before live rotation/revocation.**

## Git History Cleanup Evidence

| Check | Result |
| --- | --- |
| `git log --all --oneline -- code.zip` | No output |
| `git rev-list --objects --all | rg '(^|/)code\.zip$|(^|/)\.env$'` | No output |
| `gitleaks detect --source . --log-opts='--all' --redact` | 71 commits scanned, no leaks found |
| Limitation | Does not prove forks, clones, caches, release assets, or collaborator machines are cleaned. |

## Local Gate Evidence

| Gate | Command | Result |
| --- | --- | --- |
| Backend static check | `python3 -m flake8 app/ tests/ scripts/ --select=F401,F811,F841,E722,E999,F823 --max-line-length=120` | PASS |
| Large/banned files | `python3 scripts/check_large_files.py` | PASS: no oversized or banned tracked artifacts |
| Compose config | `docker compose config -q` | PASS |
| Backend tests, default DB | `python3 -m pytest tests/ -q` | PASS: 174 passed, 2463 warnings |
| Backend tests, PostgreSQL | `SQLALCHEMY_DATABASE_URI=postgresql://... ALLOW_TEST_DATABASE_RESET=true python3 -m pytest tests/ -q` | PASS: 174 passed, 2463 warnings |
| Frontend clean install | `cd admin-ui && npm ci` | PASS: 302 packages audited, 0 vulnerabilities |
| Frontend lint | `cd admin-ui && npm run lint` | PASS: 0 errors, 15 warnings |
| Frontend tests | `cd admin-ui && npm run test -- --passWithNoTests=false` | PASS: 2 files, 10 tests |
| Frontend production build | `cd admin-ui && npm run build` | PASS with Vite large chunk warning: main JS 1,330.98 kB, gzip 363.94 kB |
| Python dependency audit | `python3 -m pip_audit -r requirements.txt --strict` | PASS: no known vulnerabilities |
| npm audit | `cd admin-ui && npm audit --audit-level=high` | PASS: found 0 vulnerabilities |
| History Gitleaks | `gitleaks detect --source . --log-opts='--all' --redact` | PASS: no leaks found |
| Trivy filesystem | `trivy fs --severity HIGH,CRITICAL --exit-code 1 --ignore-unfixed --skip-dirs admin-ui/node_modules .` | PASS: 0 HIGH/CRITICAL |
| Production config fail-closed | weak production `SECRET_KEY`/`JWT_SECRET_KEY` probe | PASS: rejected weak keys |

## PostgreSQL Evidence

| Requirement | Result |
| --- | --- |
| Empty DB upgrade | PASS: fresh PostgreSQL 15 DB upgraded to `y5z6a7b8c9d0` |
| Single Alembic head | PASS: `y5z6a7b8c9d0 (head)` |
| Migration drift | PASS: `OK: 68 tables match the migrated schema. No drift.` |
| Backend suite on PostgreSQL | PASS: 174 tests |
| Production-shaped fixture | PASS: synthetic pre-remediation EnvConfig secret upgraded to `fernet:v1:` ciphertext |
| Non-secret EnvConfig | PASS: non-secret value remained plaintext/behaviorally unchanged |
| Encryption idempotency | PASS: repeated upgrade did not double-encrypt |
| Downgrade/forward recovery | PARTIAL: later schema downgrade/upgrade path tested; production rollback remains unverified |
| `create_all` as migration substitute | PASS locally: production container startup ran `flask db upgrade`; no production `create_all` path used for runtime smoke |

## Container And Supply-Chain Evidence

| Check | Result |
| --- | --- |
| Image build | PASS: `docker build -f Dockerfile.api -t controlhub-api:release-gate .` |
| Image digest | `sha256:694800460bbd2088f52a5beb479617c5c265886d88edfba21962a72887fcfa0b` |
| Trivy image scan | PASS: 0 HIGH/CRITICAL vulnerabilities |
| SBOM | PASS: CycloneDX at `/tmp/controlhub-api-release-gate.sbom.cdx.json` during local run |
| Non-root | PASS: image runs as UID `10001` |
| Healthcheck | PASS: `curl -fsS http://localhost:80/healthz || exit 1` configured |
| Image secret inspection | PASS: `/app/.env` and `/app/code.zip` absent; history keyword scan found no app secrets |
| Runtime smoke | PASS: rebuilt API returned `/healthz` and `/readyz`; container health `healthy` |

## Worker And Integration Evidence

| Area | Result |
| --- | --- |
| RQ/Redis worker | PARTIAL PASS: rebuilt worker listened on `campaigns` and `default`; synthetic dry-run campaign job completed exactly once with `sent_count=1`, `failed_count=0` |
| RQ retry/timeout/permanent failure | BLOCKED/UNVERIFIED: not executed in a staging/prod-like queue with alerting |
| SES/SNS | BLOCKED: dry-run SES only; no real approved provider sandbox round-trip |
| OIDC | BLOCKED: SSRF regression tests passed; no live test IdP round-trip |
| n8n | BLOCKED: no authorized live n8n endpoint/credentials provided |
| Taiga/Mattermost | BLOCKED or explicitly disabled required: production mock fallback now fails closed; live provider validation still needed if in production scope |

## Monitoring, Backup, Restore, Browser, Accessibility, Performance

| Gate | Status | Reason |
| --- | --- | --- |
| Monitoring and alert delivery | BLOCKED | No authorized on-call/observability target provided; no safe test alert sent. |
| Backup restore | BLOCKED | No sanitized backup source or restore target authorized. |
| Application/database rollback | BLOCKED | Local container smoke ran; no production-like rollback environment authorized. |
| Browser/responsive flows | BLOCKED | No deployed production-like frontend URL validated with browser automation. |
| Accessibility | BLOCKED | Automated/manual a11y scans not run against production build in browser. |
| Performance/reliability | BLOCKED | No thresholds approved and no load/perf environment executed. Existing Vite bundle warning remains P3 until measured. |
| Production-like deployment smoke | BLOCKED | No authorized staging/prod-like deployment target provided. |

## CI Evidence

Remote CI is pending for the pushed branch head. Local CI-equivalent gates above passed for code SHA `004309517f6dadbc3133c2e0bba7e8cfe8b29c20`; however, **CI is not VERIFIED** until GitHub Actions completes against the pushed branch head.

## New Findings

| Severity | Finding | Status |
| --- | --- | --- |
| P0 | Exposed historical credentials not rotated/revoked | OPEN |
| P1 | Production integration mocks previously failed open | FIXED locally in `004309517f6dadbc3133c2e0bba7e8cfe8b29c20`; CI pending |
| P2 | RQ advanced failure/retry/alerting not validated | OPEN |
| P2 | Browser/a11y/perf/live integration/restore/rollback gates not executed | OPEN |
| P3 | Frontend bundle large-chunk warning | OPEN pending measured performance |

## Final Mandatory Checklist

| Gate | Status |
| --- | --- |
| Release remediation committed to an exact SHA | VERIFIED: `004309517f6dadbc3133c2e0bba7e8cfe8b29c20` |
| Working tree clean | PENDING after evidence commit |
| CI green for exact release SHA | BLOCKED/PENDING remote run |
| A-1 credentials rotated or revoked | FAILED |
| Old sessions and exposed credentials rejected | FAILED |
| `code.zip` removed from intended reachable history | VERIFIED for current intended refs only |
| History-aware secret scan passed | VERIFIED locally |
| PostgreSQL empty-database migration passed | VERIFIED locally |
| PostgreSQL production-shaped upgrade passed | VERIFIED locally |
| Migration drift and single-head checks passed | VERIFIED locally |
| EnvConfig encryption backfill verified on PostgreSQL | VERIFIED locally |
| Backend PostgreSQL tests passed | VERIFIED locally |
| Frontend lint/tests/production build passed | VERIFIED locally |
| Dependency audits passed | VERIFIED locally |
| Gitleaks passed | VERIFIED locally |
| Trivy filesystem and image scans passed | VERIFIED locally |
| SBOM generated | VERIFIED locally |
| Container non-root and healthcheck verified | VERIFIED locally |
| RQ worker end-to-end job verified | PARTIAL VERIFIED locally |
| Required integrations completed test round-trips | BLOCKED |
| Production cannot silently use mocks | VERIFIED locally by fail-closed regression tests |
| Monitoring and alert delivery verified | BLOCKED |
| Backup restore demonstrated | BLOCKED |
| Application/database recovery strategy demonstrated | BLOCKED |
| Browser and responsive flows passed | BLOCKED |
| Accessibility validation passed | BLOCKED |
| Performance thresholds passed | BLOCKED |
| Production-like deployment smoke test passed | BLOCKED |
| No unresolved P0/P1 findings | FAILED |
| Every deferred P2 has approved risk acceptance, owner, deadline, and controls | FAILED |
| No newly introduced release blocker remains | FAILED |

## Release Decision

**NO-GO.** The application remediation is credible and locally verified, but production release is blocked until credential rotation/revocation, CI on the pushed head, live integration round-trips, monitoring/alerting, backup restore, rollback, browser/accessibility/performance, and production-like deployment smoke are completed and evidenced.
