output "app_env" {
  description = "ControlHub environment variables to set from this stack. Paste into the Railway secret store."

  value = {
    SECRET_KMS_KEY_ID                   = aws_kms_alias.secrets.name
    SECRET_KMS_PROVIDER                 = "aws"
    AUDIT_MIRROR_SINK                   = "cloudwatch"
    AUDIT_MIRROR_LOG_GROUP              = aws_cloudwatch_log_group.audit.name
    AUDIT_MIRROR_LOG_STREAM             = "audit-chain"
    SES_CONFIGURATION_SET               = aws_sesv2_configuration_set.campaigns.configuration_set_name
    SES_TRANSACTIONAL_CONFIGURATION_SET = aws_sesv2_configuration_set.transactional.configuration_set_name
    SES_ALLOWED_SENDER_DOMAINS          = join(",", var.ses_sending_domains)
    SNS_TOPIC_ARN                       = aws_sns_topic.ses_events.arn
    ARTIFACTS_KMS_KEY_ARN               = aws_kms_key.artifacts.arn
    S3_BUCKET_NAME                      = var.create_artifacts_bucket ? aws_s3_bucket.artifacts[0].id : ""
    AWS_REGION                          = var.aws_region
  }
}

output "api_user_name" {
  description = "IAM user for the API service. Create its access key out of band (see README)."
  value       = aws_iam_user.api.name
}

output "worker_user_name" {
  description = "IAM user for the RQ worker. Create its access key out of band (see README)."
  value       = aws_iam_user.worker.name
}

output "secrets_kms_key_arn" {
  description = "CMK for secret envelope encryption."
  value       = aws_kms_key.secrets.arn
}

output "security_alerts_topic_arn" {
  description = "Security alarm topic. Subscribe something that is NOT ControlHub-managed."
  value       = aws_sns_topic.security_alerts.arn
}

output "audit_worm_bucket" {
  description = "WORM audit bucket, when enabled."
  value       = var.enable_audit_worm_bucket ? aws_s3_bucket.audit_worm[0].id : null
}

output "post_apply_checklist" {
  description = "Steps Terraform deliberately does not perform."

  value = [
    "1. Create access keys out of band (they are NOT in Terraform state by design): aws iam create-access-key --user-name ${aws_iam_user.api.name}",
    "2. Set the app_env values above in the Railway secret store for the API and worker services.",
    "3. Run `flask secrets rewrap` once SECRET_KMS_KEY_ID is live to migrate fernet:v1: values.",
    "4. Confirm the alert_email subscription (AWS sends a confirmation link).",
    "5. Apply scripts/sql/audit_log_append_only.sql to the managed Postgres — Terraform does not manage that database.",
    "6. Schedule `flask audit mirror` (1 min) and `flask audit verify` (hourly) on the platform scheduler.",
  ]
}
