# Cognito Deployment Readiness

## Required AWS resources
- Cognito User Pool
- Cognito App Client
- Cognito Hosted UI domain
- Google IdP integration in Cognito
- Callback/logout URL configuration

## Backend readiness
- Config-driven auth mode and Cognito settings added in `config.py`.
- JWT verification path includes issuer/client/token_use checks.
- JWKS caching implemented to avoid per-request refetch.

## Frontend readiness
- Feature-flagged Cognito login button.
- Hosted UI callback route to process `id_token`.
- No secrets embedded; only public client IDs/domains.

## Cutover guidance
1. Ensure all active users linked with `cognito_sub`.
2. Enable Cognito login and monitor auth audit events.
3. Move to `AUTH_MODE=hybrid` in staging and validate.
4. Switch to `AUTH_MODE=cognito` in production when stable.
5. Keep local auth rollback option for emergency only.
