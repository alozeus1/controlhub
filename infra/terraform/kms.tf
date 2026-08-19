# Customer-managed key for ControlHub secrets at rest (Phase 2, §3.2).
#
# The application never holds this key. It calls GenerateDataKey per write and
# Decrypt per read, which means every secret read is a CloudTrail event in an
# account the application cannot edit — that out-of-band record is the control,
# not the encryption itself.

resource "aws_kms_key" "secrets" {
  description             = "${var.name_prefix}-${var.environment} secrets envelope encryption"
  enable_key_rotation     = true
  deletion_window_in_days = 30
  policy                  = data.aws_iam_policy_document.secrets_key.json
}

resource "aws_kms_alias" "secrets" {
  name          = "alias/${var.name_prefix}-${var.environment}-secrets"
  target_key_id = aws_kms_key.secrets.key_id
}

data "aws_caller_identity" "current" {}

data "aws_iam_policy_document" "secrets_key" {
  # Account root retains administrative control. Without this the key can become
  # unmanageable — AWS explicitly warns that a policy with no root access can
  # only be recovered via support.
  statement {
    sid       = "AllowAccountAdministration"
    effect    = "Allow"
    actions   = ["kms:*"]
    resources = ["*"]

    principals {
      type        = "AWS"
      identifiers = ["arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"]
    }
  }

  # The API identity may use the key ONLY with the encryption context the
  # application actually sets (app/services/secret_crypto.py::_encryption_context
  # sets {"purpose": ..., "app": "controlhub"}).
  #
  # This is what makes the per-purpose context a real boundary rather than a
  # convention: a caller that omits or forges the context is refused by KMS, not
  # by our code. It is the "network-layer twin" principle applied to crypto —
  # an attacker executing inside the API process cannot decrypt by calling KMS
  # directly with a different context.
  statement {
    sid    = "AllowApplicationEnvelopeEncryption"
    effect = "Allow"

    actions = [
      "kms:GenerateDataKey",
      "kms:Decrypt",
      "kms:DescribeKey",
    ]
    resources = ["*"]

    principals {
      type        = "AWS"
      identifiers = [aws_iam_user.api.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "kms:EncryptionContext:app"
      values   = ["controlhub"]
    }
  }

  # The worker never reads secrets. Stating the boundary as an explicit Deny
  # means a future broad Allow cannot silently grant it — explicit Deny always
  # wins in IAM evaluation.
  statement {
    sid       = "DenyWorkerAccessToSecrets"
    effect    = "Deny"
    actions   = ["kms:Decrypt", "kms:GenerateDataKey"]
    resources = ["*"]

    principals {
      type        = "AWS"
      identifiers = [aws_iam_user.worker.arn]
    }
  }
}

# Separate key for artifacts/uploads. Deliberately NOT the secrets key: an
# artifact-storage grant should never imply the ability to decrypt credentials,
# and sharing one key makes the CloudTrail decrypt signal useless (every S3 read
# would be noise in the alarm that is supposed to catch secret exfiltration).
resource "aws_kms_key" "artifacts" {
  description             = "${var.name_prefix}-${var.environment} artifact and upload encryption"
  enable_key_rotation     = true
  deletion_window_in_days = 30
}

resource "aws_kms_alias" "artifacts" {
  name          = "alias/${var.name_prefix}-${var.environment}-artifacts"
  target_key_id = aws_kms_key.artifacts.key_id
}
