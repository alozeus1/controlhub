# Out-of-band audit mirror destination (Phase 2, §3.3).
#
# app/services/audit_sink.py ships sealed audit rows here. The hash chain makes
# tampering detectable; this copy is what you compare against, which only works
# because the application identity is denied every delete/retention action (see
# iam.tf::DenyAuditMirrorTampering).

resource "aws_cloudwatch_log_group" "audit" {
  name              = "/${var.name_prefix}/${var.environment}/audit"
  retention_in_days = var.audit_log_retention_days
  kms_key_id        = aws_kms_key.artifacts.arn
}

# ─── Optional WORM mirror ─────────────────────────────────────────────────────
#
# CloudWatch retention is a policy the account owner can shorten. Object Lock in
# COMPLIANCE mode is not: for the retention period nobody can delete or
# overwrite an object, including the root account. That is the strongest form of
# the §3.3 control and the reason it is opt-in — it is genuinely irreversible.

resource "aws_s3_bucket" "audit_worm" {
  count = var.enable_audit_worm_bucket ? 1 : 0

  bucket              = "${var.name_prefix}-${var.environment}-audit-worm-${data.aws_caller_identity.current.account_id}"
  object_lock_enabled = true

  # Objects under a compliance-mode lock cannot be deleted until retention
  # expires, so Terraform cannot destroy this bucket either. That is intended.
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_object_lock_configuration" "audit_worm" {
  count = var.enable_audit_worm_bucket ? 1 : 0

  bucket = aws_s3_bucket.audit_worm[0].id

  rule {
    default_retention {
      mode = "COMPLIANCE"
      days = var.audit_worm_retention_days
    }
  }
}

resource "aws_s3_bucket_versioning" "audit_worm" {
  count = var.enable_audit_worm_bucket ? 1 : 0

  bucket = aws_s3_bucket.audit_worm[0].id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "audit_worm" {
  count = var.enable_audit_worm_bucket ? 1 : 0

  bucket = aws_s3_bucket.audit_worm[0].id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.artifacts.arn
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "audit_worm" {
  count = var.enable_audit_worm_bucket ? 1 : 0

  bucket                  = aws_s3_bucket.audit_worm[0].id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

data "aws_iam_policy_document" "audit_worm" {
  count = var.enable_audit_worm_bucket ? 1 : 0

  # The application may append audit objects and nothing else — no delete, no
  # overwrite, no version removal.
  statement {
    sid    = "AppendOnlyForApplication"
    effect = "Allow"
    actions = [
      "s3:PutObject",
    ]
    resources = ["${aws_s3_bucket.audit_worm[0].arn}/*"]

    principals {
      type        = "AWS"
      identifiers = [aws_iam_user.api.arn]
    }
  }

  statement {
    sid    = "DenyDeletionToEveryone"
    effect = "Deny"
    actions = [
      "s3:DeleteObject",
      "s3:DeleteObjectVersion",
      "s3:PutBucketObjectLockConfiguration",
    ]
    resources = ["${aws_s3_bucket.audit_worm[0].arn}/*"]

    principals {
      type        = "AWS"
      identifiers = ["*"]
    }
  }

  statement {
    sid       = "DenyInsecureTransport"
    effect    = "Deny"
    actions   = ["s3:*"]
    resources = [aws_s3_bucket.audit_worm[0].arn, "${aws_s3_bucket.audit_worm[0].arn}/*"]

    principals {
      type        = "AWS"
      identifiers = ["*"]
    }

    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "audit_worm" {
  count = var.enable_audit_worm_bucket ? 1 : 0

  bucket = aws_s3_bucket.audit_worm[0].id
  policy = data.aws_iam_policy_document.audit_worm[0].json
}
