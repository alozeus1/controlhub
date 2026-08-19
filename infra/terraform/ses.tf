# SES configuration sets.
#
# Two sets, matching the split the application makes (SES_CONFIGURATION_SET vs
# SES_TRANSACTIONAL_CONFIGURATION_SET). Marketing volume and password-reset
# delivery must not share a reputation: a campaign complaint spike should not be
# able to stop people signing in.

resource "aws_sesv2_configuration_set" "transactional" {
  configuration_set_name = "${var.name_prefix}-${var.environment}-transactional"

  delivery_options {
    tls_policy = "REQUIRE"
  }

  reputation_options {
    reputation_metrics_enabled = true
  }

  sending_options {
    sending_enabled = true
  }

  suppression_options {
    # Bounces only. A complaint on a password reset must not suppress future
    # security email to that address — locking someone out of account recovery
    # is a worse outcome than an unwanted message.
    suppressed_reasons = ["BOUNCE"]
  }
}

resource "aws_sesv2_configuration_set" "campaigns" {
  configuration_set_name = "${var.name_prefix}-${var.environment}-campaigns"

  delivery_options {
    tls_policy = "REQUIRE"
  }

  reputation_options {
    reputation_metrics_enabled = true
  }

  sending_options {
    sending_enabled = true
  }

  suppression_options {
    suppressed_reasons = ["BOUNCE", "COMPLAINT"]
  }
}

# ─── Event feedback ───────────────────────────────────────────────────────────
#
# Bounce/complaint events go to SNS, which app/routes/campaigns.py consumes via
# the public webhook. That endpoint verifies the SNS signature and enforces a
# TopicArn allowlist (app/services/email_ses.py::verify_sns_message), so this
# topic ARN must match SNS_TOPIC_ARN in the application environment.

resource "aws_sns_topic" "ses_events" {
  name              = "${var.name_prefix}-${var.environment}-ses-events"
  kms_master_key_id = aws_kms_key.artifacts.id
}

data "aws_iam_policy_document" "ses_events" {
  statement {
    sid       = "AllowSesPublish"
    effect    = "Allow"
    actions   = ["SNS:Publish"]
    resources = [aws_sns_topic.ses_events.arn]

    principals {
      type        = "Service"
      identifiers = ["ses.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "AWS:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }
  }
}

resource "aws_sns_topic_policy" "ses_events" {
  arn    = aws_sns_topic.ses_events.arn
  policy = data.aws_iam_policy_document.ses_events.json
}

resource "aws_sesv2_configuration_set_event_destination" "transactional" {
  configuration_set_name = aws_sesv2_configuration_set.transactional.configuration_set_name
  event_destination_name = "sns-events"

  event_destination {
    enabled              = true
    matching_event_types = ["BOUNCE", "COMPLAINT", "REJECT", "DELIVERY", "RENDERING_FAILURE"]

    sns_destination {
      topic_arn = aws_sns_topic.ses_events.arn
    }
  }
}

resource "aws_sesv2_configuration_set_event_destination" "campaigns" {
  configuration_set_name = aws_sesv2_configuration_set.campaigns.configuration_set_name
  event_destination_name = "sns-events"

  event_destination {
    enabled              = true
    matching_event_types = ["BOUNCE", "COMPLAINT", "REJECT", "DELIVERY", "OPEN", "CLICK"]

    sns_destination {
      topic_arn = aws_sns_topic.ses_events.arn
    }
  }
}
