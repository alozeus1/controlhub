# ControlHub — Abuse and Availability Plan

**ControlHub has no managed WAF and no VPC.** The API and worker are Railway
containers; AWS supplies SES, SNS, S3, KMS, CloudWatch and CloudTrail only. The
`nginx.conf` `limit_req` zones apply in the docker-compose topology, not on
Railway, where the `Procfile` starts gunicorn directly. Any plan that assumes a
cloud firewall in front of this application is wrong, so this one does not.

Volumetric absorption is therefore Railway's edge, which is not configurable from
this repository. Everything else is the application's responsibility.

## 1. Layers

| Layer | Controls in place | Proof | Gaps |
| --- | --- | --- | --- |
| Railway edge | Platform TLS termination and whatever volumetric handling Railway provides | Provider-side; not configurable here | No WAF rules, no IP/CIDR blocking, no challenge mode. A volumetric attack is absorbed or it is not |
| nginx (compose only) | `limit_req` auth 10 r/m, api 100 r/m; timeouts; header policy | `nginx.conf` | **Not in the production path** |
| Application throttle | `flask-limiter` on Redis; 23 routes; **per-identity** buckets on export and agent routes | `tests/test_export_and_agent_quotas.py` | `default_limits=[]` — 257 routes have no explicit quota (GAP-13) |
| Business flows | Agent daily row-export budget; approval thresholds; destination pinning; suppression list | `test_zero_trust_phase4.py` | — |
| Cost containment | SES send caps (10/min, 30/hour test); agent quotas; CloudWatch alarms in `infra/terraform/detection.tf` | Terraform | Alarm delivery untested (GAP-12) |
| Operations | Runbooks in `docs/` | `MIGRATION_AND_ROLLBACK_RUNBOOK.md`, `BACKUP_AND_RESTORE_RUNBOOK.md` | No abuse-specific runbook; no tabletop on record (GAP-12) |

## 2. Route-level quotas

| Surface | Limit | Bucket | Rationale |
| --- | --- | --- | --- |
| `POST /auth/login` | 10/min | IP | Credential stuffing |
| `POST /auth/forgot-password` | 5/min | IP | Reset flooding, enumeration |
| `POST /auth/reset-password` | 5/min | IP | Token brute force |
| `POST /auth/mfa/login-verify` | 10/min | IP | Second-factor brute force (plus lockout) |
| `POST /auth/mfa/verify` | 10/min | IP | Enrollment abuse |
| `POST /admin/elevation/request` | 10/min | IP | Elevation spam |
| `GET /admin/search` | 60/min | IP | Expensive query |
| `/admin/secrets*` | 20/min | IP | Restricted data |
| `GET /admin/audit-logs/export` | **20/hour** | **identity** | Whole-audit-trail extraction |
| `GET /admin/people/export/csv` | **20/hour** | **identity** | HR roster extraction |
| `GET /admin/env-projects/<id>/export` | **30/hour** | **identity** | Environment-configuration extraction |
| `POST /admin/audit-exports/now` | **10/hour** | **identity** | Full-export job spam |
| `POST /admin/audit-exports/<id>/run` | **20/hour** | **identity** | Same |
| `POST /admin/agent-requests` | **30/hour** | **identity** | Model spend |
| `POST /admin/agent-requests/<id>/run` | **20/hour** | **identity** | Model spend |
| `POST /admin/generated-artifacts/<id>/presign` | **60/hour** | **identity** | S3 egress |
| `GET /admin/generated-artifacts/<id>/download` | **120/hour** | **identity** | S3 egress |
| `POST .../publish/{drive,sheet}` | **30/hour** | **identity** | Third-party API spend |
| `POST /admin/email/campaigns/<id>/send` | 10/min | IP | SES spend and reputation |
| `POST /admin/email/campaigns/<id>/test` | 30/hour | IP | Same |
| `GET /admin/feature-flags/sdk/<project>` | 60/min | IP | SDK polling |

**Why identity, not IP, on the expensive routes.** Per-IP is simultaneously too
coarse and too loose here: every operator behind one office egress address shares
a bucket, so an ordinary admin can throttle their colleagues out of an export;
and a caller with a pool of source addresses gets a fresh quota on every hop.
`app/utils/rate_limit.py::identity_rate_key` resolves API key → JWT subject → IP,
reading the credential directly because flask-limiter evaluates limits before the
view's auth decorator runs. Service-account keys are SHA-256 hashed into the
bucket name so the raw credential never reaches Redis keyspace or a slow log.

## 3. Denial-of-wallet inventory

| Cost driver | Bound | Residual |
| --- | --- | --- |
| SES sends | Per-route limits; suppression list; separate transactional identity so campaign complaints cannot stop password-reset mail | SES account sending quota is the real ceiling; no per-day app-level cap |
| S3 storage and egress | Presign and download quotas | No lifecycle policy asserted in code |
| AI model invocation | Agent create/run quotas plus the daily row-export budget | No monetary budget check |
| KMS `Decrypt` calls | Secret-route limits | Cost is negligible; CloudTrail volume is the real signal |
| CloudWatch ingestion | — | Audit mirror volume is unbounded once GAP-09 is configured |
| RQ queue | — | **No depth bound (GAP-10)** |

## 4. Detection signals

Available today from `app/utils/audit.py` and the audit chain:

- repeated `login` failures per email and per source address;
- `api_key.denied_scope` — a service account probing outside its scope;
- `privilege.denied`, `privilege.reauth_failed` — elevation probing;
- elevation grant and approval events;
- secret reveal and `SecretAccessLog` rows;
- `verify_chain` failure — the strongest single tamper signal;
- 429 volume per identity (limiter), which distinguishes an abusive principal
  from a noisy address.

CloudWatch metric filters and four alarms exist in `infra/terraform/detection.tf`.
Their delivery is unverified (GAP-12).

## 5. Emergency controls

| Situation | Action | Owner |
| --- | --- | --- |
| Compromised operator account | Disable the user (`is_active=false`) — every protected route re-checks it per request — then bump the session epoch | Security admin |
| Compromised service account | Revoke the API key or disable the account; `require_scope` rejects immediately | Security admin |
| Compromised SDK key | Revoke; wrong-project and revoked keys are rejected identically | Admin |
| SES abuse or reputation event | `SES_SENDING_ENABLED=false` — a dry-run kill switch already in config | Ops |
| Agent runaway spend | Feature-flag `FEATURE_AGENT_SERVICE=false` | Ops |
| Module under attack | Disable that module's feature flag | Ops |
| Volumetric attack | Escalate to Railway; no in-repo edge control exists | Ops + provider |

Every kill switch above is a configuration change, not a deploy.

## 6. Rollout discipline for new restrictions

New limits and blocking policy go out in report-only or feature-flag mode first,
false positives are measured, and only then is enforcement enabled. The quotas
added in this pass were deliberately set well above observed legitimate use
(hourly, not per-minute) so the first deployment cannot lock out an operator
mid-task; the correct response to a tripped limit is to raise that decorator's
value, never to remove the key function.

No uncontrolled load or volumetric testing against production. Any load test
requires the Phase 12 authorization in
[security-test-plan.md](security-test-plan.md).
