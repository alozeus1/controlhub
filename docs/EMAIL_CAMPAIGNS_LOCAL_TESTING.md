# Email Campaigns — Local Testing with LocalStack

This guide walks through exercising the **entire** email pipeline on your machine —
subscribers → campaign → SES send → delivery/open/bounce events → suppression —
using LocalStack to emulate Amazon SES + SNS. No AWS account, no real email, no cost.

Everything here runs before you ever push to Railway/Vercel.

---

## 0. Prerequisites

- Docker + Docker Compose (you already run LocalStack for S3).
- The repo's `.env` (copy from `.env.example` if you don't have one).

The module ships **feature-flagged on** (`FEATURE_EMAIL_CAMPAIGNS=true`) and pointed
at LocalStack (`EMAIL_PROVIDER=localstack`).

---

## 1. Start the stack

```bash
docker compose up -d db redis localstack
docker compose up -d api worker
docker compose up -d ui        # React admin UI on http://localhost:3001
```

Services and what they do:

| Service | Role |
|---|---|
| `localstack` | Emulates S3 + **SES** + **SNS** (`SERVICES: s3,ses,sns`) |
| `api` | Flask API on http://localhost:9000 (runs migrations on boot) |
| `worker` | RQ worker consuming the `campaigns` queue (batch sends) |
| `ui` | ControlHub admin UI on http://localhost:3001 |

On startup, `scripts/localstack/init-ses.sh` verifies the sender identity
(`campaigns@controlhub.local`) and creates the `controlhub-ses-events` SNS topic.

Confirm SES is up:

```bash
docker exec localstack awslocal ses list-identities
# → should include controlhub.local and campaigns@controlhub.local
```

If you did not use compose to run migrations, apply them manually:

```bash
docker compose exec api flask db upgrade
```

---

## 1b. SESv2 vs SESv1 (why local sends now work)

LocalStack **Community does not implement the SESv2 `SendEmail` API** — test sends
against it fail with `InternalFailure: API for service 'sesv2' not yet implemented
or pro feature`. LocalStack **does** implement the classic **SESv1** API.

The sender (`app/services/email_ses.py`) handles this automatically:

- `EMAIL_PROVIDER=localstack` → sends via the **SESv1** `send_email` API (works in
  LocalStack Community, so the pipeline is verifiable end to end locally).
- `EMAIL_PROVIDER=aws` (production) → sends via **SESv2** `send_email`.

**Production readiness check for SESv2:** the real AWS SES service fully supports
the SESv2 `SendEmail` API in all standard regions. Confirm before first prod send:

1. The IAM user/role policy allows `ses:SendEmail` and `ses:SendRawEmail` (these
   cover both API versions) — see `docs/EMAIL_CAMPAIGNS_MODULE_PLAN.md` §3.2.
2. The account is **out of the SES sandbox** (request production access), or all
   test recipients are verified identities.
3. The `From` domain/identity is **verified** and the configuration set exists.
4. Verify pricing/limits for your region in the AWS SES console (they change).

**Recommended staging path:** point a staging deploy at real AWS SES with
`SES_SENDING_ENABLED=true` but send only to a verified internal test inbox first,
or keep `SES_SENDING_ENABLED=false` (dry-run) until DNS auth is green.


## 2. Two ways to run sends locally

**A) With the worker (production-like):** leave `CAMPAIGN_SEND_SYNC=false`.
`/send` enqueues an RQ job; the `worker` container processes it.

**B) Inline (fastest for iterating):** set `CAMPAIGN_SEND_SYNC=true` in `.env`.
`/send` runs the send in-process and returns when done — no worker needed.

LocalStack's SES accepts and records messages but does **not** deliver real mail
or emit real events — so we simulate events in step 5.

---

## 3. Drive it from the UI

1. Open http://localhost:3001 → log in → **Marketing** section in the sidebar.
2. **Subscribers** → *Import CSV*, paste:
   ```
   ada@example.com,Ada Lovelace
   grace@example.com,Grace Hopper
   bob@example.com,Bob
   ```
3. **Lists** → *New list* ("Beta") → (add members via API in step 4, or extend the UI).
4. **Campaigns** → *New campaign* → walk the wizard (Details → Audience → Design → Review) → *Create draft*.
5. On the campaign page → *Send test* (any address) then *Send campaign*.
6. Watch counters populate. Simulate engagement in step 5 to move open/click/bounce rates.

---

## 4. Or drive it from the API (scriptable)

Get a JWT by logging in, then:

```bash
API=http://localhost:9000
TOKEN=... # paste an admin access token

# Create a list
LIST=$(curl -s -X POST $API/admin/email/lists -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" -d '{"name":"Beta"}' | jq .id)

# Import subscribers + attach to the list
curl -s -X POST $API/admin/email/subscribers/import -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" -d "{\"list_id\":$LIST,\"rows\":[
    {\"email\":\"ada@example.com\",\"name\":\"Ada\"},
    {\"email\":\"grace@example.com\",\"name\":\"Grace\"}]}"

# Create + send a campaign
CID=$(curl -s -X POST $API/admin/email/campaigns -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" -d "{\"name\":\"Launch\",\"subject\":\"Hi {{name}}\",
    \"html\":\"<h1>Welcome {{name}}</h1>\",\"target_list_id\":$LIST}" | jq .id)

curl -s -X POST $API/admin/email/campaigns/$CID/send -H "Authorization: Bearer $TOKEN"
```

> n8n uses the **same** endpoints with an `X-API-Key` header (a ControlHub
> service-account key) instead of a JWT — no separate auth to build.

---

## 5. Simulate SES events (delivery / open / click / bounce / complaint)

Because LocalStack won't emit real events, `scripts/simulate_ses_event.py` posts
correctly-shaped SNS notifications to the webhook so you can test the full
event → counter → suppression → n8n loop.

Grab a message id from a send:

```bash
curl -s $API/admin/email/campaigns/$CID/sends -H "Authorization: Bearer $TOKEN" | jq '.sends[0]'
```

Then simulate:

```bash
# delivered + opened + clicked
python scripts/simulate_ses_event.py delivery --message-id <MID> --email ada@example.com
python scripts/simulate_ses_event.py open     --message-id <MID> --email ada@example.com
python scripts/simulate_ses_event.py click    --message-id <MID> --email ada@example.com

# a hard bounce → auto-suppresses grace@example.com
python scripts/simulate_ses_event.py bounce --email grace@example.com

# a complaint → auto-suppresses
python scripts/simulate_ses_event.py complaint --email angry@example.com
```

Verify:
- Campaign open/click/bounce counters moved (UI overview or `GET /admin/email/campaigns/$CID`).
- `GET /admin/email/suppressions` now lists the bounced/complained addresses.
- Re-sending the campaign **excludes** suppressed recipients.

---

## 6. One-click unsubscribe

Every send includes `List-Unsubscribe` headers and a footer link:

```
http://localhost:9000/email/unsubscribe/<token>
```

Opening it (GET) or POSTing to it flips the subscriber to `unsubscribed` and adds
them to suppression — exactly what Gmail/Yahoo one-click requires.

---

## 7. Run the automated tests

No Docker needed — these use SQLite + dry-run SES + synchronous send:

```bash
python -m pytest tests/test_campaigns.py -q
```

Covers: feature gating, subscriber/list CRUD, email validation, suppression
filtering on send, SES bounce webhook → suppression, one-click unsubscribe, and
SNS TopicArn rejection.

---

## 8. What changes when you go to the cloud (Railway/Vercel)

Flip these and **nothing else in the code changes** (same provider-toggle as S3):

| Variable | Local (LocalStack) | Production (Railway) |
|---|---|---|
| `EMAIL_PROVIDER` | `localstack` | `aws` |
| `AWS_ENDPOINT_URL` | `http://localstack:4566` | *(unset)* |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | `test` / `test` | real IAM user key (Railway secret) |
| `SES_CONFIGURATION_SET` | *(blank)* | `controlhub-prod` |
| `SES_FROM_ADDRESS` | `campaigns@controlhub.local` | `campaigns@<verified-domain>` |
| `SNS_TOPIC_ARN` | *(blank)* | real topic ARN (webhook validates it) |
| `SES_SENDING_ENABLED` | `true` | `true` (set `false` for a dry run) |

In production the SNS webhook additionally verifies the message **signature**
against the AWS signing cert (skipped for LocalStack). See
`docs/EMAIL_CAMPAIGNS_MODULE_PLAN.md` §3 for the IAM policy and DNS (DKIM/SPF/DMARC).
```
