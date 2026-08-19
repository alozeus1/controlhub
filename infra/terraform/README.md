# ControlHub — Zero Trust Phase 5 (AWS)

Terraform for the infrastructure half of
[`docs/ZERO_TRUST_ASSUME_BREACH_DESIGN.md`](../../docs/ZERO_TRUST_ASSUME_BREACH_DESIGN.md).
It also provisions the two things Phases 2–4 flagged as "requires you": the secrets
CMK, and an audit log destination the application cannot erase.

---

## Read this first: what Phase 5 can and cannot be here

The design document's §3.6 assumes ControlHub's compute runs in a VPC you control.
**It does not.** The API and worker are containers on **Railway**; AWS provides SES,
SNS, S3, KMS, and CloudWatch. That makes three items from §3.6 impossible as written:

| §3.6 item | Status on Railway | What to do instead |
|---|---|---|
| Default-deny egress from the app subnet | **Not possible** — no VPC or security groups to attach | Compensating control: the app-level egress chokepoint (`app/services/agent_egress.py`) and SSRF guard (`app/services/safe_http.py`). Weaker: both run *inside* the process an attacker controls. This gap only closes by moving compute to AWS/Fly with a VPC. |
| Block IMDS (`169.254.169.254`) | **Not applicable** — no EC2 instance metadata service to reach | Nothing to do. The equivalent risk is a stolen Railway env var, addressed by the IAM split below. |
| Split IAM roles for API vs worker | **Possible, and delivered** — as IAM *users*, since Railway cannot assume a role | `iam.tf`. Move to roles if compute ever lands on AWS. |

Everything else in §3.6/§3.7 is delivered.

**The single largest remaining risk is credential theft from the Railway environment.**
Static access keys cannot be scoped by network origin the way an instance role can. The
IAM split below shrinks what each stolen key is worth; it does not remove the exposure.
If that risk matters more than the migration cost, moving compute into a VPC is the
structural fix — and then default-deny egress becomes available too.

---

## What this creates

| File | Purpose |
|---|---|
| `kms.tf` | Secrets CMK with an **encryption-context condition**, plus a separate artifacts key |
| `iam.tf` | Split API / worker identities with least-privilege policies and explicit denies |
| `audit.tf` | CloudWatch audit mirror group; optional S3 **Object Lock (COMPLIANCE)** bucket |
| `s3.tf` | Artifacts bucket — SSE-KMS, TLS-only, public access blocked, lifecycle expiry |
| `ses.tf` | Transactional and campaign configuration sets, SNS event feedback |
| `detection.tf` | CloudTrail, metric filters, and the §3.7 alarms → a topic ControlHub cannot touch |

### The two controls worth understanding

**1. The KMS key policy enforces the encryption context.** `secret_crypto.py` sets
`{"purpose": ..., "app": "controlhub"}` on every envelope operation. `kms.tf` grants
`Decrypt` **only** when `kms:EncryptionContext:app = controlhub`. That turns the
per-purpose context from a convention our code follows into a boundary AWS enforces —
an attacker executing inside the API process cannot call KMS directly with a different
context to read secrets out of band.

**2. The API identity is explicitly denied audit deletion.** `DenyAuditMirrorTampering`
denies `logs:Delete*` and `logs:PutRetentionPolicy` unconditionally. Explicit Deny wins
over any Allow in IAM, including one added later by accident or by an attacker who can
edit IAM but not this Terraform. Without it the mirror is a convenience copy, not
evidence.

The API is also denied `ses:Send*`, and the worker is denied the secrets key — on both
the identity policy and the key policy. A compromised API cannot phish as
`@webforxtech.com`; a compromised worker cannot read a single credential.

---

## Applying

```bash
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars   # edit alert_email at minimum
terraform init
terraform plan
terraform apply
```

Configure remote state before the first production apply — see the commented backend
block in `versions.tf`. This stack owns the secrets key policy; local state is one
laptop away from an outage.

### Post-apply (Terraform deliberately does not do these)

**1. Create access keys out of band.** `aws_iam_access_key` writes the secret into
Terraform state in plaintext, which would put long-lived AWS credentials in exactly the
blast radius this phase exists to shrink.

```bash
aws iam create-access-key --user-name "$(terraform output -raw api_user_name)"
aws iam create-access-key --user-name "$(terraform output -raw worker_user_name)"
```

Put the API key on the API service and the worker key on the worker service — **not the
same key on both**, or the split buys nothing.

**2. Set the app environment** from `terraform output app_env` in the Railway secret
store for both services.

**3. Migrate stored secrets onto KMS** once `SECRET_KMS_KEY_ID` is live:

```bash
flask secrets rewrap --dry-run
flask secrets rewrap
```

Keep `SECRET_ENCRYPTION_KEYS` set until this reports `failed: 0` — it is what decrypts
the not-yet-migrated rows.

**4. Confirm the alert subscription.** AWS emails a confirmation link; the topic is inert
until someone clicks it.

**5. Apply the append-only audit grant** to the managed Postgres (Neon/Railway/RDS —
Terraform does not manage that database):

```bash
psql "$SQLALCHEMY_DATABASE_URI" -v app_role=controlhub_app \
  -f ../../scripts/sql/audit_log_append_only.sql
```

Requires the app to connect as a **non-owner** role — ownership implies full DML
regardless of grants. The script documents the check.

**6. Schedule the jobs** on the platform scheduler:

| Command | Frequency |
|---|---|
| `flask audit mirror` | every minute |
| `flask audit verify` | hourly |

Publish the verify result so the alarm has a metric to watch:

```bash
flask audit verify \
  && aws cloudwatch put-metric-data --namespace "ControlHub/prod" \
       --metric-name AuditChainDivergence --value 0 \
  || aws cloudwatch put-metric-data --namespace "ControlHub/prod" \
       --metric-name AuditChainDivergence --value 1
```

The `audit_chain_divergence` alarm is inert until something publishes this metric.

---

## Alarms

| Alarm | Catches |
|---|---|
| `kms-decrypt-spike` | Bulk secret exfiltration — the signal envelope encryption exists to create |
| `audit-chain-divergence` | Audit history was altered |
| `ses-send-spike` | Phishing from a verified domain (passes SPF/DKIM/DMARC because it is genuinely you) |
| `iam-mutation` | Access key or policy created — the usual persistence step |

`alert_email` **must not** be a ControlHub-managed mailbox. An alert an attacker can read
or silence from inside the system they just compromised is not an alert.

Tune `kms_decrypt_alarm_threshold` and `ses_send_alarm_threshold` from a week of real
data — defaults are starting points, and an alarm that cries wolf gets muted.

---

## Notes on irreversible settings

- `enable_audit_worm_bucket` uses Object Lock in **COMPLIANCE** mode: for the retention
  period nobody can delete or overwrite an object, *including the root account*. That is
  the point, and the reason it is off by default. You will pay storage for the full
  window, and `terraform destroy` cannot remove the bucket.
- Both KMS keys have a 30-day deletion window and rotation enabled. Deleting the secrets
  key makes every `kms:v1:` ciphertext permanently unreadable — run `flask secrets rewrap`
  onto a new key first if you ever need to retire it.
