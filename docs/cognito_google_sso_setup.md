# Cognito + Google SSO Setup

## Google Console
1. Create OAuth client (Web application).
2. Set authorized redirect URI to Cognito hosted UI callback.
3. Copy client ID/secret into Cognito Google IdP config.

## Cognito User Pool
1. Create User Pool and App Client (no secret for SPA).
2. Configure hosted UI domain.
3. Add Google as federated identity provider.
4. Set callback URL(s):
   - `http://localhost:3001/ui/auth/callback`
5. Set logout URL(s):
   - `http://localhost:3001/ui/login`
6. Enable scopes: `openid`, `email`, `profile`.
7. Map claims:
   - `email` -> email
   - `sub` -> cognito username/sub
   - `email_verified` -> email_verified
   - optional phone/mfa claims where available

## ControlHub env vars
Backend:
- `AUTH_MODE=hybrid`
- `COGNITO_REGION`
- `COGNITO_USER_POOL_ID`
- `COGNITO_APP_CLIENT_ID`
- `COGNITO_DOMAIN`
- `COGNITO_JWKS_URL` (optional override)

Frontend:
- `REACT_APP_AUTH_MODE=hybrid`
- `REACT_APP_ENABLE_COGNITO_LOGIN=true`
- `REACT_APP_COGNITO_DOMAIN=https://<domain>.auth.<region>.amazoncognito.com`
- `REACT_APP_COGNITO_APP_CLIENT_ID=<app_client_id>`
- `REACT_APP_COGNITO_REDIRECT_URI=http://localhost:3001/ui/auth/callback`

## Testing steps
1. Click “Sign in with Google” on login page.
2. Complete Google auth via Cognito hosted UI.
3. Ensure callback route receives `id_token` and posts to backend `/auth/cognito/login`.
4. Confirm local user linking and RBAC authorization.
