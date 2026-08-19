# ControlHub — Role and Permission Matrix

Source of truth: `app/models.py::ROLE_LEVELS`, `app/permissions.py::PERMISSION_CATALOG`
and `DEFAULT_ROLE_PERMISSIONS`, `app/utils/rbac.py`. This document restates them;
if it disagrees with the code, the code is right and this file is stale.

## 1. Role levels

`require_role(min_role)` compares `ROLE_LEVELS[user.role] >= ROLE_LEVELS[min_role]`.
An unrecognised role string resolves to level 0 and is therefore denied everywhere —
the hierarchy fails closed.

| Role | Level | Intent |
| --- | --- | --- |
| `superadmin` | 100 | Full system access |
| `hr_admin` | 80 | HR administration. Outranks `admin` by level but holds a narrower default permission set |
| `admin` | 50 | Platform administration |
| `people_manager` | 40 | Manages people records |
| `team_lead` | 30 | PoC for intern biweekly reviews |
| `mentor` | 20 | Mentors interns |
| `viewer` | 10 | Read-only admin console |
| `user` | 1 | Self-service only; no admin console |

**Level vs. permission is a deliberate split.** `hr_admin` at level 80 satisfies
`require_role("admin")` on any role-gated route, while its default permission set
excludes `manage_secrets`, `manage_roles`, `manage_sso` and the rest of the
Security group. Routes protected by `require_permission` therefore behave
differently from routes protected by `require_role` for this role. Any new
security-sensitive route should use the permission gate, not the level gate.

## 2. Permission catalog

| Key | Group | superadmin | hr_admin | admin | people_manager | team_lead | mentor | viewer | user |
| --- | --- | :-: | :-: | :-: | :-: | :-: | :-: | :-: | :-: |
| `view_dashboard` | General | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `global_search` | General | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | — |
| `manage_users` | People | ✅ | ✅ | ✅ | ✅ | — | — | — | — |
| `view_audit_logs` | Security | ✅ | ✅ | ✅ | — | — | — | ✅ | — |
| `manage_secrets` | Security | ✅ | — | ✅ | — | — | — | — | — |
| `manage_certificates` | Security | ✅ | — | ✅ | — | — | — | — | — |
| `manage_roles` | Security | ✅ | — | ✅ | — | — | — | — | — |
| `manage_mfa_policy` | Security | ✅ | — | ✅ | — | — | — | — | — |
| `manage_sso` | Security | ✅ | — | ✅ | — | — | — | — | — |
| `manage_org_settings` | Admin | ✅ | — | ✅ | — | — | — | — | — |
| `manage_integrations` | Admin | ✅ | — | ✅ | — | — | — | — | — |
| `manage_deployments` | DevOps | ✅ | — | ✅ | — | — | — | — | — |
| `manage_email_campaigns` | Marketing | ✅ | — | ✅ | — | — | — | — | — |

Custom roles live in the database (`models_admin.Role`); the table above is the
seeded default. `superadmin` receives all keys implicitly.

## 3. Non-human principals

| Principal | Mechanism | Authorization | Explicitly cannot |
| --- | --- | --- | --- |
| Service account | `X-API-Key`, hashed at rest, expiry + revocation | `require_scope(scope)` — deny-by-default scope match | Reach any `require_role` or `require_active_user` route; it is rejected with `API_KEY_NOT_PERMITTED` before authentication is even attempted. Never inherits its creator's role — `request.current_user` is forced to `None` |
| Feature-flag SDK key | `X-SDK-Key` or `?sdk_key=`, hashed, project-bound | Exact project match | Read another project's flags; missing, revoked and wrong-project keys are rejected identically to avoid an oracle |
| AWS SNS | Signature over the canonical string, host-pinned cert, topic-bound, age-bounded | Event ingestion only | Reach anything but `/email/webhooks/ses`; redirect the confirmation fetch |
| Unsubscribe token | Opaque per-subscriber token | Unsubscribe that subscriber | Enumerate subscribers |
| RQ worker | In-process, app credentials | Campaign sends, scheduled jobs | — (shares the app's blast radius; see GAP-09) |
| AI agent | Approval-pinned destination fingerprint | Allowlisted egress destinations only | Publish to a destination repointed after approval |

## 4. Step-up (just-in-time elevation)

`require_elevation(key)` checks only for a live grant; it stacks under whichever
gate establishes eligibility. Elevation **activates** a permission the role
already implies — it never grants one, and a request for a permission outside the
role's set is refused with `INSUFFICIENT_PERMISSIONS` and audited as
`privilege.denied`.

| Setting | Default | Effect |
| --- | --- | --- |
| `JIT_ELEVATED_PERMISSIONS` | *empty* | **Which keys require elevation. Empty ⇒ `require_elevation` is a no-op on every route.** See GAP-07 |
| `JIT_DUAL_APPROVAL_PERMISSIONS` | *empty* | Keys needing a second approver |
| `JIT_ELEVATION_TTL_MINUTES` | 15 | Grant lifetime |
| `JIT_REQUIRE_MFA` | `false` | Require a second factor to elevate |

Routes carrying an elevation gate today: secret create/update/delete/reveal,
role list/create/update/delete, the permission catalog, org-settings update, and
SSO config read/update/test.

## 5. Negative-test coverage

| Property | Covered by |
| --- | --- |
| Anonymous is refused on every non-public route | `test_public_route_allowlist.py` (structural), `test_secrets_security.py` |
| API key refused on human endpoints | `test_api_key_scopes.py` |
| Scope mismatch refused, and audited | `test_api_key_scopes.py` |
| Wrong-project SDK key refused without an oracle | `test_a10_feature_flag_sdk.py` |
| Cross-user self-service object access refused | `test_saas_phase2.py`, `test_saas_employee_reviews.py`, `test_saas_poc.py` |
| Insufficient role refused | `test_admin_platform.py`, `test_people_module.py` |
| Elevation cannot grant an ineligible permission | `test_zero_trust_phase3.py` |
| Self-approval refused | `test_zero_trust_phase3.py` |
| Revoked/expired token refused | `test_jwt_revocation.py` |
| Restricted modules are never public | `test_public_route_allowlist.py` |
| Per-identity quota isolation | `test_export_and_agent_quotas.py` |
