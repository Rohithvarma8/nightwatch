data "aws_region" "current" {}
data "aws_caller_identity" "current" {}

locals {
  name = "${var.name_prefix}-notifier"
}

resource "aws_sns_topic" "notify" {
  name = "${var.name_prefix}-notify"
}

resource "aws_ssm_parameter" "ntfy_topic" {
  name  = "/${var.name_prefix}/ntfy-topic"
  type  = "SecureString"
  value = var.ntfy_topic
}

# Creating this sends a verification email; delivery fails until the link is clicked.
resource "aws_sesv2_email_identity" "sender" {
  email_identity = var.ses_sender_email
}

resource "aws_cloudwatch_log_group" "this" {
  name              = "/aws/lambda/${local.name}"
  retention_in_days = var.log_retention_days
}

data "aws_iam_policy_document" "assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "this" {
  name               = "${local.name}-lambda"
  assume_role_policy = data.aws_iam_policy_document.assume.json
}

data "aws_iam_policy_document" "this" {
  statement {
    sid       = "Logs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.this.arn}:*"]
  }

  statement {
    sid       = "ReadContacts"
    actions   = ["dynamodb:GetItem"]
    resources = [var.table_arn]
    condition {
      test     = "ForAllValues:StringLike"
      variable = "dynamodb:LeadingKeys"
      values   = ["HH#*"]
    }
  }

  statement {
    sid       = "ReadNtfyTopic"
    actions   = ["ssm:GetParameter"]
    resources = [aws_ssm_parameter.ntfy_topic.arn]
  }

  statement {
    sid       = "SendEmail"
    actions   = ["ses:SendEmail"]
    resources = ["arn:aws:ses:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:identity/*"]
  }
}

resource "aws_iam_role_policy" "this" {
  name   = "notifier"
  role   = aws_iam_role.this.id
  policy = data.aws_iam_policy_document.this.json
}

resource "aws_lambda_function" "this" {
  function_name    = local.name
  role             = aws_iam_role.this.arn
  runtime          = "python3.12"
  architectures    = ["arm64"]
  handler          = "nightwatch_pipeline.notify.handler.handler"
  filename         = var.zip_path
  source_code_hash = filebase64sha256(var.zip_path)
  memory_size      = 256
  timeout          = 15 # ntfy 3 s + SES

  environment {
    variables = {
      NIGHTWATCH_TABLE = var.table_name
      NTFY_TOPIC_PARAM = aws_ssm_parameter.ntfy_topic.name
      SES_SENDER       = var.ses_sender_email
    }
  }

  depends_on = [aws_cloudwatch_log_group.this, aws_iam_role_policy.this]
}

resource "aws_sns_topic_subscription" "notifier" {
  topic_arn = aws_sns_topic.notify.arn
  protocol  = "lambda"
  endpoint  = aws_lambda_function.this.arn
}

resource "aws_lambda_permission" "from_sns" {
  statement_id  = "AllowNotifyTopic"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.this.function_name
  principal     = "sns.amazonaws.com"
  source_arn    = aws_sns_topic.notify.arn
}
