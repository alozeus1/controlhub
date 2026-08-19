# Agent artifact storage.
#
# Artifacts are generated exports of employee data. They are transient by
# design — the lifecycle rule below is a security control, not housekeeping:
# an artifact that still exists is still exfiltratable.

locals {
  artifacts_bucket_name = (
    var.artifacts_bucket_name != ""
    ? var.artifacts_bucket_name
    : "${var.name_prefix}-${var.environment}-artifacts-${data.aws_caller_identity.current.account_id}"
  )
}

resource "aws_s3_bucket" "artifacts" {
  count  = var.create_artifacts_bucket ? 1 : 0
  bucket = local.artifacts_bucket_name
}

resource "aws_s3_bucket_public_access_block" "artifacts" {
  count = var.create_artifacts_bucket ? 1 : 0

  bucket                  = aws_s3_bucket.artifacts[0].id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "artifacts" {
  count = var.create_artifacts_bucket ? 1 : 0

  bucket = aws_s3_bucket.artifacts[0].id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.artifacts.arn
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_versioning" "artifacts" {
  count = var.create_artifacts_bucket ? 1 : 0

  bucket = aws_s3_bucket.artifacts[0].id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "artifacts" {
  count = var.create_artifacts_bucket ? 1 : 0

  bucket     = aws_s3_bucket.artifacts[0].id
  depends_on = [aws_s3_bucket_versioning.artifacts]

  rule {
    id     = "expire-generated-artifacts"
    status = "Enabled"

    filter {}

    expiration {
      days = var.artifact_expiry_days
    }

    noncurrent_version_expiration {
      noncurrent_days = 7
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}

data "aws_iam_policy_document" "artifacts" {
  count = var.create_artifacts_bucket ? 1 : 0

  statement {
    sid       = "DenyInsecureTransport"
    effect    = "Deny"
    actions   = ["s3:*"]
    resources = [aws_s3_bucket.artifacts[0].arn, "${aws_s3_bucket.artifacts[0].arn}/*"]

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

  # Presigned download URLs are the one legitimate way artifacts leave S3, and
  # they are already short-lived and authorization-checked in the application
  # (AGENT_ARTIFACT_URL_EXPIRY_SECONDS). Refusing unencrypted uploads keeps a
  # future code path from writing an artifact in the clear.
  statement {
    sid       = "DenyUnencryptedUploads"
    effect    = "Deny"
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.artifacts[0].arn}/*"]

    principals {
      type        = "AWS"
      identifiers = ["*"]
    }

    condition {
      test     = "StringNotEquals"
      variable = "s3:x-amz-server-side-encryption"
      values   = ["aws:kms"]
    }
  }
}

resource "aws_s3_bucket_policy" "artifacts" {
  count = var.create_artifacts_bucket ? 1 : 0

  bucket = aws_s3_bucket.artifacts[0].id
  policy = data.aws_iam_policy_document.artifacts[0].json
}
