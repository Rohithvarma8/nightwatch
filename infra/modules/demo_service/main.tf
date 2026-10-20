data "aws_region" "current" {}
data "aws_caller_identity" "current" {}

locals {
  region     = data.aws_region.current.region
  account    = data.aws_caller_identity.current.account_id
  alias_name = "live"
  alarm_name = "nightwatch-checkout-latency-p95"
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

# --- checkout-service ------------------------------------------------------------------

resource "aws_cloudwatch_log_group" "checkout" {
  name              = "/aws/lambda/${var.service_name}"
  retention_in_days = var.log_retention_days
}

resource "aws_iam_role" "checkout" {
  name               = "nightwatch-${var.service_name}-lambda"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy" "checkout" {
  name = "logs"
  role = aws_iam_role.checkout.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
      Resource = "${aws_cloudwatch_log_group.checkout.arn}:*"
    }]
  })
}

resource "aws_lambda_function" "checkout" {
  function_name    = var.service_name
  role             = aws_iam_role.checkout.arn
  runtime          = "python3.12"
  architectures    = ["arm64"]
  handler          = "app.handler"
  filename         = var.checkout_zip_path
  source_code_hash = filebase64sha256(var.checkout_zip_path)
  memory_size      = 128
  timeout          = 5
  publish          = true

  environment {
    variables = { CHECKOUT_MODE = "good" }
  }

  lifecycle {
    # make bad-deploy / good-deploy set CHECKOUT_MODE on $LATEST before publishing a version.
    ignore_changes = [environment]
  }

  depends_on = [aws_cloudwatch_log_group.checkout, aws_iam_role_policy.checkout]
}

resource "aws_lambda_alias" "live" {
  name             = local.alias_name
  function_name    = aws_lambda_function.checkout.function_name
  function_version = aws_lambda_function.checkout.version

  lifecycle {
    ignore_changes = [function_version] # CodeDeploy owns which version is live
  }
}

resource "aws_apigatewayv2_api" "checkout" {
  name          = var.service_name
  protocol_type = "HTTP"
}

resource "aws_apigatewayv2_integration" "checkout" {
  api_id                 = aws_apigatewayv2_api.checkout.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_alias.live.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "checkout" {
  api_id    = aws_apigatewayv2_api.checkout.id
  route_key = "GET /checkout"
  target    = "integrations/${aws_apigatewayv2_integration.checkout.id}"
}

resource "aws_apigatewayv2_stage" "checkout" {
  api_id      = aws_apigatewayv2_api.checkout.id
  name        = "$default"
  auto_deploy = true

  default_route_settings {
    throttling_rate_limit  = 5
    throttling_burst_limit = 10
  }
}

resource "aws_lambda_permission" "checkout_api" {
  statement_id  = "AllowCheckoutApi"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.checkout.function_name
  qualifier     = aws_lambda_alias.live.name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.checkout.execution_arn}/*/*"
}

# --- CodeDeploy (AllAtOnce, no automatic rollback: we want the alarm to fire) -------------

data "aws_iam_policy_document" "codedeploy_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["codedeploy.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "codedeploy" {
  name               = "nightwatch-${var.service_name}-codedeploy"
  assume_role_policy = data.aws_iam_policy_document.codedeploy_assume.json
}

# AWSCodeDeployRoleForLambdaLimited's actions, scoped to this one function.
resource "aws_iam_role_policy" "codedeploy" {
  name = "shift-alias"
  role = aws_iam_role.codedeploy.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = ["lambda:GetAlias", "lambda:UpdateAlias", "lambda:GetProvisionedConcurrencyConfig"]
        Resource = [
          aws_lambda_function.checkout.arn,
          "${aws_lambda_function.checkout.arn}:*",
        ]
      },
      { Effect = "Allow", Action = ["cloudwatch:DescribeAlarms"], Resource = "*" },
    ]
  })
}

resource "aws_codedeploy_app" "checkout" {
  name             = var.service_name
  compute_platform = "Lambda"
}

resource "aws_codedeploy_deployment_group" "checkout" {
  app_name               = aws_codedeploy_app.checkout.name
  deployment_group_name  = var.service_name
  service_role_arn       = aws_iam_role.codedeploy.arn
  deployment_config_name = "CodeDeployDefault.LambdaAllAtOnce"

  deployment_style {
    deployment_type   = "BLUE_GREEN"
    deployment_option = "WITH_TRAFFIC_CONTROL"
  }

  auto_rollback_configuration {
    enabled = false
  }
}

# --- p95 latency alarm on the live alias ---------------------------------------------------

resource "aws_cloudwatch_metric_alarm" "latency" {
  alarm_name          = local.alarm_name
  alarm_description   = "${var.service_name} p95 latency on the live alias is above ${var.latency_threshold_ms} ms."
  namespace           = "AWS/Lambda"
  metric_name         = "Duration"
  extended_statistic  = "p95"
  period              = 60
  evaluation_periods  = 3
  datapoints_to_alarm = 2
  threshold           = var.latency_threshold_ms
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    FunctionName = var.service_name
    Resource     = "${var.service_name}:${local.alias_name}"
  }
}

# --- load generator (Scheduler, 1/min) -----------------------------------------------------

resource "aws_cloudwatch_log_group" "loadgen" {
  name              = "/aws/lambda/nightwatch-loadgen"
  retention_in_days = var.log_retention_days
}

resource "aws_iam_role" "loadgen" {
  name               = "nightwatch-loadgen-lambda"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy" "loadgen" {
  name = "logs"
  role = aws_iam_role.loadgen.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
      Resource = "${aws_cloudwatch_log_group.loadgen.arn}:*"
    }]
  })
}

resource "aws_lambda_function" "loadgen" {
  function_name    = "nightwatch-loadgen"
  role             = aws_iam_role.loadgen.arn
  runtime          = "python3.12"
  architectures    = ["arm64"]
  handler          = "app.handler"
  filename         = var.loadgen_zip_path
  source_code_hash = filebase64sha256(var.loadgen_zip_path)
  memory_size      = 128
  timeout          = 50 # 20 requests × ≤ 1.1 s, well under the 60 s schedule

  environment {
    variables = {
      CHECKOUT_URL = "${aws_apigatewayv2_api.checkout.api_endpoint}/checkout"
      REQUESTS     = "20"
    }
  }

  depends_on = [aws_cloudwatch_log_group.loadgen, aws_iam_role_policy.loadgen]
}

data "aws_iam_policy_document" "scheduler_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["scheduler.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "loadgen_scheduler" {
  name               = "nightwatch-loadgen-scheduler"
  assume_role_policy = data.aws_iam_policy_document.scheduler_assume.json
}

resource "aws_iam_role_policy" "loadgen_scheduler" {
  name = "invoke-loadgen"
  role = aws_iam_role.loadgen_scheduler.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = "lambda:InvokeFunction"
      Resource = aws_lambda_function.loadgen.arn
    }]
  })
}

resource "aws_scheduler_schedule" "loadgen" {
  name                = "nightwatch-loadgen"
  schedule_expression = "rate(1 minute)"
  state               = var.loadgen_enabled ? "ENABLED" : "DISABLED"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_lambda_function.loadgen.arn
    role_arn = aws_iam_role.loadgen_scheduler.arn
    input    = jsonencode({})

    retry_policy {
      maximum_retry_attempts = 0
    }
  }
}
