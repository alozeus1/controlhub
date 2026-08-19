# ControlHub — Threat Model

Scope: the deployed ControlHub API, worker, SPA and their AWS dependencies.
Baselines: OWASP Top 10:2025, OWASP API Security Top 10:2023, ASVS L2,
NIST SP 800-207.

## 1. Assets, by classification

| Class | Assets |
| --- | --- |
| **Restricted** | Secret values and env-config ciphertext; KMS key material and data keys; service-account API key hashes; MFA seeds; SSO client secret; the hash-chained audit log; AWS credentials in the Railway environment; agent tool credentials; Google WIF configuration |
| **Confidential** | People/HR records, employment, performance and biweekly reviews; incidents; certificates; licenses; cost data; subscriber lists and campaign content |
| **Internal** | Runbooks, deployments, workflows, feature flags, assets/CMDB, notifications |
| **Public** | Health and readiness probes, module on/off flags, the static landing page, SSO display metadata |

## 2. Actors

| Actor | Capability |
| --- | --- |
| Anonymous internet | 16 allowlisted public routes |
| `user` (1) | Own notifications, own self-review, own onboarding items |
| `viewer` (10) | Read-only admin console, audit log read, global search, exports |
| `mentor` (20) / `team_lead` (30) | Viewer plus intern review participation |
| `people_manager` (40) | Plus `manage_users` |
| `admin` (50) | All permissions except those reserved to superadmin |
| `hr_admin` (80) | Outranks admin by level but holds a *narrower* default permission set |
| `superadmin` (100) | Everything |
| Service account | Scope-gated API routes only; never granted a human role |
| RQ worker | Campaign sends, scheduled jobs; runs with the app's own credentials |
| AI agent | Constrained egress to allowlisted destinations |

**Primary adversary (per the assume-breach design): a stolen `admin` or
`superadmin` session.** Standing privilege, not perimeter penetration, is the
dominant risk in an internal control plane.

## 3. Trust boundaries

1. Internet → nginx (compose) **or directly → gunicorn (Railway)**. The second
   path is the production one and has no proxy in front, which is why header and
   rate-limit policy must live in the application.
2. Browser → API. The SPA is untrusted; role, permission and feature entitlement
   are re-derived server-side on every request.
3. API → PostgreSQL / Redis / S3. Compromise of the app process implies these.
4. AWS → API (inbound SNS). Signature-verified and topic-bound; **hardened this
   pass**.
5. API → AWS / Google / n8n / webhook destinations. Outbound, SSRF-guarded.
6. CI → Railway. Deployment identity; secret exposure here is a full compromise.

## 4. Abuse cases and mitigations

### 4.1 Identity and authorization

| Abuse case | Mitigation | Evidence |
| --- | --- | --- |
| Forged role/permission in a request header or body | Never read from the request; derived from the JWT subject and DB row | `rbac.py`, `permissions.py` |
| API key used on a human endpoint | `require_role` rejects `X-API-Key` outright | `test_api_key_scopes.py` |
| Service account impersonating its creator | `require_scope` sets `current_user = None` | `rbac.py:require_scope` |
| Cross-user object access on self-service routes | Ownership filter in the query | 15 candidate routes reviewed; all check ownership. `test_saas_phase2.py`, `test_saas_employee_reviews.py` |
| Unknown/legacy role string grants access | `ROLE_LEVELS.get(role, 0)` ⇒ denied | `models.py:44` |
| Revoked/expired token still accepted | Fail-closed revocation; epoch bump on reset | `test_jwt_revocation.py`, `session_security.py` |
| Refresh-token replay | Family rotation; replay kills the family | `auth.py:refresh` |
| Privilege escalation by self-elevation | Elevation activates only a permission the role already implies | `test_zero_trust_phase3.py` |
| Self-approval of an elevation | Refused; approver must hold the permission | `test_zero_trust_phase3.py` |
| **Standing admin power** | JIT elevation — **opt-in, off by default** | **GAP-07** |

### 4.2 Account takeover

| Abuse case | Mitigation | Evidence |
| --- | --- | --- |
| Credential stuffing | 10/min per IP on login; MFA | `auth.py` |
| Account enumeration via reset | Uniform response | `test_password_reset_link_origin.py` |
| **Reset-token theft via forged `Host`** | **Link origin from config only** | **Fixed `3289820`** |
| MFA brute force | 10/min plus lockout | `mfa.py` |
| MFA silently bypassed by an internal error | Login refused (503), not downgraded | `auth.py:login` |

### 4.3 Inbound event forgery

| Abuse case | Mitigation | Evidence |
| --- | --- | --- |
| **Forged SES bounce/complaint ⇒ suppress any address, incl. password-reset mail** | SNS signature verified against a **host-pinned** signing cert | **Fixed `fe7ccb5`** |
| Attacker's own SNS topic accepted | Fails closed when `SNS_TOPIC_ARN` unset in production | Fixed `fe7ccb5` |
| Replay of a captured notification | Message-age bound + per-event uniqueness | Fixed `fe7ccb5` |
| **SSRF via `SubscribeURL`** | Host-pinned, redirects refused | **Fixed `fe7ccb5`** |
| Signature downgrade via unknown `SignatureVersion` | Refused; v1/v2 only | Fixed `fe7ccb5` |
| `EMAIL_PROVIDER=localstack` disabling verification in production | Short-circuit does not apply when `FLASK_ENV` is production | Fixed `fe7ccb5` |
| Unsubscribe-token guessing | Opaque per-subscriber token | `test_campaigns.py` |

### 4.4 Bulk extraction and denial-of-wallet

| Abuse case | Mitigation | Evidence |
| --- | --- | --- |
| **Whole-audit-log / HR-roster / env-config extraction in a loop** | **Per-identity quotas** | **Fixed `2852b59`** |
| **Unbounded AI-agent invocation (model + AWS spend)** | **Per-identity quotas on create/run/presign/publish** | **Fixed `2852b59`** |
| One operator's quota starving colleagues on a shared egress IP | Bucket keyed on principal, not IP | `test_export_and_agent_quotas.py` |
| Quota bypass by rotating source addresses | Same | Same |
| API key leaking into Redis keyspace via the limiter key | SHA-256 hashed bucket name | Same |
| Expensive global search | 60/min | `search.py` |
| SES send flooding | 10/min send, 30/hour test | `campaigns.py` |
| Agent row-export budget | `check_daily_export_budget` | `agent_service.py` |
| Queue flooding | **Not bounded** | GAP-10 |

### 4.5 Application-layer

| Abuse case | Mitigation | Evidence |
| --- | --- | --- |
| SQL injection | SQLAlchemy parameterisation throughout | No raw interpolation found |
| Stored XSS in campaign/runbook HTML | `bleach` allowlist sanitiser | `test_html_sanitizer.py` |
| **Clickjacking / inline-script injection on the deployed origin** | **CSP + frame-ancestors now emitted by the app** | **Fixed `c68f3be`** |
| **TLS downgrade on the deployed origin** | **HSTS now emitted by the app over TLS** | **Fixed `c68f3be`** |
| CORS credential theft | Explicit origin list; production refuses `*` | `config.py:220` |
| SSRF via SSO discovery / webhooks | `safe_http.assert_public_url` | `test_a6_ssrf_guard.py` |
| Response body DoS | `MAX_CONTENT_LENGTH` 64 MiB | `config.py:66` |
| Error-message disclosure | Central handlers | `test_error_handlers.py` |
| Caching of authenticated data | `no-store` on `/auth`, `/admin`, `/email`, `/features` | `test_security_headers.py` |
| **New route shipped without an auth decorator** | **CI gate** | **Fixed `28b549d`** |

### 4.6 Provider, supply chain and insider

| Abuse case | Mitigation | Evidence |
| --- | --- | --- |
| AWS credential theft from the Railway environment | Split IAM users for API vs worker, least privilege | `infra/terraform/iam.tf`; residual risk acknowledged in the design doc |
| Poisoned integration payload | Schema validation on inbound events | `campaigns.py`, `n8n_events.py` |
| Agent output redirected post-approval | Destination fingerprint pinned at approval | `test_zero_trust_phase4.py` |
| Dependency vulnerability | `pip-audit --strict`, `npm audit --audit-level=high` | CI |
| Secret committed | `gitleaks` | CI |
| Container/OS vulnerability | Trivy fs + image, HIGH/CRITICAL, non-root verified | CI |
| **Audit tampering by the compromised app itself** | Hash chain + append-only grant; external mirror **off by default** | **GAP-09** |

## 5. Risk ranking

Ranked by severity × likelihood × blast radius, highest first. Items marked
**fixed** were closed in this pass; see [security-gap-register.md](security-gap-register.md).

1. **Fixed** — SNS signing-cert host bypass ⇒ arbitrary SES event forgery (Critical).
2. **Fixed** — reset-link `Host` injection ⇒ account takeover in one request (High).
3. **Fixed** — `SubscribeURL` SSRF (High).
4. **Open (deployment)** — JIT elevation off by default ⇒ standing admin power (High) — GAP-07.
5. **Open (deployment)** — audit mirror off by default ⇒ audit log inside the blast radius (High) — GAP-09.
6. **Open (deployment)** — `SECRET_KMS_KEY_ID` unset ⇒ secrets under a derived local key (High) — GAP-08.
7. **Fixed** — unbounded bulk export and agent invocation (Medium-High).
8. **Fixed** — no CSP/HSTS on the deployed origin (Medium).
9. **Open** — no queue-depth bound on RQ (Medium) — GAP-10.
10. **Open** — no automated DAST or alert-delivery test (Medium) — GAP-11, GAP-12.
