# ControlHub — Security Baseline

Branch `security-gauntlet-controlhub`. Baseline commit `d3a4298`
(in-flight zero-trust phase 1–4 work, carried over unchanged).

> **Commit references.** The six controls reached `main` as the single squash
> commit `51dfce8` (PR #30), which merged while this branch was still open. The
> per-control hashes below are from the `security-gauntlet-controlhub` branch
> history and are useful for reading one control in isolation; on `main` they are
> all one commit.

## 1. Architecture as deployed

| Layer | Reality | Notes |
| --- | --- | --- |
| API | Flask 3.1 + SQLAlchemy 2.0 + Alembic, Gunicorn 26, 4 workers | `wsgi.py`, `Procfile` |
| Async | RQ 2.10 worker, queues `campaigns` + `default`, with scheduler | Separate Railway service, same image/commit |
| Frontend | React 19 + Vite 8 SPA | `admin-ui/`, 33 pages |
| Data | PostgreSQL (managed), Redis (limiter + queue), S3 (uploads, artifacts) | `psycopg2`, `redis`, `boto3` |
| Compute | **Railway containers.** No VPC, no managed WAF | `Procfile` runs gunicorn directly |
| Reverse proxy | nginx — **compose topology only** | `nginx.conf` is not in the Railway path |
| AWS | SES, SNS, S3, KMS, CloudWatch, CloudTrail | `infra/terraform/` |
| Identity | Password + TOTP MFA (`pyotp`), OIDC SSO, service-account API keys, Google WIF | |
| Non-prod | Docker Compose + LocalStack | `docker-compose.yml` |

**Topology consequence recorded during this pass:** because Railway runs gunicorn
directly, anything expressed only in `nginx.conf` — the header policy, the
`limit_req` zones — is absent in production. This drove controls 5 and 6.

## 2. Existing controls (verified by reading the code, not the docs)

| Control | Location | State |
| --- | --- | --- |
| Role hierarchy, 8 levels | `app/models.py:10` `ROLE_LEVELS` | Unknown role ⇒ level 0, fail-closed |
| Role gate | `app/utils/rbac.py` `require_role` | Rejects API keys outright on human endpoints |
| Scope gate | `app/utils/rbac.py` `require_scope` | Deny-by-default; never impersonates the key's creator |
| Permission catalog | `app/permissions.py` 13 keys | `require_permission` / `has_permission` |
| Just-in-time elevation | `app/permissions.py` `require_elevation` | **Opt-in — no-op unless `JIT_ELEVATED_PERMISSIONS` lists the key** (GAP-07) |
| Dual approval | `app/routes/elevation.py` | Self-approval refused; approver must hold the permission |
| MFA | `app/routes/mfa.py` | Purpose-scoped challenge token, lockout, fails closed on error |
| Session revocation | `app/services/session_security.py` | Epoch bump, refresh-token family rotation, replay kills family |
| Secret encryption | `app/services/secret_crypto.py` | KMS envelope with encryption context; dev Fernet fallback (GAP-08) |
| Audit chain | `app/services/audit_chain.py` | Hash-chained rows, `verify_chain`; append-only SQL grant in `scripts/sql/` |
| Audit mirror | `app/services/audit_sink.py` | **Off by default** (`AUDIT_MIRROR_SINK=none`) (GAP-09) |
| SSRF guard | `app/services/safe_http.py` | Resolves all addresses, blocks private/link-local, re-validates redirects |
| Agent egress | `app/services/agent_egress.py` | Destination allowlist, approval-pinned fingerprint |
| HTML sanitisation | `app/services/html_sanitizer.py` | `bleach` with CSS allowlist |
| Client IP | `app/__init__.py` ProxyFix + `app/utils/audit.py` | Hop-counted; audit reads `remote_addr` only |
| Rate limiting | `flask-limiter` + Redis | 23 routes after this pass; `default_limits=[]` |
| Headers | `app/utils/security_headers.py` | CSP + HSTS added this pass |

## 3. Endpoint surface

280 routes. Generated inventory: [endpoint-inventory.md](endpoint-inventory.md).

| Posture | Count |
| --- | --- |
| Role-gated (`require_role`) | 171 |
| Authenticated, any active user | 65 |
| Scope-gated (service or human) | 28 |
| Public, allowlisted with a reason | 16 |

Of the 16 public routes, 4 authenticate inside the handler (feature-flag SDK key,
SNS-signed webhook, unsubscribe token) and 12 are genuinely anonymous — health
and readiness probes, the static landing page, the module on/off flag list, and
the pre-authentication steps of the login and SSO flows. Each is justified
individually in `scripts/dump_endpoint_inventory.py::PUBLIC_ALLOWLIST` and the
list is CI-enforced.

## 4. Critical journeys mapped

Registration (admin-invited, not public) · login → MFA challenge → token pair ·
SSO login → callback → token pair · refresh rotation and revocation · secret
create/reveal/update/delete · env-config write and decrypt · elevation request →
dual approval → expiring grant · role and permission change · people/HR record
read and CSV export · campaign create → send → SES → SNS event → suppression ·
agent request → run → artifact → presign/publish · audit query → export → SIEM
delivery · upload → S3 → download.

## 5. Baseline commands and results

At baseline commit `d3a4298`, Python 3.13.5 local (CI uses 3.10):

| Gate | Command | Baseline | After this pass |
| --- | --- | --- | --- |
| Backend lint | `flake8 app/ tests/ scripts/ --select=F401,F811,F841,E722,E999,F823 --max-line-length=120` | **FAIL — 4 findings** | pass |
| Backend tests | `pytest tests/ -q` (SQLite in-memory) | 264 passed | **335 passed** |
| Frontend lint | `npm run lint` | pass (15 warnings, 0 errors) | pass |
| Frontend tests | `npm run test -- --passWithNoTests=false` | 2 files, 10 tests passed | pass |
| Frontend build | `npm run build` | pass (chunk-size warning) | pass |
| Endpoint surface | `python scripts/dump_endpoint_inventory.py --check` | n/a (gate created) | pass, 0 unreviewed |

The four flake8 findings were a **baseline failure, not a regression** — they
arrived with the carried-over zero-trust work and were fixed at source in
`d1c6e5e` rather than by widening the ignore list.

### Not run locally

`pip-audit`, `npm audit`, `gitleaks`, Trivy filesystem/image scans, the PostgreSQL
migration replay and the container build are CI-only jobs in
`.github/workflows/ci.yml` and were not executed in this environment. They are
unchanged by this pass except for the added `endpoint-surface` job.

## 6. Rollback point

Every control is a single revertible commit; none carries a schema migration or a
required configuration change. On `main` the six are squashed into `51dfce8`
(PR #30) — see [deployment-and-rollback.md](deployment-and-rollback.md) for the
revert commands that apply there.

```
c68f3be  app-level CSP + HSTS
2852b59  per-identity export/agent quotas
28b549d  endpoint inventory + CI surface gate
3289820  password-reset link origin
d1c6e5e  flake8 baseline fix
fe7ccb5  SNS webhook verification hardening
d3a4298  BASELINE (carried-over zero-trust work)
```
