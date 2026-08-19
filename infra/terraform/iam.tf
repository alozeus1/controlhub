# Split AWS identities for the API and the worker (§3.6).
#
# ControlHub's compute runs on Railway, so these are IAM *users* with static
# access keys rather than roles — Railway has no way to assume an AWS role. If
# the app ever moves to AWS compute, replace these with roles and delete the
# keys; the policies below attach to either.
#
# The split is the point. Today one credential set does everything, so a
# compromised API process can send email as @webforxtech.com and a compromised
# worker can decrypt every stored secret. After this:
#
#   API    → KMS secrets (context-bound), artifacts read/write, audit log append
#   Worker → SES send (from-address bound), artifacts read
#
# Neither can do the other's job.
#
# NOTE: access keys are deliberately NOT created here. `aws_iam_access_key`
# stores the secret in Terraform state in plaintext, which would put long-lived
# AWS credentials in the same blast radius this phase exists to shrink. Create
# them out of band — see README.md.

resource "aws_iam_user" "api" {
  name = "${var.name_prefix}-${var.environment}-api"
  path = "/controlhub/"
}

resource "aws_iam_user" "worker" {
  name = "${var.name_prefix}-${var.environment}-worker"
  path = "/controlhub/"
}

# ─── API policy ───────────────────────────────────────────────────────────────

data "aws_iam_policy_document" "api" {
  # Artifact storage. Scoped to the bucket's object space, not the account's.
  dynamic "statement" {
    for_each = var.create_artifacts_bucket ? [1] : []

    content {
      sid    = "ArtifactObjectAccess"
      effect = "Allow"
      actions = [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject",
      ]
      resources = ["${aws_s3_bucket.artifacts[0].arn}/*"]
    }
  }

  dynamic "statement" {
    for_each = var.create_artifacts_bucket ? [1] : []

    content {
      sid       = "ArtifactBucketListing"
      effect    = "Allow"
      actions   = ["s3:ListBucket"]
      resources = [aws_s3_bucket.artifacts[0].arn]
    }
  }

  statement {
    sid    = "ArtifactEncryption"
    effect = "Allow"
    actions = [
      "kms:GenerateDataKey",
      "kms:Decrypt",
    ]
    resources = [aws_kms_key.artifacts.arn]
  }

  # Audit mirror: append only. The matching explicit Deny is below.
  statement {
    sid    = "AuditMirrorAppend"
    effect = "Allow"
    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents",
      "logs:DescribeLogStreams",
    ]
    resources = ["${aws_cloudwatch_log_group.audit.arn}:*"]
  }

  # The whole value of the mirror is that the application cannot rewrite it.
  # Explicit Deny beats any Allow, including one added later by mistake or by
  # an attacker who can edit IAM but not this Terraform.
  statement {
    sid    = "DenyAuditMirrorTampering"
    effect = "Deny"
    actions = [
      "logs:DeleteLogGroup",
      "logs:DeleteLogStream",
      "logs:DeleteRetentionPolicy",
      "logs:PutRetentionPolicy",
    ]
    resources = ["*"]
  }

  # The API does not send email. The worker does.
  statement {
    sid       = "DenyEmailSending"
    effect    = "Deny"
    actions   = ["ses:SendEmail", "ses:SendRawEmail", "ses:SendBulkEmail"]
    resources = ["*"]
  }
}

resource "aws_iam_user_policy" "api" {
  name   = "${var.name_prefix}-${var.environment}-api"
  user   = aws_iam_user.api.name
  policy = data.aws_iam_policy_document.api.json
}

# ─── Worker policy ────────────────────────────────────────────────────────────

data "aws_iam_policy_document" "worker" {
  # SES send, bound to the verified domains at the IAM layer. This is the
  # enforcement twin of SES_ALLOWED_SENDER_DOMAINS in the application: the app
  # check gives a clean error, this one holds even if the app is compromised.
  statement {
    sid    = "SendAsVerifiedDomainsOnly"
    effect = "Allow"
    actions = [
      "ses:SendEmail",
      "ses:SendRawEmail",
      "ses:SendBulkEmail",
    ]
    resources = ["*"]

    condition {
      test     = "StringLike"
      variable = "ses:FromAddress"
      values   = [for domain in var.ses_sending_domains : "*@${domain}"]
    }
  }

  statement {
    sid    = "SesTelemetry"
    effect = "Allow"
    actions = [
      "ses:GetAccount",
      "ses:GetSendQuota",
    ]
    resources = ["*"]
  }

  dynamic "statement" {
    for_each = var.create_artifacts_bucket ? [1] : []

    content {
      sid       = "ReadArtifactsForDelivery"
      effect    = "Allow"
      actions   = ["s3:GetObject"]
      resources = ["${aws_s3_bucket.artifacts[0].arn}/*"]
    }
  }

  statement {
    sid       = "DecryptArtifactsOnly"
    effect    = "Allow"
    actions   = ["kms:Decrypt"]
    resources = [aws_kms_key.artifacts.arn]
  }

  # Belt and braces alongside the Deny in the secrets key policy: the worker has
  # no business reading credentials, stated on both the identity and the key.
  statement {
    sid       = "DenySecretsKeyAccess"
    effect    = "Deny"
    actions   = ["kms:Decrypt", "kms:GenerateDataKey", "kms:DescribeKey"]
    resources = [aws_kms_key.secrets.arn]
  }
}

resource "aws_iam_user_policy" "worker" {
  name   = "${var.name_prefix}-${var.environment}-worker"
  user   = aws_iam_user.worker.name
  policy = data.aws_iam_policy_document.worker.json
}
