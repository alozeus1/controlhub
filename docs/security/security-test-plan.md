# ControlHub — Security Test Plan

## 1. Automated evidence, mapped to controls

Run: `SQLALCHEMY_DATABASE_URI="sqlite:///:memory:" FLASK_APP=wsgi.py ALLOW_TEST_DATABASE_RESET=true pytest tests/ -q`

| Control | Test file | Cases | Negative coverage |
| --- | --- | --- | --- |
| Inbound SNS/SES trust boundary | `tests/test_sns_webhook_trust.py` | 21 | Attacker-hosted signing cert on 5 non-SNS hosts; plaintext cert URL; stale and unparseable timestamps; missing timestamp in production; unset and wrong `SNS_TOPIC_ARN`; unknown `SignatureVersion`; LocalStack short-circuit in production; 5 SSRF targets for `SubscribeURL`; replay of a legitimate event |
| Reset-link origin | `tests/test_password_reset_link_origin.py` | 11 | 3 forged `Host` values; 3 forged `X-Forwarded-Host` values; unconfigured-origin refusal; enumeration parity |
| Authenticated surface | `tests/test_public_route_allowlist.py` | 5 | Synthetic unregistered route is flagged; stale allowlist entries; reason-free entries; restricted modules never public |
| Export and agent quotas | `tests/test_export_and_agent_quotas.py` | 11 | 429 on each throttled class; cross-identity isolation; raw API key absent from the bucket key |
| Response headers | `tests/test_security_headers.py` | 16 | HSTS absent over plaintext; proxy policy not overwritten or duplicated; static delivery still cacheable |
| Zero-trust phases 1–4 (carried over) | `tests/test_zero_trust_phase{1,2,3,4}.py` | 75 | Elevation of an ineligible permission; self-approval; approver without the permission; failed re-auth; destination repointing after approval; template/field scope |
| API key and scope model | `tests/test_api_key_scopes.py` | — | Key on human endpoint; scope mismatch; disabled service account |
| JWT revocation | `tests/test_jwt_revocation.py` | — | Revoked token; epoch mismatch |
| SSRF guard | `tests/test_a6_ssrf_guard.py` | — | Private, loopback, link-local, metadata addresses |
| Env-config encryption | `tests/test_a7_env_config_encryption.py`, `tests/test_env_config_contract.py` | — | Decryption failure surfaced, not silently empty |
| Feature-flag SDK key | `tests/test_a10_feature_flag_sdk.py` | — | Missing, revoked, wrong-project keys are indistinguishable |
| Secrets authorization | `tests/test_secrets_security.py` | — | Role and elevation gates; value masking in audit |
| HTML sanitisation | `tests/test_html_sanitizer.py` | — | Script, event-handler and style-injection payloads |
| Cross-user self-service | `tests/test_saas_phase2.py`, `test_saas_employee_reviews.py`, `test_saas_poc.py` | — | Another person's onboarding item, self-review, biweekly review |
| Error handling | `tests/test_error_handlers.py` | — | No stack or SQL in the response body |
| SES sender identity | `tests/test_ses_senders.py` | — | Unverified `From` domain refused |

Suite total: **335 passing** (264 at baseline `d3a4298`; 71 added).

## 2. CI gates

`.github/workflows/ci.yml` — every job is release-blocking, none uses
`continue-on-error`.

| # | Job | Checks |
| --- | --- | --- |
| 1 | `backend-lint` | flake8 correctness selection (F401, F811, F841, E722, E999, F823) |
| 2 | `backend-test-sqlite` | Full suite, fast feedback |
| 3–5 | `backend-postgres` | Migration from an empty DB, single-head assertion, model/migration drift, full suite on PostgreSQL |
| 6–8 | `frontend` | eslint, Vitest (fails on no tests), production build |
| 9 | `dependency-audit` | `pip-audit --strict`, `npm audit --audit-level=high` |
| 10 | `secret-scan` | gitleaks, full history |
| 11 | `repo-policy` | Large-file scan |
| 12–16 | `container` | Trivy filesystem, image build, CycloneDX SBOM, non-root verification, HEALTHCHECK verification, Trivy image scan (HIGH/CRITICAL, exit 1) |
| **17** | **`endpoint-surface`** | **No unreviewed public route; committed endpoint inventory is not stale** |
| 18 | `deploy-config` | Compose config validity; required deployment files present |

Not executed in this environment (CI-only): `pip-audit`, `npm audit`, gitleaks,
Trivy, the PostgreSQL migration replay, the container build.

## 3. Manual evidence recorded during this pass

| Check | Method | Result |
| --- | --- | --- |
| Vulnerability of the old SNS cert-host predicate | Direct comparison of the old suffix test against the new host pin | `attacker-bucket.s3.amazonaws.com` accepted by the old predicate, refused by the new |
| Reset-link tests are meaningful | Stashed the fix, re-ran the suite | 8 of 11 fail without it |
| Quota tests are meaningful | Stashed the route decorators, re-ran | 5 of 11 fail without them |
| Public-route gate is meaningful | Synthetic route asserted in-test | Flagged as expected |
| Route inventory | Generated from `app.url_map` | 280 routes; 171 role-gated, 65 authenticated, 28 scope-gated, 16 allowlisted public |
| Object-level authorization | Reviewed all 15 `require_active_user` routes carrying a path parameter | Every one filters on ownership or an explicit role bypass set |
| Production topology | `Procfile` vs `nginx.conf` vs `docker-compose.yml` | nginx is absent from the Railway path — drove the header and quota work |

## 4. Not yet evidenced — required before production sign-off

| Item | Blocker | Owner |
| --- | --- | --- |
| DAST (ZAP baseline) against a running instance | Needs an authorized isolated environment | Security |
| Alert delivery from the CloudWatch alarms in `infra/terraform/detection.tf` | Needs live AWS | Ops |
| `verify_chain` scheduled run plus failure alerting | Depends on GAP-09 configuration | Ops |
| Backup restore drill, RTO/RPO measurement | Needs production-adjacent infrastructure | Ops |
| Rollback drill | Needs staging | Ops |
| Tabletop exercise | Needs human participants | Security + Ops |
| Load, spike and soak tests | Phase 12 authorization | Security |
| Post-configuration re-verification of GAP-07/08/09 | Requires the env vars to be set | Ops, then Security |

## 5. Phase 12 — authorization required before any active testing

Not performed. Penetration and resilience testing must not begin until the
following are agreed in writing:

- target: an isolated environment with **synthetic data only**, never production;
- accounts: purpose-created at each role level, disabled afterwards;
- rates and tool list, with an explicit ceiling;
- window, monitoring in place, named emergency contact;
- stop conditions: any scope crossing, any availability impact, any contact with
  production, any real AWS spend.

**Prohibited regardless of authorization:** uncontrolled volumetric testing,
destructive payloads, credential attacks against real accounts, production data
extraction, and anything that bills production AWS.
