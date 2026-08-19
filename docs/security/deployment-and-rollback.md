# ControlHub — Deployment and Rollback

Applies to the six commits on `security-gauntlet-controlhub` above baseline
`d3a4298`. **Nothing here has been deployed. Nothing here is authorized to be
deployed.**

## 1. What is being shipped

| Commit | Change | Schema | Config required | Behaviour change visible to users |
| --- | --- | --- | --- | --- |
| `fe7ccb5` | SNS webhook verification hardening | none | `SNS_TOPIC_ARN` **must** be set in production or the webhook fails closed | Inbound SES events are refused unless genuinely from the configured topic |
| `d1c6e5e` | flake8 baseline fix (tests only) | none | none | none |
| `3289820` | Reset-link origin from config | none | `UI_BASE_URL` recommended; falls back to `PUBLIC_BASE_URL` | Reset links use the configured origin instead of the request host |
| `28b549d` | Endpoint inventory + CI gate | none | none | none at runtime |
| `2852b59` | Per-identity export/agent quotas | none | none | 429 after the hourly quota on 10 routes |
| `c68f3be` | App-level CSP + HSTS | none | optional `CONTENT_SECURITY_POLICY`, `STRICT_TRANSPORT_SECURITY`, `HSTS_ALWAYS` | New response headers |

No Alembic migration is introduced. `flask db upgrade` on release is a no-op for
this branch.

## 2. Pre-deployment configuration — blocking

`fe7ccb5` makes `SNS_TOPIC_ARN` **mandatory in production**. Deploying without it
means `/email/webhooks/ses` refuses every event, so bounces and complaints stop
being recorded and suppression stops updating. This is the intended fail-closed
behaviour, and it is the one change here that can break a working flow if
configuration is skipped.

| Variable | Action | Consequence if skipped |
| --- | --- | --- |
| `SNS_TOPIC_ARN` | **Set before deploy** | SES events silently refused |
| `UI_BASE_URL` | Set to the real public origin | Reset links fall back to `PUBLIC_BASE_URL`; if that is still `http://localhost:9000`, links are unusable (an error is logged) |
| `SNS_MAX_MESSAGE_AGE_SECONDS` | Leave at 900 | — |
| `JIT_ELEVATED_PERMISSIONS` | Set (GAP-07) | Step-up remains a no-op |
| `SECRET_KMS_KEY_ID` | Set + `flask secrets rewrap` (GAP-08) | Secrets stay under a locally derived key |
| `AUDIT_MIRROR_SINK` | Set (GAP-09) | Audit log stays inside the blast radius |

## 3. Staged rollout

1. **Isolated staging, synthetic data, non-production credentials.** Never a copy
   of production data.
2. Run the full CI gauntlet on the branch: all 18 jobs green, including the new
   `endpoint-surface` job and the PostgreSQL migration replay.
3. Verify the critical journeys by hand or with an authenticated browser suite:
   login → MFA → token pair; refresh rotation; secret reveal; elevation request →
   approval; role change; people CSV export; campaign send → SES → SNS event →
   suppression; agent run → artifact → download; audit query → export.
4. Confirm the SNS path end to end with a real test notification from the
   configured topic, then confirm a message from a *different* topic is refused.
5. Confirm a reset email arrives with the configured origin, and that a request
   carrying a forged `Host` still produces the configured origin.
6. Confirm response headers on the staging origin directly (not through nginx):
   CSP present, HSTS present over TLS.
7. Exercise one quota to a 429 and confirm a second identity is unaffected.
8. Human security and product approval.
9. Canary if the platform allows; otherwise deploy `web` and `worker` from the
   same image/commit, as the `Procfile` requires.

## 4. Rollback triggers

Roll back immediately on any of:

- login or MFA failure rate above baseline;
- `403`/`ELEVATION_REQUIRED` on a flow that previously worked;
- `429` on a route an operator needs mid-task, where raising the limit is not an
  immediate option;
- inbound SES events refused when `SNS_TOPIC_ARN` is confirmed correct;
- password-reset emails not arriving, or arriving with an unusable link;
- `verify_chain` failure;
- campaign sends failing or the worker queue backing up;
- 5xx or latency regression;
- any CSP violation breaking the SPA (watch browser console reports).

## 5. Rollback procedure

Each control is one commit with no schema and no state. Revert individually,
smallest blast radius first:

```bash
# a single control
git revert c68f3be          # app-level headers
git revert 2852b59          # quotas
git revert 3289820          # reset-link origin
git revert fe7ccb5          # SNS hardening

# the whole pass, keeping the carried-over baseline work
git revert --no-commit c68f3be 2852b59 28b549d 3289820 d1c6e5e fe7ccb5
git commit -m "revert: security gauntlet pass"
```

Then redeploy `web` and `worker` from the same reverted commit.

**Order matters if `SNS_TOPIC_ARN` was the problem:** reverting `fe7ccb5` restores
the permissive behaviour and re-opens GAP-01 and GAP-03. Prefer fixing the ARN.
Treat reverting that commit as an incident, not a routine rollback.

Header and quota reverts are safe and independent. Reverting `28b549d` removes a
CI gate only.

## 6. Observation window

Keep every rollback asset for at least one full business cycle after deployment:

- do not delete the pre-deployment image;
- do not remove `PUBLIC_BASE_URL` even after `UI_BASE_URL` is set — it is the
  documented fallback;
- do not remove the previous Fernet secret key until `flask secrets rewrap` has
  completed and been verified (GAP-08);
- keep the prior SNS subscription confirmed until the hardened path has processed
  real events.

## 7. Monitoring during the window

| Signal | Source | Threshold |
| --- | --- | --- |
| Login success rate | audit `login` events | any drop |
| 403 by code | audit + app logs | any new `ELEVATION_REQUIRED` |
| 429 by identity | limiter | any operator identity hitting a quota |
| SNS refusals | `SNS signature verification failed` / `TopicArn mismatch` warnings | any, once the ARN is confirmed |
| Reset-link errors | `Cannot build a password-reset link` / localhost-in-production error | any |
| Audit chain | scheduled `verify_chain` | any failure |
| CSP violations | browser console / report endpoint if configured | any |
| Queue depth | RQ | growth (unbounded — GAP-10) |
