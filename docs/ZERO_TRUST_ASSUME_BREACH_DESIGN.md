# ControlHub — Zero Trust / Assume-Breach Security Design

**Status:** Phases 1–5 implemented (see §5). Phase 5 ships as Terraform in `infra/terraform/`.
**Scope:** Whole platform, with emphasis on the automation / workflow / AI-agent surface
**Threat model:** The adversary is already inside — network, database, API process — and holds elevated credentials.

> **Implementation note.** Phase 1 shipped in migration `z6a7b8c9d0e1`; Phase 2 in
> `a7b8c9d0e1f2`. Together they close both structural failures called out in §0:
> secrets no longer share a blast radius with their key (§3.2), and the audit log is
> chained, mirrored, and append-only at the database (§3.3). The findings table below is
> preserved as the record of what was found, with each row's current state.
>
> Phase 3 (`b8c9d0e1f2a3`) adds the JIT elevation model of §3.1, defaulting to OFF.
>
> Phase 4 (`c9d0e1f2a3b4`) adds the egress chokepoint of §3.4d and pins §3.4b.
>
> Phase 5 ships as Terraform (`infra/terraform/`) covering §3.6's IAM split and all of
> §3.7's detection.
>
> **Known gaps, stated plainly:**
> - **Default-deny network egress is not achievable on Railway** (no VPC). The app-level
>   chokepoint compensates, but runs inside the process an attacker controls. See §5 item 13.
> - **Per-run ephemeral credentials** (§3.4a) remain partial — destination-scoped identity
>   shipped; true per-run credentials need Google-side WIF configuration.
> - **Static AWS access keys** in the Railway environment cannot be origin-scoped the way an
>   instance role can. The IAM split limits blast radius; it does not remove the exposure.

---

## 0. Verdict on the current posture

**ControlHub is not zero trust today.** It is a well-built RBAC application with several
genuinely zero-trust-aligned pieces, sitting on an architecture that still assumes the
inside is trustworthy.

**What is already right** (do not regress these):

| Control | Where |
|---|---|
| JWT revocation fails **closed** when Redis is unreachable | `app/__init__.py:49` |
| API keys are a separate authorization domain, denied on every human endpoint | `app/utils/rbac.py:56`, `app/permissions.py:99` |
| Service accounts are never impersonated as their creator | `app/utils/rbac.py:172` |
| `is_active` is re-checked on **every** request, not just at login | `app/utils/rbac.py:80` |
| Deny-by-default API scopes | `app/utils/rbac.py:154` |
| SSRF-guarded outbound HTTP | `app/services/safe_http.py` |
| OIDC `id_token` verified against JWKS (aud/iss/exp/nonce) | `app/routes/sso.py` |
| Production config validation refuses to boot on weak keys / wildcard CORS | `config.py:validate` |
| Agent exports constrained by template `allowed_fields` + masking + approval thresholds | `app/services/agent_tools.py` |
| HSTS, CSP, frame-deny, `no-store` on auth/admin | `nginx.conf:51`, `app/utils/security_headers.py` |

**Where it fails the assume-breach test.** Each of these is a case where holding the
credential is *sufficient* to cause the harm — which is exactly what zero trust must prevent:

1. ~~**The audit log is rewritable by the attacker.**~~ ✅ **Closed in Phase 2.** Was: an
   ordinary table in the same Postgres the app has full DML on, with no chain, sink, or
   grant restriction. Now chained, mirrored out-of-band, and `SELECT, INSERT`-only for the
   application role.
2. ~~**Secret encryption keys share a blast radius with the secrets.**~~ ✅ **Closed in
   Phase 2**, once `SECRET_KMS_KEY_ID` is set. Was: `SECRET_ENCRYPTION_KEYS` in the API
   process environment alongside DB access to the ciphertext — an attacker inside the API
   held both halves, so encryption-at-rest bought nothing against them.
3. ~~**Privilege is standing, not just-in-time.**~~ ✅ **Closed in Phase 3**, for the
   permissions you list in `JIT_ELEVATED_PERMISSIONS`. Was: `role` as a static column, so a
   stolen admin session was admin for the token's whole life across every capability, with
   no re-verification, reason, or expiry.
4. ~~**The AI agent service is an exfiltration engine the attacker inherits.**~~
   ✅ **Closed in Phase 4**, once the egress allowlist is configured. Was: bulk-read of
   people/asset/deployment data publishable *outside* the org to any Drive folder or Sheet
   a destination named. Now volume-capped (Phase 1), routed through one chokepoint against
   a deployment-level target allowlist, and pinned against post-approval redirection.

**Confirmed defects — all four fixed in Phase 1:**

| Severity | Finding | State |
|---|---|---|
| **High** | MFA **failed open**: any exception in the MFA layer fell through to issuing full access + refresh tokens with no second factor. A DB hiccup or a missing `UserMfa` row downgraded every MFA-protected account to password-only. | ✅ Fixed — now returns 503 `MFA_UNAVAILABLE`. |
| **High** | No `ProxyFix`/trusted-proxy handling. Behind nginx, `get_remote_address` returned the **proxy** IP, so `@limiter.limit("10 per minute")` on login was a single global bucket — not per-IP. Simultaneously a bypass and a self-DoS. | ✅ Fixed — `TRUSTED_PROXY_COUNT`, set to 1 in compose. |
| **Medium** | `X-Forwarded-For` was trusted verbatim, so audit-log source IPs were attacker-controlled — forged attribution in the record you would investigate with. | ✅ Fixed — `get_client_ip` reads only `remote_addr`. |
| **Medium** | Refresh tokens were neither rotated nor reuse-detected; a captured refresh token was a 7-day renewable session. | ✅ Fixed — rotation + family revocation on replay. |

---

## 1. The adversary, concretely

Assume the attacker holds, simultaneously: a valid admin JWT, the API process environment,
read/write on Postgres, read/write on Redis, and a foothold on the app network.

What that gets them in ControlHub today:

| Asset | Reachable? | Via |
|---|---|---|
| All employee/intern PII | Yes | `/admin/people`, or an agent export |
| Stored secrets (plaintext) | Yes | Fernet key is in the same process env |
| SSO client secret, integration tokens | Yes | Same |
| Bulk export to external Drive/Sheets | Yes | Agent service + destination they can add |
| Outbound email as `@webforxtech.com` | Yes | SES creds in env — phishing with a verified domain |
| Covering their tracks | Yes | `DELETE FROM audit_log` |
| Persistence | Yes | Create a service account + non-expiring API key |

The design goal is to move every row of that table from "Yes" to "No, or not without
tripping a signal the attacker cannot reach."

---

## 2. Design principles

1. **A credential is never sufficient.** High-impact actions require a second, independent
   control that is *not* in the same blast radius as the credential.
2. **No standing privilege.** Base identity is read-only. Power is borrowed, time-boxed,
   justified, and returned.
3. **The record of what happened must outlive the attacker's access.** Audit leaves the
   trust boundary within seconds and is verifiable.
4. **Automation gets its own identity, never a human's**, scoped to one task and one TTL.
5. **The model never chooses the tool, the scope, or the destination.**
6. **Every in-app guard has a network-layer twin**, because in-app guards do not bind an
   attacker already executing code in the process.

---

## 3. The control plane

### 3.1 Just-in-time privilege (removes standing power)

**Today:** `role` is permanent; `require_permission` checks it and proceeds.

**Design:** split *eligibility* from *activation*.

- Every user's effective baseline drops to read-only. `manage_secrets`, `manage_users`,
  `manage_roles`, `manage_sso`, `manage_org_settings`, agent export-approval, and external
  destination changes all become **activatable, not held**.
- New `PrivilegeGrant` table: `(user_id, permission_key, reason, approved_by, granted_at,
  expires_at, used_count, revoked_at)`.
- New decorator `require_elevated_permission(key)` wrapping the existing
  `require_permission` — same call sites, so this is an additive change:

  ```python
  @secrets_bp.post("/secrets/<int:id>/reveal")
  @require_elevated_permission("manage_secrets")   # was @require_permission
  def reveal_secret(id): ...
  ```

- Activation requires: a typed **reason**, a **fresh second factor** (re-verify TOTP at
  elevation time — *not* a flag on the login session, because the stolen artifact **is**
  the session), and a **TTL of 15 minutes**. Auto-expiry, no renewal without a new reason.
- The most sensitive keys (`manage_roles`, `manage_sso`, adding an external agent
  destination) additionally require **a second human to approve** — the existing
  `ApprovalRequest` / `check_policy` machinery in `app/routes/governance.py` already
  models this; reuse it rather than building a parallel path.

**Why this defeats the adversary:** a stolen admin token now buys read-only access. To do
damage they must also defeat a live second factor and, for the worst actions, a second
person — and every elevation is a loud, attributable, out-of-band-logged event.

### 3.2 Key custody outside the blast radius

**Today:** Fernet keys in `SECRET_ENCRYPTION_KEYS`, ciphertext in Postgres, attacker has both.

**Design:** AWS KMS envelope encryption. The API can *request a decrypt*; it never holds the
master key.

- Per-secret **encryption context** (`{"secret_id": ..., "org": ...}`) so a stolen
  ciphertext cannot be replayed as a different secret.
- Keep `secret_crypto.py`'s interface (`encrypt_secret` / `decrypt_secret`) and swap the
  implementation — call sites do not change.
- Wrap `kms:Decrypt` for the secrets key behind the **JIT elevation** grant (3.1), so the
  IAM policy itself denies bulk decryption outside an active elevation window.
- CloudTrail now gives you a decrypt log **the attacker cannot edit from inside ControlHub**,
  plus a natural anomaly signal: normal operation decrypts a handful per day; exfiltration
  decrypts everything.

This is the single change that converts encryption-at-rest from paperwork into a real
control against this adversary.

### 3.3 Tamper-evident audit

**Today:** rewritable table. **Design:** three layers.

1. **Hash chain.** Add `prev_hash` and `row_hash` to `audit_log`;
   `row_hash = SHA256(canonical(actor, action, target, details, created_at) || prev_hash)`.
   Any deletion or edit breaks the chain at a detectable point.
2. **Out-of-band mirror.** Every audit event ships within seconds to a sink ControlHub
   cannot rewrite: CloudWatch Logs with a resource policy denying `Delete*`, or S3 with
   **Object Lock in compliance mode**. This is the copy you investigate with.
3. **Least privilege on the table itself.** The application's DB role gets `INSERT` only on
   `audit_log` — no `UPDATE`, no `DELETE`. Requires a migration granting a separate role;
   it stops the single most damaging DB action outright.
4. **A verifier job** recomputes the chain on a schedule and alarms on divergence. Alarm
   destination must not be ControlHub.

### 3.4 AI agent / automation containment

This is the highest-leverage area, because the agent surface is *purpose-built* to do the
thing the attacker wants: read broadly, publish outward.

**a) Per-run ephemeral identity.** No ambient agent credential. Each run mints a
single-purpose token scoped to **one template + one destination + one TTL**, unusable for
anything else and dead when the run ends. Extends the existing "never impersonate a human"
rule (`rbac.py:172`) from API keys to agent runs.

**b) Treat all data the agent reads as attacker-controlled — prompt injection is privilege
escalation.** Once the attacker is in the DB, they control the content of person notes,
incident write-ups, runbooks, and email bodies. If tool selection is model-driven, a
crafted note becomes an instruction. **Invariant:**

> The model may fill in *parameters*. The template determines the tool, the field scope,
> and the destination. Parameters are re-validated server-side against the template's
> `allowed_fields` after the model returns.

ControlHub is already close to this — `enforce_template_fields` and
`resolve_requested_fields` exist in `app/services/agent_tools.py:463`. Make it an explicit,
tested invariant with a test that feeds injected instructions through a person record and
asserts the destination and field scope are unchanged.

**c) Approval on sensitivity, not just row count.** Today the only gate is
`AGENT_EXPORT_APPROVAL_ROW_THRESHOLD=200`. Add:

- Any export touching masked/PII fields → approval **regardless of row count** (200 people
  records is a breach; 200 asset rows is a Tuesday).
- Any **new or modified** external destination → two-person approval under elevation.
- A **cumulative per-actor daily export budget** with a hard stop, so the attacker cannot
  slice one large exfiltration into 199-row requests.

**d) One egress chokepoint.** Every artifact leaving ControlHub — Drive, Sheets, presigned
S3, email — passes through a single function that re-checks the destination allowlist at
*send* time (not request time), and emits an audit event with the artifact SHA-256
(`sha256_hex` already exists). The sheet allowlist (`agent_tools.py:436`) becomes one case
of the general rule, and the allowlist itself is elevation-gated config.

**e) Agent runs are off-hours-sensitive.** A bulk people export at 03:00 from a new IP is
the signature of this exact attack. Make it a first-class alert, not a log line.

### 3.5 Continuous session verification

The stolen artifact is the session, so the session must keep proving itself.

- **Refresh-token rotation with reuse detection.** Rotate on every refresh; if a
  previously-used refresh token is replayed, revoke the entire token family and alert.
  This is the highest value-per-line control on this page — a replayed token is a
  near-unambiguous compromise signal, and ControlHub already has the Redis blocklist
  infrastructure to enforce it.
- **Per-user revocation epoch.** Add `User.session_epoch`, embed it in the JWT, compare per
  request. Bump on disable, role change, password change, and elevation revoke → every
  outstanding token dies **immediately** rather than within the 1-hour access-token TTL.
- **Bind tokens to a client fingerprint** (UA + client-ID cookie); require re-auth on change.
- **Fix the MFA fail-open** at `app/routes/auth.py:108`. Failing closed here means an MFA
  subsystem error blocks login — that is the correct trade for an internal tool, and it is
  consistent with the deliberate fail-closed choice already made for JWT revocation.
- **Add `ProxyFix`** with a trusted-proxy count, so per-IP rate limiting and audit source
  IPs become real (`app/extensions.py:44`, `app/utils/audit.py:13`).

### 3.6 Network-layer twins (the attacker executes code in-process)

`safe_http.py` cannot bind an attacker who is already running code in the API process.
Every in-app guard needs a network enforcement point:

- **Default-deny egress** from the API/worker subnet, allowlisting only SES, SNS, KMS,
  S3, Google APIs, and the OIDC provider. A compromised process then cannot open a C2
  channel or POST the database to an arbitrary host.
- **Block IMDS** (`169.254.169.254`) from the app container / IMDSv2 hop limit 1 —
  otherwise elevated in-process code lifts the instance role and pivots into AWS.
- **Separate the worker's IAM role from the API's.** The campaign worker needs SES send;
  the API does not need it, and neither needs the other's permissions.
- **DB least privilege**, per 3.3: no `DELETE` on `audit_log` for the app role.

### 3.7 Detection (assume the controls fail)

Signals worth alarming on, all routed to the out-of-band sink from 3.3 so they survive the
attacker:

| Signal | Why it matters |
|---|---|
| Refresh-token reuse | Near-unambiguous session theft |
| Audit hash-chain divergence | Someone edited history |
| KMS decrypt volume spike | Bulk secret exfiltration |
| Elevation grant, especially off-hours | The new front door — watch it |
| New/modified agent external destination | Exfiltration setup |
| Bulk PII export, or export budget exhaustion | Exfiltration in progress |
| Role change / service-account + API key created | Persistence |
| SES send-rate spike | Domain-reputation abuse / phishing from a verified domain |
| Login MFA-bypass path taken | Would have caught the `auth.py:108` fail-open |

---

## 4. What "just-in-time hardening" means here

| Capability | Standing (always on) | JIT (borrowed, TTL'd, justified) |
|---|---|---|
| Read dashboards, own records | ✅ | |
| View audit logs | ✅ | |
| Manage users | | ✅ 15 min + reason + fresh 2FA |
| Reveal/manage secrets | | ✅ 15 min + fresh 2FA + KMS grant |
| Manage roles / SSO / org settings | | ✅ + **second approver** |
| Approve agent exports | | ✅ + second approver for PII |
| Add/modify external destinations | | ✅ + second approver |
| Agent run credentials | | ✅ per-run, single template + destination |
| Production DB write access (humans) | | ✅ break-glass only, auto-expiring, alarmed |

Rule of thumb: **if it can move data out, change who has power, or rewrite history, it is
never standing.**

---

## 5. Sequencing

**Phase 1 — ✅ SHIPPED** (migration `z6a7b8c9d0e1`, 17 tests in `tests/test_zero_trust_phase1.py`)

1. ✅ MFA fails closed — a fault denies login instead of downgrading to password-only.
2. ✅ `ProxyFix` behind `TRUSTED_PROXY_COUNT`; `get_client_ip` no longer parses `X-Forwarded-For`.
3. ✅ Refresh-token rotation with reuse detection — a replayed token revokes the whole
   family and writes an `auth.refresh_token_reuse` audit event.
   *Required a client change:* the SPA previously discarded the rotated refresh token
   (`admin-ui/src/utils/auth.js`), which would have tripped reuse detection on every
   second refresh.
4. ✅ `User.session_epoch` — bumped on disable, role change, password change/reset, so
   existing tokens die immediately rather than within an access-token TTL.
   `/auth/change-password` now returns a fresh pair so the caller's own tab survives.
5. ✅ Per-actor daily export budget (`AGENT_EXPORT_DAILY_ROW_BUDGET`, default 5000 rows /
   24h, 429 on breach). PII-based approval already existed via `template.pii_flag` in
   `evaluate_approval_requirements` — verified, not rebuilt.

**Phase 2 — ✅ SHIPPED** (migration `a7b8c9d0e1f2`, 16 tests in `tests/test_zero_trust_phase2.py`)

6. ✅ **Audit integrity, all three layers.**
   - **Hash chain** (`app/services/audit_chain.py`) — every row commits to its content and
     its predecessor; `verify_chain()` reports the first divergence and distinguishes a
     deletion from an edit.
   - **Out-of-band mirror** (`app/services/audit_sink.py`) — ships sealed rows, chain
     hashes included, to CloudWatch Logs or a file sink. Shipping is a separate pass with
     a persisted high-water mark, so a sink outage replays rather than silently skipping,
     and an unreachable sink can never block an audited action.
   - **Append-only at the database** (`scripts/sql/audit_log_append_only.sql`) — the
     application role gets `SELECT, INSERT` and nothing else. Verified: with the script
     applied, `DELETE FROM audit_log` and `UPDATE audit_log` both fail with *permission
     denied* for the app role while inserts and the mirror cursor keep working.
     **Caveat:** this only works if the app connects as a **non-owner** role. Ownership
     implies full DML regardless of grants — the script documents the check.
   - **Verifier** — `flask audit verify` exits non-zero on divergence so cron can alarm.
     Confirmed against a real out-of-band `DELETE` issued through psql.

7. ✅ **KMS envelope encryption** (`app/services/secret_crypto.py`). A per-write data key
   from `GenerateDataKey`, used once; only its KMS-wrapped form is stored, so every read
   costs a `kms:Decrypt` that CloudTrail records and IAM can gate.
   - **Per-purpose encryption context** binds each ciphertext to its domain — an SSO
     client-secret blob cannot be moved into a Secret row and read back. Verified against
     real KMS (LocalStack), which refuses the mismatched context rather than returning
     plaintext.
   - **No downtime, no data migration.** Ciphertexts are self-describing (`fernet:v1:` /
     `kms:v1:`), so existing rows keep decrypting the moment KMS is switched on;
     `flask secrets rewrap` migrates them in place when convenient.
   - *Scope honesty:* the context is **purpose-scoped, not row-scoped**. Row-scoped would
     be stronger, but `encrypt_secret` runs during row construction — before an id exists
     — so a row-scoped context could not be reproduced at decrypt time for new records,
     and getting that wrong makes secrets permanently unreadable.

   **Requires from you:** a CMK plus an IAM policy granting the app `kms:GenerateDataKey`
   and `kms:Decrypt` on it, then `SECRET_KMS_KEY_ID`. Until that is set the app falls back
   to Fernet and logs a startup warning.

**Phase 3 — ✅ SHIPPED** (migration `b8c9d0e1f2a3`, 23 tests in `tests/test_zero_trust_phase3.py`)

8. ✅ `PrivilegeGrant` + `require_elevation` / `require_elevated_permission`
   (`app/services/privilege.py`, `app/routes/elevation.py`). Applied to `manage_roles`,
   `manage_sso`, `manage_org_settings`, and secret reveal.
   - **Fresh re-authentication** at elevation time — MFA if enrolled, password otherwise
     (`JIT_REQUIRE_MFA=true` removes the fallback). Fails closed on an MFA fault, same as
     the login path.
   - **Session binding.** The grant records the refresh-token family that requested it.
     A different stolen token for the same user cannot use it — without this, an attacker
     sharing the victim's account would inherit every elevation the real operator performs.
   - **Reason required** (≥10 chars), audited on grant, on each use, and on revocation.
   - **Auto-expiry** (default 15 min), plus early hand-back and automatic revocation on
     role change or disable.
9. ✅ Second-approver requirement, opt-in per permission via
   `JIT_DUAL_APPROVAL_PERMISSIONS`. Pending grants are created already-expired, so there
   is no window where they are briefly live; approval extends the clock. Self-approval is
   refused, and approvers must themselves hold the permission.

   **Defaults are OFF.** `JIT_ELEVATED_PERMISSIONS` is empty, so this migration changes no
   behavior until you opt in. `manage_users` is deliberately absent from the recommended
   set: it is routine work for `hr_admin`/`people_manager`, and §6 is right that gating
   routine work is how the control ends up disabled.

   **UI:** `admin-ui` prompts automatically — any `403 ELEVATION_REQUIRED` opens the
   elevation modal and retries the original request on success
   (`components/ElevationGate.jsx`), so individual pages need no changes.

**Phase 4 — ✅ SHIPPED** (migration `c9d0e1f2a3b4`, 16 tests in `tests/test_zero_trust_phase4.py`)

10. ✅ **Single egress chokepoint** (`app/services/agent_egress.py`). Everything leaving
    ControlHub goes through `deliver()`, which closes two holes found while building it:

    - **Destinations were self-defining.** `_validate_destination_payload` checks the
      *shape* of a destination config, never its value — any Drive folder id or
      spreadsheet id was accepted. An attacker with admin access could point a
      destination at storage they own and publish through the normal, fully-approved,
      fully-audited flow. Now the real target ids must appear in
      `AGENT_EGRESS_DRIVE_FOLDERS` / `AGENT_EGRESS_SHEETS`, which live in **deployment
      config, not the database** — so compromising the application does not grant a new
      egress target.
    - **Time-of-check/time-of-use.** An approved request stored a destination *id*, and
      the config behind it was re-resolved at publish time, so a benign destination could
      be approved and then repointed. Requests now pin a fingerprint of the resolved
      target (`agent_request.destination_fingerprint`); publish recomputes it and refuses
      on drift. The fingerprint covers type + target only, so renaming a destination does
      not invalidate approved requests but repointing one does.

    The audit event records the **resolved target**, not just the destination id — the id
    is an indirection the attacker controls. Also records the impersonation identity used.

    *Verified end to end:* an admin with a **granted approval** publishing to a
    non-allowlisted folder gets `403 EGRESS_TARGET_NOT_ALLOWLISTED`; the sanctioned target
    still publishes.

11. 🟡 **Prompt-injection invariant — pinned, but note what this is.** ControlHub's agent
    has **no model in the loop**: `process_agent_request` reads the stored template and the
    approved request, and nothing else influences tool, field scope, or destination. That
    is already the property §2.5 asks for, so this is a **regression guard, not a fix for a
    live hole** — it exists because once an attacker is in the database they control the
    *content* of person records, and if data content could ever steer tool selection,
    injected text in a "notes" field becomes privilege escalation. Tests assert that row
    content cannot widen field scope or influence destination resolution, and that
    caller-supplied field selection is validated against the template.

    Added `assert_scope_integrity()`, which re-checks the projection immediately before
    rows become bytes — defense in depth so field scope does not rest on one upstream call
    staying correct forever.

12. 🟡 **Per-run identity — partial.** Destinations may now set `config.impersonate_user`
    to write as a narrowly scoped principal instead of one ambient `GOOGLE_IMPERSONATE_USER`
    account used for everything, and the identity used is recorded on every publish.
    **True per-run ephemeral credentials still need Google-side WIF/DWD configuration**
    and cannot be delivered from this repo alone.

**Phase 5 — ✅ SHIPPED as Terraform** (`infra/terraform/`, `terraform validate` + `tflint` clean, full `plan` verified)

13. 🟡 **Network controls — partially impossible here, and that matters.** §3.6 assumes
    ControlHub's compute sits in a VPC you control. **It does not** — the API and worker
    are containers on **Railway**; AWS provides only SES, SNS, S3, KMS, and CloudWatch.

    | §3.6 item | Status | Why |
    |---|---|---|
    | Default-deny egress from the app subnet | ❌ **Not possible** | No VPC or security groups to attach. The app-level chokepoint (`agent_egress.py`) and SSRF guard (`safe_http.py`) are the compensating controls — weaker, because both run *inside* the process an attacker controls. |
    | Block IMDS | ➖ **Not applicable** | No EC2 metadata service exists to reach. |
    | Split IAM roles for API vs worker | ✅ **Delivered** | As IAM *users* — Railway cannot assume a role. |

    **The largest remaining risk is credential theft from the Railway environment.** Static
    access keys cannot be scoped by network origin the way an instance role can. The IAM
    split shrinks what each stolen key is worth; it does not remove the exposure. Moving
    compute into a VPC is the structural fix, and would also unlock default-deny egress.

14. ✅ **Everything else in §3.6/§3.7**, in `infra/terraform/`:
    - **Split identities.** API gets KMS-secrets (context-bound), artifacts, and audit
      append — and is **explicitly denied** `ses:Send*`. Worker gets SES send (bound to the
      verified domains by a `ses:FromAddress` condition) and artifact read — and is
      **explicitly denied** the secrets key, on both the identity policy and the key policy.
      A compromised API cannot phish as `@webforxtech.com`; a compromised worker cannot read
      a single credential.
    - **KMS key policy enforces the encryption context.** `Decrypt` is granted only when
      `kms:EncryptionContext:app = controlhub`, matching what `secret_crypto.py` sets. This
      turns the per-purpose context from a convention our code follows into a boundary AWS
      enforces — §2.6's "network-layer twin" applied to crypto.
    - **Audit mirror the app cannot erase.** `DenyAuditMirrorTampering` denies `logs:Delete*`
      and `logs:PutRetentionPolicy` unconditionally; explicit Deny wins over any later Allow.
      Optional S3 Object Lock (COMPLIANCE) bucket for the stronger form.
    - **Detection** (§3.7): CloudTrail + alarms for KMS-decrypt spikes, SES send spikes, IAM
      mutations, and audit-chain divergence — routed to an SNS topic ControlHub has no
      permission to publish to or delete.

    This also provisions the two items Phases 2–4 flagged as "requires you": the secrets CMK
    and the audit log destination.

    *Access keys are deliberately not created in Terraform* — `aws_iam_access_key` writes the
    secret into state in plaintext, which would put long-lived AWS credentials in exactly the
    blast radius this phase exists to shrink. Created out of band; see the README.

**Phase 5 — detection**
13. Wire the §3.7 signals to the out-of-band sink with alarms that do not depend on ControlHub.

---

## 6. Honest limits of this design

- Zero trust does not survive a compromised *build pipeline* or a malicious *maintainer*.
  Signed images, branch protection, and reproducible builds are a separate workstream this
  document does not cover.
- ControlHub has **no device-identity signal at all** today (no mTLS, no device posture, no
  managed-device attestation). Full ZT normally treats device trust as a co-equal pillar
  alongside identity. Adding it means an identity-aware proxy in front of nginx and is a
  larger organizational decision than an application change — worth scoping separately.
- JIT elevation adds real operator friction. It is worth it for secrets, roles, SSO, and
  bulk export. Applying it to routine work will get it disabled, which is worse than not
  having it.
