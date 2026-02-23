# ControlHub Auth Audit Report

## Existing implementation summary
- Backend auth endpoints exist for login, refresh, me, logout, forgot/reset password, and change password in `app/routes/auth.py`.
- Local JWT access/refresh tokens are issued by Flask-JWT-Extended and checked in RBAC decorators (`app/utils/rbac.py`).
- Password hashing uses Werkzeug `generate_password_hash` / `check_password_hash` in `app/models.py`.
- RBAC role hierarchy and route enforcement are implemented in `app/utils/rbac.py`.
- Audit logging exists via `app/utils/audit.py` with auth events currently labeled `user.login`, `user.login_failed`, and `user.logout`.
- Rate limiting is present on login and password reset endpoints via Flask-Limiter.
- Frontend login/reset flows exist in React (`admin-ui/src/pages/Login.jsx`, `ForgotPassword.jsx`, `ResetPassword.jsx`) and token storage is in sessionStorage/localStorage (`admin-ui/src/utils/auth.js`).
- Protected route gating is simple token existence check (`admin-ui/src/components/ProtectedRoute.jsx`).

## Gaps and risks identified
- No Cognito/SSO integration points currently exist.
- JWT middleware only accepts local app JWTs; no federated token verification.
- Password policy is weak (length >= 8 only), with no complexity checks.
- No account lockout mechanism.
- No email verification workflow.
- User schema lacks identity-provider and login-security metadata.
- Audit events are not normalized to requested `auth.*` naming.
- Auth tests are very limited (only health checks in `tests/`).

## Cognito integration insertion points
- Add token verification service under `app/auth/` and reuse from both `/auth/cognito/login` and RBAC decorator path.
- Extend `User` model with provider and identity-link fields in `app/models.py` + Alembic migration.
- Update `app/utils/rbac.py` to accept local JWT and Cognito JWT in hybrid mode.
- Add frontend optional Cognito login button + hosted UI callback route in React app.

## Immediate recommendations
1. Implement hybrid `AUTH_MODE` (`local`, `cognito`, `hybrid`) in config.
2. Keep local `/auth/login` and `/auth/refresh` path intact while adding `/auth/cognito/login`.
3. Maintain RBAC lookup from local DB for both auth providers.
4. Add lockout, password policy, email verification, and expanded audit events.
5. Expand backend/frontend tests for both paths.
