# Email Campaigns — n8n Orchestration Setup

n8n owns automation (drip flows, scheduling, branching). ControlHub owns the
data, sending, and deliverability. They talk over two authenticated channels:

- **ControlHub → n8n** — signed outbound webhooks on every email event.
- **n8n → ControlHub** — REST calls authenticated with a service-account API key.

This guide wires both, plus a reference welcome-drip workflow.

---

## 1. Create the ControlHub API key for n8n

Run the provisioning script (inside the `api` container or a venv with the app importable):

```bash
# Local (docker):
docker compose exec api python scripts/create_n8n_service_account.py

# With options:
docker compose exec api python scripts/create_n8n_service_account.py \
  --name "n8n Drip Bot" --expires-days 365
```

It prints the **plaintext API key once**. Copy it — you'll paste it into n8n next.
It reuses ControlHub's existing service-account + API-key module, so the key
authenticates via the `X-API-Key` header and is granted admin-level access to the
email endpoints (no extra auth to build).

To rotate later: run the script again with a new `--key-name`, update n8n, then
revoke the old key in ControlHub → Service Accounts.

---

## 2. Create the n8n credential

In n8n → **Credentials → New → Header Auth**:

| Field | Value |
|---|---|
| Credential name | `ControlHub X-API-Key` |
| Name | `X-API-Key` |
| Value | *(the key printed in step 1)* |

---

## 3. Set n8n environment variables

On your self-hosted n8n:

| Variable | Example | Purpose |
|---|---|---|
| `CONTROLHUB_BASE_URL` | `https://api.controlhub.webforx.tech` | Base URL the workflow calls |
| `N8N_WEBHOOK_SECRET` | *(shared secret)* | HMAC verification of inbound events |

> `CONTROLHUB_BASE_URL` for **local** testing where n8n runs in Docker and
> ControlHub runs on the host is usually `http://host.docker.internal:9000`.

---

## 4. Point ControlHub at n8n

Set these in ControlHub (Railway secrets / local `.env`):

| Variable | Value |
|---|---|
| `N8N_BASE_URL` | `https://n8n.webforx.tech` |
| `N8N_WEBHOOK_PATH` | `/webhook/controlhub-email` |
| `N8N_WEBHOOK_SECRET` | *(same value as n8n's)* |

ControlHub now POSTs every email event to `N8N_BASE_URL + N8N_WEBHOOK_PATH`,
signed with `X-ControlHub-Signature: hmac_sha256(secret, body)`.

---

## 5. Import the reference workflow

1. n8n → **Workflows → Import from File** → `n8n/controlhub_welcome_drip.json`.
2. Open each **HTTP Request** node and re-select the `ControlHub X-API-Key` credential
   (the import placeholder must be replaced with your real credential).
3. **Activate** the workflow. Copy its **Production webhook URL** — it should match
   `.../webhook/controlhub-email`.

The flow: `subscriber.created` event → verify signature → send welcome email →
wait 2 days → send follow-up. The `transactional` endpoint it calls is
**suppression-aware**, so bounced/unsubscribed contacts are skipped automatically.

---

## 6. Event contract (ControlHub → n8n)

All events POST the same envelope to the single webhook path:

```json
{
  "event": "subscriber.created",
  "data": { "id": 12, "email": "ada@example.com", "name": "Ada", "status": "subscribed" },
  "ts": 1752690000
}
```

Emitted event types:

| Event | Fires when | `data` payload |
|---|---|---|
| `subscriber.created` | New contact added/imported | subscriber dict |
| `subscriber.unsubscribed` | One-click / manual unsubscribe | subscriber dict |
| `email.delivery` | SES delivered | `{campaign_id, email, ses_message_id}` |
| `email.open` | Recipient opened | `{campaign_id, email, ses_message_id}` |
| `email.click` | Recipient clicked | `{campaign_id, email, ses_message_id}` |
| `email.bounce` | Hard bounce (auto-suppressed) | `{campaign_id, email, ses_message_id}` |
| `email.complaint` | Spam complaint (auto-suppressed) | `{campaign_id, email, ses_message_id}` |
| `campaign.sent` | Batch send finished | `{campaign_id, name, sent, failed, skipped}` |

Verify the signature in n8n (the reference workflow's **Verify Signature** Code node
does this): `HMAC_SHA256(N8N_WEBHOOK_SECRET, compact_json_body)` must equal
`X-ControlHub-Signature`.

---

## 7. What n8n can call (n8n → ControlHub)

All under `CONTROLHUB_BASE_URL`, header `X-API-Key: <key>`:

| Method & path | Purpose |
|---|---|
| `POST /admin/email/transactional` | **Send one suppression-aware email** (drip step). Body: `{email, subject, html, from_name?, from_address?}` |
| `POST /admin/email/subscribers` | Upsert a contact + consent |
| `POST /admin/email/subscribers/import` | Bulk import + optional `list_id` |
| `POST /admin/email/lists/{id}/members` | Add contacts to a list. Body: `{subscriber_ids:[...]}` |
| `POST /admin/email/campaigns` | Create a campaign |
| `POST /admin/email/campaigns/{id}/send` | Trigger a list send (e.g. at a scheduled time) |
| `GET  /admin/email/campaigns/{id}` | Pull live stats into a flow |

`transactional` returns `200 {sent:true, message_id}` on send, or
`202 {sent:false, reason}` when the contact is suppressed/unsubscribed (so your
flow can branch without treating it as an error).

---

## 8. Building more flows

The reference is deliberately small. Common extensions, all using the same
webhook + API-key wiring:

- **Re-engagement:** on `email.open` absence over N days (n8n schedule + `GET campaign stats`), send a win-back `transactional` email.
- **Bounce alerting:** on `email.bounce` / `email.complaint`, post to Slack/Teams (ControlHub already auto-suppresses; this is just notification).
- **Scheduled newsletters:** n8n cron → `POST /email/campaigns/{id}/send` at the send time (keeps scheduling in n8n, not ControlHub).

> Security: keep the API key in n8n's credential store (never in a node field),
> keep `N8N_WEBHOOK_SECRET` matched on both sides, and use TLS end-to-end.
