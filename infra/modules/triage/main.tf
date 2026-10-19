data "aws_region" "current" {}
data "aws_caller_identity" "current" {}

locals {
  model_ids = compact([var.model_id, var.fallback_model_id])
  # Cross-region inference profiles ("us.…", "global.…") need the profile ARN plus the
  # foundation model in every region the profile routes to; plain IDs need just the model.
  profile_prefix = "^(us|eu|apac|global)\\."
  model_arns = flatten([
    for id in local.model_ids : length(regexall(local.profile_prefix, id)) > 0 ? [
      "arn:aws:bedrock:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:inference-profile/${id}",
      "arn:aws:bedrock:*::foundation-model/${replace(id, "/${local.profile_prefix}/", "")}",
      ] : [
      "arn:aws:bedrock:${data.aws_region.current.region}::foundation-model/${id}",
    ]
  ])
}

resource "aws_cloudwatch_log_group" "this" {
  name              = "/aws/lambda/${var.name}"
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
  name               = "${var.name}-lambda"
  assume_role_policy = data.aws_iam_policy_document.assume.json
}

data "aws_iam_policy_document" "this" {
  statement {
    sid       = "Logs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.this.arn}:*"]
  }

  statement {
    sid       = "ReadIncidentAndSignals"
    actions   = ["dynamodb:GetItem", "dynamodb:BatchGetItem", "dynamodb:UpdateItem"]
    resources = [var.table_arn]
    condition {
      test     = "ForAllValues:StringLike"
      variable = "dynamodb:LeadingKeys"
      values   = ["INC#*", "SIG#*"]
    }
  }

  statement {
    sid       = "ReadHouseholdProfile"
    actions   = ["dynamodb:GetItem"] # time zone for the replay until-time
    resources = [var.table_arn]
    condition {
      test     = "ForAllValues:StringLike"
      variable = "dynamodb:LeadingKeys"
      values   = ["HH#*"]
    }
  }

  statement {
    sid       = "InvokeTriageModels"
    actions   = ["bedrock:InvokeModel"]
    resources = local.model_arns
  }
}

resource "aws_iam_role_policy" "this" {
  name   = "triage"
  role   = aws_iam_role.this.id
  policy = data.aws_iam_policy_document.this.json
}

resource "aws_lambda_function" "this" {
  function_name    = var.name
  role             = aws_iam_role.this.arn
  runtime          = "python3.12"
  architectures    = ["arm64"]
  handler          = "nightwatch_pipeline.triage.handler.handler"
  filename         = var.zip_path
  source_code_hash = filebase64sha256(var.zip_path)
  memory_size      = 512
  timeout          = 30 # model budget is 8 s; the rest covers Strands import on cold start

  environment {
    variables = {
      NIGHTWATCH_TABLE         = var.table_name
      NIGHTWATCH_BUS           = var.bus_name
      TRIAGE_MODEL_ID          = var.model_id
      TRIAGE_FALLBACK_MODEL_ID = var.fallback_model_id
    }
  }

  depends_on = [aws_cloudwatch_log_group.this, aws_iam_role_policy.this]
}

resource "aws_cloudwatch_event_rule" "incident_changed" {
  name           = "${var.name}-incident-changed"
  event_bus_name = var.bus_name
  event_pattern  = jsonencode({ "detail-type" = ["IncidentChanged"] })
}

resource "aws_cloudwatch_event_target" "this" {
  rule           = aws_cloudwatch_event_rule.incident_changed.name
  event_bus_name = var.bus_name
  arn            = aws_lambda_function.this.arn

  retry_policy {
    maximum_event_age_in_seconds = 900
    maximum_retry_attempts       = 2
  }
}

resource "aws_lambda_permission" "from_bus" {
  statement_id  = "AllowIncidentChangedRule"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.this.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.incident_changed.arn
}
