# ControlHub — Security Loop Checkpoint

Resume file. Read this plus `git log d3a4298..HEAD` and the gap register; nothing
else is needed to continue.

## Position

| | |
| --- | --- |
| Branch | `security-gauntlet-controlhub` |
| Baseline | `d3a4298` — carried-over zero-trust phase 1–4 work, unmodified |
| Head | `c68f3be` |
| Controls landed | 6 |
| Suite | 335 passing (264 at baseline) |
| Local gates | flake8 clean; `dump_endpoint_inventory.py --check` exit 0 |
| Not run locally | pip-audit, npm audit, gitleaks, Trivy, PostgreSQL migration replay, container build — CI-only |
| Deployed | **Nothing.** No merge, no deploy, no key rotation, no production config change |

## Phase status

| Phase | State |
| --- | --- |
| 0 Baseline and architecture | **Complete** — `security-baseline.md` |
| 1 Endpoint / data / trust inventory | **Complete** — `endpoint-inventory.md`, generated and CI-gated |
| 2 Threat model and ranking | **Complete** — `threat-model.md` |
| 3 Zero-trust identity and authorization | **Reviewed, sound in code.** 15 object-level routes verified; the enforcement gap is configuration (GAP-07), not code |
| 4 API / browser / application | **Advanced** — headers closed (`c68f3be`); SSRF, sanitisation, CORS, error handling already in place |
| 5 Webhooks and event integrity | **Closed** — `fe7ccb5` |
| 6 Secrets / config / agent integrity | **Code complete, configuration open** — GAP-08 |
| 7 Abuse and denial-of-wallet | **Advanced** — `2852b59`; GAP-10 and GAP-13 open |
| 8 Network policy and blocking | **Documented as absent.** No WAF exists; recorded honestly in `abuse-and-availability-plan.md` rather than simulated |
| 9 Encryption and secrets | **Code complete, configuration open** — GAP-08 |
| 10 CI/CD and supply chain | **Advanced** — 18 gates; `endpoint-surface` added |
| 11 Logging and detection | **Code complete, delivery unverified** — GAP-09, GAP-12 |
| 12 Controlled penetration testing | **Not started — authorization required** |

## Controls landed

| Commit | Control | Proof that it works |
| --- | --- | --- |
| `fe7ccb5` | SNS cert-host pin, message-age bound, topic fail-closed, confirm-SSRF block, SHA256 support, transient-bounce idempotency | Old predicate accepts `attacker-bucket.s3.amazonaws.com`; new one refuses. 21 tests |
| `d1c6e5e` | Baseline flake8 gate cleared at source | flake8 exit 0 |
| `3289820` | Reset-link origin from config | 8 of 11 tests fail against the old code |
| `28b549d` | Generated endpoint inventory + CI surface gate | Gate fires on a synthetic route; 0 unreviewed public routes |
| `2852b59` | Per-identity quotas on 10 export/agent routes | 5 of 11 tests fail with the limits removed |
| `c68f3be` | App-level CSP + HSTS (nginx is not in the Railway path) | 16 tests |

## Reusable evidence — do not re-derive

- **Production topology:** the `Procfile` runs gunicorn directly on Railway.
  `nginx.conf` applies **only** to docker-compose. Anything expressed only in
  nginx — headers, `limit_req` — is absent in production.
- **No payment provider, no sports data, no Vercel, no WAF, no VPC.** The
  original prompt's payment and edge-firewall phases were re-based onto webhook
  integrity and application-layer abuse controls respectively.
- **Tenancy is effectively single-organisation.** `org_id` appears on one model;
  isolation is by role and ownership, not by tenant. Do not write cross-tenant
  tests for a boundary that does not exist.
- **Route posture:** 280 routes — 171 role-gated, 65 authenticated, 28
  scope-gated, 16 allowlisted public (4 of those authenticate in-handler).
- **Object-level authorization:** all 15 `require_active_user` routes with a path
  parameter filter on ownership. Already covered by
  `test_saas_phase2.py`, `test_saas_employee_reviews.py`, `test_saas_poc.py`.
  **This ground is covered — do not re-audit it.**
- **Role model:** 8 levels; unknown role ⇒ level 0 ⇒ denied. `hr_admin` (80)
  outranks `admin` (50) by level but holds a narrower permission set — that
  asymmetry is intentional (GAP-14).
- **Regenerate the inventory** after adding any route:
  `python3 scripts/dump_endpoint_inventory.py` — CI fails on drift.
- **Test command:**
  `SQLALCHEMY_DATABASE_URI="sqlite:///:memory:" FLASK_APP=wsgi.py ALLOW_TEST_DATABASE_RESET=true python3 -m pytest tests/ -q`
- `email_env` is a **local** fixture in `test_campaigns.py`, not in `conftest.py`;
  duplicate it when writing campaign tests.
- The limiter is live in tests (`RATELIMIT_STORAGE_URL=memory://` in conftest), so
  quota tests work without Redis.

## Next safest actions, in order

1. **Hand GAP-07/08/09 to Ops.** Three implemented, tested controls are inert
   until environment variables are set. This is the highest-value remaining
   action and it is not a code change.
2. **GAP-10 — bound the RQ queue.** Depth check before enqueue, retry/backoff,
   dead-letter. Needs a load figure; drill with a synthetic flood in staging.
3. **GAP-13 — measure then set `default_limits`.** Profile per-endpoint p99 call
   rates in staging first; a blind global default risks tripping SPA bursts.
4. **GAP-11/12 — DAST, alert-delivery test, tabletop.** All require
   authorization or live infrastructure.
5. **GAP-14 — confirm the `hr_admin` level/permission asymmetry** with the
   product owner; prefer `require_permission` for new security-sensitive routes.

## Discipline notes for the next iteration

- Two of the six controls were found by asking "what does the deployed topology
  actually run?" rather than by reading a route. That question paid twice; ask it
  again before trusting any control documented as living in nginx.
- Every fix here was proved by removing it and watching the tests fail. Keep
  doing that — a passing test on new code proves nothing about the bug.
- Do not fabricate findings in well-covered areas. Object-level authorization and
  the API-key/scope model were examined and found sound; that was recorded as a
  result, not converted into busywork.
