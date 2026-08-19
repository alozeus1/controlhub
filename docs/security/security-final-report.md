# ControlHub — Security Final Report

Branch `security-gauntlet-controlhub`, baseline `d3a4298`.
Six controls, no schema migration, nothing deployed.

**The six code controls are already on `main`** as squash commit `51dfce8`
(PR #30), which merged while this branch was still open. This branch now carries
only the security artifacts in `docs/security/`. Three further commits in the
branch history (`f9af41c`, `075e8bf`, `2222084`) came from a concurrent process
and are not part of this pass — see the branch-history note in
[security-loop-state.md](security-loop-state.md).

---

## FINAL STATUS: HOLD — SECURITY BLOCKERS REMAIN

Three **High**-severity findings are unresolved. None is a code defect — each is a
implemented, tested control that stays **inert until an operator sets an
environment variable in the Railway environment**, which this pass is explicitly
not authorized to do. Until they are set and re-verified, the deployed posture is
materially weaker than the code suggests.

| Blocker | Effect while unresolved |
| --- | --- |
| **GAP-07** `JIT_ELEVATED_PERMISSIONS` empty | `require_elevation` is a no-op on all 13 routes that carry it. A stolen admin session — the threat model's primary adversary — keeps standing power over secrets, roles and SSO configuration |
| **GAP-08** `SECRET_KMS_KEY_ID` unset | Secrets are encrypted under a locally derived Fernet key. Reading one does not require a CloudTrail-logged `kms:Decrypt`, so decryption is neither externally auditable nor independently revocable |
| **GAP-09** `AUDIT_MIRROR_SINK=none` | The audit log exists only where a compromised application can reach it. The hash chain detects edits; nothing detects truncation or loss |

`config.py` warns about all three in production but does not refuse to boot, so a
deploy can proceed silently without them.

Additionally, three completion criteria cannot be satisfied from this
environment: rollback and alert-delivery drills (GAP-12), authorized DAST
(GAP-11), and human security review.

---

## 1. What was implemented

| # | Control | Severity closed | Commit |
| --- | --- | --- | --- |
| 1 | **SNS/SES inbound trust boundary.** Signing-certificate host pinned to `sns.<region>.amazonaws.com[.cn]` over HTTPS; `SubscribeURL` host-pinned with redirects refused; topic binding fails closed in production; message age bounded; SignatureVersion 2 supported and unknown versions refused; LocalStack short-circuit disabled in production; transient-bounce path made idempotent | Critical + 2 High | `fe7ccb5` |
| 2 | **Baseline CI gate cleared.** Four flake8 findings fixed at source, ignore list not widened | Low (release-blocking) | `d1c6e5e` |
| 3 | **Password-reset link origin from configuration**, never from the `Host` header | High | `3289820` |
| 4 | **Endpoint inventory generated from the URL map, gated in CI.** 280 routes; every route without an auth decorator must be allowlisted with a reason | Medium (systemic) | `28b549d` |
| 5 | **Per-identity quotas on 10 bulk-export and cost-bearing routes**, keyed on principal rather than source address | Medium-High | `2852b59` |
| 6 | **CSP and HSTS emitted by the application**, because nginx is not in the Railway path | Medium | `c68f3be` |

The two highest-value findings both came from one question — *what does the
deployed topology actually run?* The `Procfile` starts gunicorn directly, so the
header policy and rate-limit zones written in `nginx.conf` were never active in
production. Any control documented as living in nginx should be re-checked against
that fact.

## 2. Validation performed

| Gate | Baseline `d3a4298` | After the six controls |
| --- | --- | --- |
| `pytest tests/ -q` | 264 passed | **335 passed** |
| flake8 (CI selection) | **FAIL — 4 findings** | pass |
| `dump_endpoint_inventory.py --check` | n/a | pass — 0 unreviewed public routes |
| admin-ui lint / test / build | pass | pass (untouched) |

**Each fix was proved by removing it and watching the tests fail** — a passing
test on new code proves nothing about the bug it claims to fix:

- old SNS cert-host predicate accepts `attacker-bucket.s3.amazonaws.com`; the new
  host pin refuses it;
- 8 of 11 reset-link tests fail against the previous implementation;
- 5 of 11 quota tests fail with the route decorators removed;
- the public-route gate flags a synthetic unregistered route.

**Not run here** (CI-only): `pip-audit`, `npm audit`, gitleaks, Trivy filesystem
and image scans, the PostgreSQL migration replay, the container build. They are
unchanged by this pass apart from the added `endpoint-surface` job.

## 3. Completion criteria

| # | Criterion | State |
| --- | --- | --- |
| 1 | Endpoint, asset, data and trust inventories complete | ✅ Generated and CI-gated |
| 2 | Every sensitive route has tested server-side auth and object/function authorization | ✅ Code sound; enforcement of step-up is blocked on GAP-07 |
| 3 | Cross-user, cross-role and entitlement-bypass attacks fail safely | ✅ 15 object-level routes verified; existing negative tests cover them |
| 4 | Inbound event verification and delivery ordering durable and tested | ✅ `fe7ccb5` |
| 5 | Restricted data has quota, export and abuse guardrails | ✅ `2852b59` |
| 6 | Configuration and agent operations have provenance, validation, egress limits, rollback | ⚠️ Code complete; GAP-08 open |
| 7 | Rate limits, cost containment, blocking policy, emergency controls evidenced | ⚠️ Limits and kill switches yes; **no WAF exists** — recorded honestly, not simulated. GAP-10, GAP-13 open |
| 8 | TLS, at-rest encryption, secret custody, backup recovery evidenced | ❌ GAP-08 open; restore drill not performed (GAP-15) |
| 9 | CI security checks, migration replay, frontend suite, authorized DAST pass | ⚠️ CI gates in place and extended; DAST not authorized (GAP-11) |
| 10 | No unresolved Critical/High without authorized, expiring risk acceptance | ❌ **GAP-07, GAP-08, GAP-09** |
| 11 | Rollback and incident alerts tested | ❌ GAP-12 |
| 12 | Human security review complete | ❌ Not started |

## 4. Residual risks

**High — awaiting operator action.** GAP-07, GAP-08, GAP-09. Each is a one-line
environment change plus a verification step; GAP-08 additionally needs
`flask secrets rewrap`, which is safe to run incrementally because ciphertexts are
self-describing.

**Medium.**
- GAP-10 — RQ queue depth unbounded; a send flood delays operational mail. Also
  recorded as P2-4 in `docs/PRODUCTION_READINESS_AUDIT.md`.
- GAP-13 — no global `default_limits`; 257 of 280 routes have no explicit quota,
  and every new route defaults to unlimited. Needs a measured request profile
  before a blanket default is safe.
- GAP-11, GAP-12 — no DAST, no alert-delivery test, no tabletop on record.
- **No WAF and no VPC.** Volumetric absorption is entirely Railway's, and is not
  configurable from this repository. No amount of application work changes this;
  it is a platform decision to accept or to change.
- **AWS credential theft from the Railway environment** remains the largest single
  residual risk, as the existing design document already states. The split IAM
  users in `infra/terraform/iam.tf` limit blast radius but cannot prevent it.

**Low.**
- GAP-14 — `hr_admin` (level 80) satisfies `require_role("admin")` while its
  default permission set excludes the Security group, so level-gated and
  permission-gated routes disagree for that role. Intentional in the code;
  confirm with the product owner.
- GAP-15 — backup restore, RTO/RPO and recovery access documented but not drilled.

## 5. One deviation from the brief, stated plainly

The brief asked for a `ddos-abuse-plan.md` covering a Vercel edge firewall,
country/subdivision geofencing and WAF challenge mode. **ControlHub has none of
that infrastructure.** Writing a plan for controls that do not exist would have
produced a document that reads as coverage while providing none. The artifact was
delivered as `abuse-and-availability-plan.md`, which states the absence
explicitly, documents what actually protects each layer, and records the
unprotected layer as a platform gap. The Phase 8 blocking requirements were
retained in the refactored prompt for the day a firewall is introduced.

Likewise, the payments/subscriptions phase was re-based onto webhook and event
integrity: ControlHub has no payment processor, and the equivalent
integrity-critical inbound path is SES/SNS — which is where the Critical finding
turned out to be.

## 6. Recommended next step

Hand GAP-07, GAP-08 and GAP-09 to whoever owns the Railway environment. They are
the highest-value remaining actions, they are not code changes, and all three are
already implemented and tested. Then re-run
`tests/test_zero_trust_phase3.py` against the deployed configuration to confirm
elevation actually enforces, and schedule `verify_chain` with alerting.

After that, GAP-10 (queue bound) is the next code-side control worth landing.

---

**FINAL STATUS: HOLD — SECURITY BLOCKERS REMAIN**
