# Hybrid Auth Design (Local + Cognito)

## Modes
- `AUTH_MODE=local`: only local auth endpoints accepted.
- `AUTH_MODE=cognito`: local login disabled, Cognito path enabled.
- `AUTH_MODE=hybrid` (default): both local and Cognito accepted.

## Flows
### Local flow
1. `/auth/login` validates email/password.
2. Enforces lockout, active status, optional email verification.
3. Issues local app JWT access/refresh.
4. RBAC derives role from local DB user.

### Cognito flow
1. Frontend obtains Cognito token (hosted UI/social federation).
2. Frontend posts token to `/auth/cognito/login`.
3. Backend verifies token signature and claims (issuer/audience/token_use/exp).
4. Backend links user by `cognito_sub`; fallback to verified email.
   - If an existing local user already has a `cognito_sub`, login is allowed only on exact `sub` match.
   - `sub` mismatches are denied and audited (`auth.cognito_sub_mismatch_denied`).
5. Optional auto-provision if `COGNITO_AUTO_PROVISION=true`.
6. Backend issues app JWT to keep session model consistent.

## User mapping strategy
- Primary key: `cognito_sub`.
- Fallback: verified email match, then link `cognito_sub`.
- Email fallback linking is only allowed when `cognito_sub` is empty, token email is verified, and `COGNITO_ALLOW_EMAIL_LINKING=true`.
- RBAC source of truth remains `user.role` in local DB.

## Migration and backfill
- Add provider/profile/security columns to `user` table.
- Backfill existing users with `auth_provider=local` and `email_verified=true` (internal trusted-user assumption).
- Add indexes on `email`, `cognito_sub`, and `auth_provider`.

## Rollback plan
- Set `AUTH_MODE=local` immediately.
- Disable Cognito button in frontend env.
- Keep schema fields (non-breaking); no data loss required.

## Security considerations
- Never trust unverified JWTs.
- Never store Cognito passwords.
- Generic auth failure responses for token errors.
- Rate-limit auth endpoints.
- Capture normalized auth audit events.
