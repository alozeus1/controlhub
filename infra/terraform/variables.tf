variable "aws_region" {
  description = "AWS region for all resources."
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Deployment environment. Used in resource names, so prod and staging can coexist in one account."
  type        = string
  default     = "prod"

  validation {
    condition     = contains(["prod", "staging", "dev"], var.environment)
    error_message = "environment must be one of: prod, staging, dev."
  }
}

variable "name_prefix" {
  description = "Prefix for every created resource name."
  type        = string
  default     = "controlhub"
}

# ─── Sender identities ────────────────────────────────────────────────────────

variable "ses_sending_domains" {
  description = <<-EOT
    Verified SES domains this deployment may send as. Enforced at the IAM layer
    via a ses:FromAddress condition, so it holds even if the application-level
    SES_ALLOWED_SENDER_DOMAINS check is bypassed or the code is modified.
  EOT
  type        = list(string)
  default     = ["webforxtech.com", "dev.webforxtech.com"]

  validation {
    condition     = length(var.ses_sending_domains) > 0
    error_message = "At least one sending domain is required; an empty list would permit sending as anyone."
  }
}

# ─── Audit mirror ─────────────────────────────────────────────────────────────

variable "audit_log_retention_days" {
  description = "CloudWatch retention for the audit mirror. Must outlast your incident-discovery window."
  type        = number
  default     = 400
}

variable "enable_audit_worm_bucket" {
  description = <<-EOT
    Create an S3 bucket with Object Lock in COMPLIANCE mode for the audit mirror.
    Compliance mode cannot be disabled or shortened by anyone, including the root
    account, for the retention period — that is the point, and also why it is
    opt-in. Objects cannot be deleted until retention expires, and you will pay
    storage for the full window.
  EOT
  type        = bool
  default     = false
}

variable "audit_worm_retention_days" {
  description = "Object Lock retention for the WORM audit bucket. Irreversible once objects land."
  type        = number
  default     = 365
}

# ─── Optional buckets ─────────────────────────────────────────────────────────

variable "create_artifacts_bucket" {
  description = "Create the agent artifacts bucket. Set false if it already exists and is managed elsewhere."
  type        = bool
  default     = true
}

variable "artifacts_bucket_name" {
  description = "Agent artifacts bucket name. Must be globally unique."
  type        = string
  default     = ""
}

variable "artifact_expiry_days" {
  description = "Lifecycle expiry for generated artifacts. Exports are transient; keeping them is standing exposure."
  type        = number
  default     = 30
}

# ─── Alerting ─────────────────────────────────────────────────────────────────

variable "alert_email" {
  description = <<-EOT
    Address for security alarms. MUST NOT be a ControlHub-managed mailbox: an
    alert an attacker can read or silence from inside the system they just
    compromised is not an alert. Leave empty to create the topic without a
    subscription and wire it yourself (PagerDuty, Slack via chatbot, etc.).
  EOT
  type        = string
  default     = ""
}

variable "kms_decrypt_alarm_threshold" {
  description = <<-EOT
    kms:Decrypt calls in a 5-minute window that trip the exfiltration alarm.
    Normal operation decrypts a handful; reading every secret in the vault looks
    very different. Tune from a week of CloudTrail data.
  EOT
  type        = number
  default     = 50
}

variable "ses_send_alarm_threshold" {
  description = "Emails sent in 5 minutes that trip the alarm. Catches a compromised key phishing from a verified domain."
  type        = number
  default     = 500
}

variable "enable_cloudtrail" {
  description = <<-EOT
    Create a CloudTrail for KMS/SES API visibility. Set false if the account is
    already covered by an organization trail — a second trail duplicates cost
    without adding coverage.
  EOT
  type        = bool
  default     = true
}
