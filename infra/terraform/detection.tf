# Detection (§3.7).
#
# Assume the preventive controls fail. These alarms watch the signals that
# distinguish normal operation from an attacker using stolen credentials — and
# they route to a topic ControlHub has no permission to publish to or delete,
# so an attacker inside the application cannot silence them.

resource "aws_sns_topic" "security_alerts" {
  name              = "${var.name_prefix}-${var.environment}-security-alerts"
  kms_master_key_id = aws_kms_key.artifacts.id
}

resource "aws_sns_topic_subscription" "security_alerts_email" {
  count = var.alert_email != "" ? 1 : 0

  topic_arn = aws_sns_topic.security_alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

# ─── CloudTrail: the record of who called KMS and SES ─────────────────────────

resource "aws_s3_bucket" "trail" {
  count         = var.enable_cloudtrail ? 1 : 0
  bucket        = "${var.name_prefix}-${var.environment}-cloudtrail-${data.aws_caller_identity.current.account_id}"
  force_destroy = false
}

resource "aws_s3_bucket_public_access_block" "trail" {
  count = var.enable_cloudtrail ? 1 : 0

  bucket                  = aws_s3_bucket.trail[0].id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

data "aws_iam_policy_document" "trail" {
  count = var.enable_cloudtrail ? 1 : 0

  statement {
    sid       = "AWSCloudTrailAclCheck"
    effect    = "Allow"
    actions   = ["s3:GetBucketAcl"]
    resources = [aws_s3_bucket.trail[0].arn]

    principals {
      type        = "Service"
      identifiers = ["cloudtrail.amazonaws.com"]
    }
  }

  statement {
    sid       = "AWSCloudTrailWrite"
    effect    = "Allow"
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.trail[0].arn}/AWSLogs/${data.aws_caller_identity.current.account_id}/*"]

    principals {
      type        = "Service"
      identifiers = ["cloudtrail.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "s3:x-amz-acl"
      values   = ["bucket-owner-full-control"]
    }
  }
}

resource "aws_s3_bucket_policy" "trail" {
  count = var.enable_cloudtrail ? 1 : 0

  bucket = aws_s3_bucket.trail[0].id
  policy = data.aws_iam_policy_document.trail[0].json
}

resource "aws_cloudwatch_log_group" "trail" {
  count = var.enable_cloudtrail ? 1 : 0

  name              = "/${var.name_prefix}/${var.environment}/cloudtrail"
  retention_in_days = 90
}

resource "aws_iam_role" "trail_to_logs" {
  count = var.enable_cloudtrail ? 1 : 0

  name = "${var.name_prefix}-${var.environment}-trail-to-logs"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "cloudtrail.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "trail_to_logs" {
  count = var.enable_cloudtrail ? 1 : 0

  name = "write-trail-events"
  role = aws_iam_role.trail_to_logs[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
      Resource = "${aws_cloudwatch_log_group.trail[0].arn}:*"
    }]
  })
}

resource "aws_cloudtrail" "main" {
  count = var.enable_cloudtrail ? 1 : 0

  name                          = "${var.name_prefix}-${var.environment}"
  s3_bucket_name                = aws_s3_bucket.trail[0].id
  include_global_service_events = true
  is_multi_region_trail         = true
  enable_log_file_validation    = true

  cloud_watch_logs_group_arn = "${aws_cloudwatch_log_group.trail[0].arn}:*"
  cloud_watch_logs_role_arn  = aws_iam_role.trail_to_logs[0].arn

  depends_on = [aws_s3_bucket_policy.trail]
}

# ─── Metric filters + alarms ──────────────────────────────────────────────────

# Bulk secret exfiltration. Normal operation decrypts a handful of secrets a
# day; reading the whole vault produces a very different shape. This is the
# signal KMS envelope encryption exists to create.
resource "aws_cloudwatch_log_metric_filter" "kms_decrypt" {
  count = var.enable_cloudtrail ? 1 : 0

  name           = "${var.name_prefix}-${var.environment}-kms-decrypt"
  log_group_name = aws_cloudwatch_log_group.trail[0].name
  pattern        = "{ ($.eventSource = \"kms.amazonaws.com\") && ($.eventName = \"Decrypt\") }"

  metric_transformation {
    name      = "KmsDecryptCalls"
    namespace = "ControlHub/${var.environment}"
    value     = "1"
    unit      = "Count"
  }
}

resource "aws_cloudwatch_metric_alarm" "kms_decrypt_spike" {
  count = var.enable_cloudtrail ? 1 : 0

  alarm_name          = "${var.name_prefix}-${var.environment}-kms-decrypt-spike"
  alarm_description   = "Unusual volume of secret decryptions — possible bulk exfiltration."
  namespace           = "ControlHub/${var.environment}"
  metric_name         = "KmsDecryptCalls"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = var.kms_decrypt_alarm_threshold
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.security_alerts.arn]
}

# Failed elevation reauth / IAM changes are application-level; these two are the
# AWS-level equivalents an attacker needs for persistence.
resource "aws_cloudwatch_log_metric_filter" "iam_changes" {
  count = var.enable_cloudtrail ? 1 : 0

  name           = "${var.name_prefix}-${var.environment}-iam-changes"
  log_group_name = aws_cloudwatch_log_group.trail[0].name
  pattern        = "{ ($.eventSource = \"iam.amazonaws.com\") && (($.eventName = \"CreateAccessKey\") || ($.eventName = \"AttachUserPolicy\") || ($.eventName = \"PutUserPolicy\") || ($.eventName = \"CreateUser\")) }"

  metric_transformation {
    name      = "IamMutations"
    namespace = "ControlHub/${var.environment}"
    value     = "1"
    unit      = "Count"
  }
}

resource "aws_cloudwatch_metric_alarm" "iam_changes" {
  count = var.enable_cloudtrail ? 1 : 0

  alarm_name          = "${var.name_prefix}-${var.environment}-iam-mutation"
  alarm_description   = "IAM identity or key created/modified — the usual persistence step."
  namespace           = "ControlHub/${var.environment}"
  metric_name         = "IamMutations"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.security_alerts.arn]
}

# Phishing from a verified domain is one of the most valuable things a stolen
# key buys — the mail passes SPF/DKIM/DMARC because it genuinely is you.
resource "aws_cloudwatch_metric_alarm" "ses_send_spike" {
  alarm_name          = "${var.name_prefix}-${var.environment}-ses-send-spike"
  alarm_description   = "Send volume spike — possible phishing from a verified domain."
  namespace           = "AWS/SES"
  metric_name         = "Send"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = var.ses_send_alarm_threshold
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.security_alerts.arn]
}

# Fed by the scheduled `flask audit verify` job, which exits non-zero on chain
# divergence. Publish 1 on failure / 0 on success:
#
#   flask audit verify || aws cloudwatch put-metric-data \
#     --namespace "ControlHub/${var.environment}" \
#     --metric-name AuditChainDivergence --value 1
#
# See README.md — this alarm is inert until something publishes the metric.
resource "aws_cloudwatch_metric_alarm" "audit_chain_divergence" {
  alarm_name          = "${var.name_prefix}-${var.environment}-audit-chain-divergence"
  alarm_description   = "Audit hash chain failed verification — history was altered. Investigate immediately."
  namespace           = "ControlHub/${var.environment}"
  metric_name         = "AuditChainDivergence"
  statistic           = "Maximum"
  period              = 3600
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.security_alerts.arn]
}
