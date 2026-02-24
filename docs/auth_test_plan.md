# Auth Test Plan

## Backend unit/integration
- Local login success/failure.
- Lockout after repeated failed attempts.
- Password policy enforcement on reset/change.
- Cognito login linking by email and by sub.
- Cognito linked-account sub mismatch denial path.
- Cognito token failure handling.
- Hybrid RBAC path accepts local and Cognito bearer paths.
- RBAC role source remains local DB.
- Logout behavior for both local JWT and Cognito bearer auth.
- `/auth/me` normalized identity response for local and Cognito.
- `/healthz` Cognito readiness states.
- Admin auth-link visibility and audit `auth_only` filtering.

Implemented in:
- `tests/test_auth_hybrid.py`

## Frontend tests
- Hosted UI callback parser test.
- Auth utility baseline tests for Cognito URL behavior.

Implemented in:
- `admin-ui/src/pages/AuthCallback.test.jsx`
- `admin-ui/src/utils/auth.test.js`

## E2E skeleton
- Playwright skeleton scenarios for:
  - local login success
  - local lockout
  - password reset
  - cognito callback
  - protected route and logout

Implemented in:
- `tests/e2e/auth.e2e.spec.ts`

## Real Cognito integration testing
- Use a dedicated test user pool/app client.
- Set CI secrets for Cognito values.
- Run targeted integration suite with live JWKS and hosted UI.
