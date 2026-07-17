# Security Authorization Matrix

Two independent authorization domains:

- **Human users** authenticate with a JWT and authorize by **role** (via
  `require_role` / `require_permission`).
- **Service accounts** authenticate with an `X-API-Key` header and authorize by
  **scope** (via `require_scope`). A service account is **never** given a human
  role and its creator is **never** impersonated.

**Deny-by-default:** an API key is rejected on any endpoint that is not
explicitly annotated with `require_scope`. Every `require_role` /
`require_permission` endpoint (users, secrets, roles, org settings, SSO, MFA
policy, superadmin controls) therefore rejects API keys with `403
API_KEY_NOT_PERMITTED` — regardless of the key's scopes, including a wildcard.

## Scope registry (`app/api_scopes.py`)

| Scope | Grants |
|---|---|
| `email:read` | Read subscribers, lists, campaigns, settings, stats |
| `email:write` | Create/update subscribers, lists, membership, campaigns, settings |
| `email:send` | Trigger campaign sends and transactional email |
| `email:*` | Namespace wildcard — satisfies any `email:*` scope above |

- A bare `*` is **not** in the registry and grants **nothing**.
- Unknown / malformed scopes never satisfy a requirement.
- A requirement that is itself unregistered is denied (defensive).

## Route → required scope (API-accessible endpoints)

| Method + path | Required scope | Human role |
|---|---|---|
| `GET /admin/email/subscribers` | `email:read` | viewer |
| `POST /admin/email/subscribers` | `email:write` | admin |
| `PATCH/DELETE /admin/email/subscribers/{id}` | `email:write` | admin |
| `POST /admin/email/subscribers/import` | `email:write` | admin |
| `GET /admin/email/lists`, `.../{id}/members` | `email:read` | viewer |
| `POST/PATCH/DELETE /admin/email/lists...` | `email:write` | admin |
| `POST/DELETE /admin/email/lists/{id}/members...` | `email:write` | admin |
| `GET /admin/email/campaigns...` | `email:read` | viewer |
| `POST/PATCH /admin/email/campaigns...` | `email:write` | admin |
| `POST /admin/email/campaigns/{id}/test\|send\|schedule` | `email:send` | admin |
| `POST /admin/email/transactional` | `email:send` | admin |
| `GET/POST/DELETE /admin/email/suppressions...` | `email:read` / `email:write` | viewer / admin |
| `GET/PUT /admin/email/settings` | `email:read` / `email:write` | viewer / admin |
| `GET /admin/email/identities`, `/admin/email/stats` | `email:read` | viewer |

## Human-only (API keys always denied — `403 API_KEY_NOT_PERMITTED`)

`/admin/users*`, `/admin/secrets*`, `/admin/roles*`, `/admin/permissions/*`,
`/admin/org-settings` (PUT), `/admin/sso/*`, `/auth/mfa/*`, `/admin/audit-logs*`,
`/admin/search`, `/admin/certificates*`, and every other `require_role` /
`require_permission` / `require_active_user` endpoint.

## n8n integration (least privilege)

Provisioned via `scripts/create_n8n_service_account.py` with exactly
`["email:read", "email:write", "email:send"]` — sufficient for its drip/send
operations and nothing else.

## Auth response codes

| Situation | Status | code |
|---|---|---|
| No/invalid credentials | 401 | `AUTH_REQUIRED` |
| Invalid API key | 401 | `INVALID_API_KEY` |
| Revoked/unverifiable token (fail-closed) | 401 | `TOKEN_REVOKED` |
| API key on human-only endpoint | 403 | `API_KEY_NOT_PERMITTED` |
| API key missing required scope | 403 | `INSUFFICIENT_SCOPE` |
| Human lacks role/permission | 403 | `INSUFFICIENT_PERMISSIONS` |
| Disabled service account | 403 | `SERVICE_ACCOUNT_DISABLED` |

## Audit attribution

Service-account actions are logged with `actor_email =
"service-account:<name>#<key_prefix>"`; the raw key is never logged. Scope
denials emit `api_key.denied_scope` with the required scope and key prefix.
