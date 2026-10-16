locals {
  ingester_name = "${var.name_prefix}-ingest-nws"
  builder_name  = "${var.name_prefix}-incident-builder"
  common_env = {
    NIGHTWATCH_TABLE = var.table_name
    NIGHTWATCH_BUS   = aws_cloudwatch_event_bus.this.name
    HOUSEHOLD_IDS    = join(",", var.household_ids)
  }
}

resource "aws_cloudwatch_event_bus" "this" {
  name = var.name_prefix
}

data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

# --- NWS ingester -------------------------------------------------------------

resource "aws_cloudwatch_log_group" "ingester" {
  name              = "/aws/lambda/${local.ingester_name}"
  retention_in_days = var.log_retention_days
}

resource "aws_iam_role" "ingester" {
  name               = "${local.ingester_name}-lambda"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

data "aws_iam_policy_document" "ingester" {
  statement {
    sid       = "Logs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.ingester.arn}:*"]
  }

  statement {
    sid       = "ReadHouseholds"
    actions   = ["dynamodb:GetItem"]
    resources = [var.table_arn]
    condition {
      test     = "ForAllValues:StringLike"
      variable = "dynamodb:LeadingKeys"
      values   = ["HH#*"]
    }
  }

  statement {
    sid       = "DedupeSignals"
    actions   = ["dynamodb:PutItem", "dynamodb:DeleteItem"]
    resources = [var.table_arn]
    condition {
      test     = "ForAllValues:StringLike"
      variable = "dynamodb:LeadingKeys"
      values   = ["SIG#*"]
    }
  }

  statement {
    sid       = "PublishSignals"
    actions   = ["events:PutEvents"]
    resources = [aws_cloudwatch_event_bus.this.arn]
  }
}

resource "aws_iam_role_policy" "ingester" {
  name   = "ingest"
  role   = aws_iam_role.ingester.id
  policy = data.aws_iam_policy_document.ingester.json
}

resource "aws_lambda_function" "ingester" {
  function_name    = local.ingester_name
  role             = aws_iam_role.ingester.arn
  runtime          = "python3.12"
  architectures    = ["arm64"]
  handler          = "nightwatch_pipeline.ingest.nws.handler"
  filename         = var.zip_path
  source_code_hash = filebase64sha256(var.zip_path)
  memory_size      = 256
  timeout          = 60

  environment {
    variables = merge(local.common_env, { NWS_USER_AGENT = var.nws_user_agent })
  }

  depends_on = [aws_cloudwatch_log_group.ingester, aws_iam_role_policy.ingester]
}

# --- Incident builder -----------------------------------------------------------

resource "aws_cloudwatch_log_group" "builder" {
  name              = "/aws/lambda/${local.builder_name}"
  retention_in_days = var.log_retention_days
}

resource "aws_iam_role" "builder" {
  name               = "${local.builder_name}-lambda"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

data "aws_iam_policy_document" "builder" {
  statement {
    sid       = "Logs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.builder.arn}:*"]
  }

  statement {
    sid = "WriteIncidents"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:DeleteItem",
      "dynamodb:ConditionCheckItem",
    ]
    resources = [var.table_arn]
    condition {
      test     = "ForAllValues:StringLike"
      variable = "dynamodb:LeadingKeys"
      values   = ["HH#*", "INC#*"]
    }
  }

  statement {
    sid       = "QueryActive"
    actions   = ["dynamodb:Query"]
    resources = ["${var.table_arn}/index/GSI1"]
  }
}

resource "aws_iam_role_policy" "builder" {
  name   = "incidents"
  role   = aws_iam_role.builder.id
  policy = data.aws_iam_policy_document.builder.json
}

resource "aws_lambda_function" "builder" {
  function_name    = local.builder_name
  role             = aws_iam_role.builder.arn
  runtime          = "python3.12"
  architectures    = ["arm64"]
  handler          = "nightwatch_pipeline.incidents.handler.handler"
  filename         = var.zip_path
  source_code_hash = filebase64sha256(var.zip_path)
  memory_size      = 256
  timeout          = 30

  environment {
    variables = local.common_env
  }

  depends_on = [aws_cloudwatch_log_group.builder, aws_iam_role_policy.builder]
}

# Bus → builder for every signal (live and replay).
resource "aws_cloudwatch_event_rule" "signals" {
  name           = "${var.name_prefix}-signals"
  event_bus_name = aws_cloudwatch_event_bus.this.name
  event_pattern  = jsonencode({ "detail-type" = ["Signal"] })
}

resource "aws_cloudwatch_event_target" "builder" {
  rule           = aws_cloudwatch_event_rule.signals.name
  event_bus_name = aws_cloudwatch_event_bus.this.name
  arn            = aws_lambda_function.builder.arn

  retry_policy {
    maximum_event_age_in_seconds = 3600
    maximum_retry_attempts       = 10
  }
}

resource "aws_lambda_permission" "builder_from_bus" {
  statement_id  = "AllowSignalsRule"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.builder.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.signals.arn
}

# --- Schedules: NWS poll + expiry sweep -------------------------------------------

data "aws_iam_policy_document" "scheduler_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["scheduler.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "scheduler" {
  name               = "${var.name_prefix}-scheduler"
  assume_role_policy = data.aws_iam_policy_document.scheduler_assume.json
}

data "aws_iam_policy_document" "scheduler" {
  statement {
    actions   = ["lambda:InvokeFunction"]
    resources = [aws_lambda_function.ingester.arn, aws_lambda_function.builder.arn]
  }
}

resource "aws_iam_role_policy" "scheduler" {
  name   = "invoke"
  role   = aws_iam_role.scheduler.id
  policy = data.aws_iam_policy_document.scheduler.json
}

resource "aws_scheduler_schedule" "nws" {
  name                = "${var.name_prefix}-ingest-nws"
  schedule_expression = var.nws_schedule

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_lambda_function.ingester.arn
    role_arn = aws_iam_role.scheduler.arn
    input    = jsonencode({})

    retry_policy {
      maximum_retry_attempts = 0 # the next run is 5 minutes away
    }
  }
}

resource "aws_scheduler_schedule" "sweep" {
  name                = "${var.name_prefix}-incident-sweep"
  schedule_expression = var.nws_schedule

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_lambda_function.builder.arn
    role_arn = aws_iam_role.scheduler.arn
    input    = jsonencode({ action = "sweep" })

    retry_policy {
      maximum_retry_attempts = 0
    }
  }
}
