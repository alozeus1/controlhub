# ControlHub — Security Gap Register

Branch `security-gauntlet-controlhub`, baseline `d3a4298`.
Severity uses OWASP-style qualitative ranking: Critical / High / Medium / Low.

## Closed in this pass

### GAP-01 — SNS signing-certificate host bypass ⇒ arbitrary SES event forgery
| | |
| --- | --- |
| **Severity** | Critical |
| **Evidence** | `app/services/email_ses.py` accepted any signing-certificate URL whose host ended in `.amazonaws.com`. Demonstrated: the old predicate accepts `attacker-bucket.s3.amazonaws.com`; the replacement does not. |
| **Attack path** | Attacker publishes a PEM to a public S3 bucket, signs a forged SES `Bounce`/`Complaint` notification with the matching private key, POSTs it to the unauthenticated `/email/webhooks/ses`. Verification passes. The event suppresses any address they name — including addresses that receive password-reset mail, making it a denial of account recovery. |
| **Fix** | Host pinned to `sns.<region>.amazonaws.com[.cn]`, HTTPS required. `SignatureVersion` 2 (SHA256) supported; unknown versions refused rather than treated as SHA1. LocalStack short-circuit no longer applies when `FLASK_ENV` is production. |
| **Test** | `tests/test_sns_webhook_trust.py` — 7 rejected cert-URL shapes, 3 accepted, version handling, production short-circuit |
| **Rollout / rollback** | Code-only. Revert `fe7ccb5`. |
| **Commit** | `fe7ccb5` |

### GAP-02 — Password-reset link origin taken from the `Host` header
| | |
| --- | --- |
| **Severity** | High |
| **Evidence** | `app/routes/auth.py` built `reset_url` from `request.host_url`. nginx uses catch-all `server_name _` and forwards `Host $host`; ProxyFix additionally trusts `X-Forwarded-Host`. |
| **Attack path** | One unauthenticated `POST /auth/forgot-password` for a victim's address with `Host: evil.example.com`. The victim receives a genuine ControlHub email; clicking the link sends the single-use reset token to the attacker. Full account takeover, no interaction with the victim's session required. |
| **Fix** | Origin resolved from `UI_BASE_URL` then `PUBLIC_BASE_URL`. If neither is set, no mail is sent and the error is logged; the response stays uniform so enumeration is still impossible. Deployed environments still pointing at localhost log an error. |
| **Test** | `tests/test_password_reset_link_origin.py` — 11 cases; 8 fail against the previous implementation |
| **Rollout / rollback** | `UI_BASE_URL` is optional. Revert `3289820`. |
| **Commit** | `3289820` |

### GAP-03 — SSRF via SNS `SubscribeURL`
| | |
| --- | --- |
| **Severity** | High |
| **Evidence** | `urlopen(sub_url, timeout=5)` on a request-body value, with no host validation and redirects followed. |
| **Attack path** | Combined with GAP-01, or with the attacker's own SNS topic, the confirmation handshake becomes a server-side fetch of any URL — internal services, link-local metadata — from inside the app's network position. |
| **Fix** | `confirm_sns_subscription` validates against the same host pin and refuses redirects; response body is size-capped. |
| **Test** | `tests/test_sns_webhook_trust.py` — 5 SSRF targets refused, route returns 400 |
| **Commit** | `fe7ccb5` |

### GAP-04 — Unbounded bulk extraction and AI-agent invocation
| | |
| --- | --- |
| **Severity** | Medium-High |
| **Evidence** | Ten routes had no rate limit: audit-log export, people CSV export, env-config export, `audit-exports/now` and `/run`, agent request create and run, artifact presign, download, publish to Drive and Sheets. `default_limits=[]`, so nothing applied globally. |
| **Attack path** | A stolen `viewer` session loops the exports to extract the whole audit trail, HR roster and every environment configuration — each call a full table scan. The agent routes bill model and AWS spend per call, making an unbounded loop a denial-of-wallet primitive. |
| **Fix** | Per-identity quotas via `app/utils/rate_limit.py::identity_rate_key`, resolving API key → JWT subject → IP. Per-IP alone was both too coarse (shared office egress) and too loose (rotating source addresses). API keys are SHA-256 hashed into the bucket name so the credential never reaches Redis keyspace. |
| **Test** | `tests/test_export_and_agent_quotas.py` — 11 cases; 5 fail with the limits removed |
| **Rollout / rollback** | Limits are decorator-level. If a legitimate workflow trips one, raise that decorator's value rather than removing the key function. Revert `2852b59`. |
| **Commit** | `2852b59` |

### GAP-05 — No CSP or HSTS on the deployed origin
| | |
| --- | --- |
| **Severity** | Medium |
| **Evidence** | The full header policy existed only in `nginx.conf`. The `Procfile` — what Railway runs — starts gunicorn directly, so no proxy was adding Content-Security-Policy or Strict-Transport-Security in production. The app's own hook set five headers and neither of those. |
| **Fix** | Both emitted by `app/utils/security_headers.py`, mirroring nginx's policy so the two origins cannot disagree. HSTS only over TLS (`request.is_secure`), with an `HSTS_ALWAYS` override. Added `Cross-Origin-Opener-Policy` and `X-Permitted-Cross-Domain-Policies`; extended `no-store` to `/email` and `/features`. Headers set only when absent, so a proxy's stricter value wins and browsers never intersect two policies. |
| **Test** | `tests/test_security_headers.py` — 16 cases |
| **Commit** | `c68f3be` |

### GAP-06 — A new route could ship without an authentication decorator
| | |
| --- | --- |
| **Severity** | Medium (systemic) |
| **Evidence** | 280 routes across 33 blueprints, no mechanism asserting that each is authenticated. The realistic failure is omission, not intent. |
| **Fix** | `scripts/dump_endpoint_inventory.py` derives the inventory from `app.url_map` plus an AST parse of the decorator stacks. Any route without an auth decorator must be in `PUBLIC_ALLOWLIST` with a reason. Enforced by `tests/test_public_route_allowlist.py` (runs in both backend jobs, and asserts the gate fires on a synthetic route) and the new `endpoint-surface` CI job, which also fails on inventory drift. All 16 current public routes were individually reviewed and justified. |
| **Commit** | `28b549d` |

### GAP-00 — Baseline CI failure: four flake8 findings
| | |
| --- | --- |
| **Severity** | Low (release-blocking) |
| **Evidence** | `backend-lint` selects F401/F811/F841/E722/E999/F823 and failed on four findings in the carried-over `tests/test_zero_trust_phase{1,2,3,4}.py`. A **baseline failure, not a regression.** |
| **Fix** | Fixed at source — unused imports removed, an unused binding dropped while keeping the fixture call, and a never-consumed literal replaced by a statement of what the surrounding assertions actually prove. The ignore list was not widened. |
| **Commit** | `d1c6e5e` |

## Open — deployment configuration, requires human action

These are not code defects. Each control is implemented and tested; each is
**inert until an operator sets an environment variable in Railway.** `config.py`
prints a warning in production but does not refuse to boot, so a deploy can
silently proceed without them. Making them fatal is a deployment decision and is
outside what this pass should decide unilaterally.

### GAP-07 — Just-in-time elevation is off by default
| | |
| --- | --- |
| **Severity** | High |
| **Evidence** | `JIT_ELEVATED_PERMISSIONS` defaults to empty, and `require_elevation` is documented as "a no-op unless the key is listed". Thirteen routes carry the gate — including secret reveal, role change and SSO config — and none of them enforce step-up until the variable names the permission. |
| **Consequence** | The primary adversary in the threat model (a stolen admin session) retains standing power over secrets and roles. |
| **Required action** | Set `JIT_ELEVATED_PERMISSIONS` to at least `manage_secrets,manage_roles,manage_sso,manage_org_settings`; set `JIT_DUAL_APPROVAL_PERMISSIONS` for the broadest keys; set `JIT_REQUIRE_MFA=true`. Verify with `tests/test_zero_trust_phase3.py` against the deployed configuration. |

### GAP-08 — `SECRET_KMS_KEY_ID` unset ⇒ secrets under a derived local key
| | |
| --- | --- |
| **Severity** | High |
| **Evidence** | `app/services/secret_crypto.py` falls back to a Fernet key derived locally when no KMS key is configured. `config.py:228` warns in production. |
| **Consequence** | Reading a secret no longer requires a CloudTrail-logged `kms:Decrypt`, so decryption is neither externally auditable nor independently revocable. |
| **Required action** | Provision the KMS key from `infra/terraform/kms.tf`, set `SECRET_KMS_KEY_ID`, then run `flask secrets rewrap` to migrate stored `fernet:v1:` values to `kms:v1:`. Ciphertexts are self-describing, so both formats read correctly during migration. |

### GAP-09 — Audit mirror off by default ⇒ audit log inside the blast radius
| | |
| --- | --- |
| **Severity** | High |
| **Evidence** | `AUDIT_MIRROR_SINK` defaults to `none`; `config.py:239` warns in production. |
| **Consequence** | The hash chain detects tampering, and the append-only grant in `scripts/sql/audit_log_append_only.sql` blocks it at the database — but the log still lives only where a compromised application can reach it. Truncation or wholesale loss is undetectable without an external copy. |
| **Required action** | Configure the mirror sink to the CloudWatch log group in `infra/terraform/audit.tf`, apply the append-only grant, and schedule `verify_chain` with alerting on failure. |

## Open — not addressed in this pass

| ID | Severity | Gap | Why deferred | Next step |
| --- | --- | --- | --- | --- |
| GAP-10 | Medium | No RQ queue-depth bound or dead-letter policy. A flood of enqueued sends can exhaust the worker and delay operational mail. Already noted as P2-4 in `docs/PRODUCTION_READINESS_AUDIT.md`. | Touches the worker's runtime behaviour; needs a load figure to size the bound, and this pass must not change send semantics unverified. | Add a depth check before enqueue plus retry/backoff and a dead-letter queue; drill with a synthetic flood in staging. |
| GAP-11 | Medium | No automated DAST against a running instance. | Requires an authorized isolated environment; Phase 12 is authorization-gated. | Run ZAP baseline against staging once authorized. |
| GAP-12 | Medium | Alert delivery and the rollback drill are untested; no tabletop exercise on record. | Needs live AWS and human participants. | Execute before production sign-off. |
| GAP-13 | Low-Medium | No global `default_limits`. 257 of 280 routes still have no explicit quota, and each new route defaults to unlimited. | A blanket default risks tripping legitimate SPA burst traffic; needs a measured request profile first. | Measure per-endpoint p99 call rates in staging, then set a generous global default and tighten per route. |
| GAP-14 | Low | `hr_admin` (level 80) satisfies `require_role("admin")` while its default permission set excludes the Security group, so level-gated and permission-gated routes disagree for that role. | Intentional per the code's design; changing it is a product decision about what HR admins may reach. | Confirm intent with the product owner; prefer `require_permission` for new security-sensitive routes. |
| GAP-15 | Low | Backup restoration, RTO/RPO and recovery access are documented in `docs/BACKUP_AND_RESTORE_RUNBOOK.md` but not evidenced by a test restore. | Requires production-adjacent infrastructure. | Perform and record a restore drill. |
