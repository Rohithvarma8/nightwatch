locals {
  alias_name = "live"
  # The SDK's DNS-rebinding check compares the Host header against this list.
  api_host = replace(aws_apigatewayv2_api.this.api_endpoint, "https://", "")
}

# --- Logs + IAM -------------------------------------------------------------

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

data "aws_iam_policy_document" "logs" {
  statement {
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.this.arn}:*"]
  }
}

resource "aws_iam_role_policy" "logs" {
  name   = "logs"
  role   = aws_iam_role.this.id
  policy = data.aws_iam_policy_document.logs.json
}

# Hot path is DynamoDB-only and read-only: household profile GetItem + GSI1 Query.
data "aws_iam_policy_document" "table_read" {
  statement {
    actions   = ["dynamodb:GetItem", "dynamodb:Query"]
    resources = [var.table_arn, "${var.table_arn}/index/GSI1"]
  }
}

# acknowledge / notify_contact / escalate: UpdateItem on incidents (and their timeline items)
# and on per-contact notification rate-limit counters. Nothing else is writable.
data "aws_iam_policy_document" "actions" {
  statement {
    sid       = "UpdateIncidents"
    actions   = ["dynamodb:UpdateItem"]
    resources = [var.table_arn]
    condition {
      test     = "ForAllValues:StringLike"
      variable = "dynamodb:LeadingKeys"
      values   = ["INC#*", "RATE#*"]
    }
  }

  statement {
    sid       = "PublishNotifications"
    actions   = ["sns:Publish"]
    resources = [var.notify_topic_arn]
  }
}

resource "aws_iam_role_policy" "actions" {
  name   = "actions"
  role   = aws_iam_role.this.id
  policy = data.aws_iam_policy_document.actions.json
}

resource "aws_iam_role_policy" "table_read" {
  name   = "table-read"
  role   = aws_iam_role.this.id
  policy = data.aws_iam_policy_document.table_read.json
}

# --- Lambda (uvicorn behind Lambda Web Adapter) -----------------------------

resource "aws_lambda_function" "this" {
  function_name    = var.name
  role             = aws_iam_role.this.arn
  runtime          = "python3.12"
  architectures    = ["arm64"]
  handler          = "run.sh"
  filename         = var.zip_path
  source_code_hash = filebase64sha256(var.zip_path)
  memory_size      = var.memory_size
  timeout          = var.timeout
  layers           = [var.lambda_web_adapter_layer_arn]
  publish          = true # versions back the `live` alias (needed for provisioned concurrency)

  environment {
    variables = {
      AWS_LAMBDA_EXEC_WRAPPER      = "/opt/bootstrap"
      AWS_LWA_PORT                 = "8080"
      AWS_LWA_READINESS_CHECK_PATH = "/healthz"
      MCP_ALLOWED_HOSTS            = local.api_host
      NIGHTWATCH_TABLE             = var.table_name
      HOUSEHOLD_ID                 = var.household_id
      NOTIFY_TOPIC_ARN             = var.notify_topic_arn
    }
  }

  depends_on = [
    aws_cloudwatch_log_group.this,
    aws_iam_role_policy.logs,
    aws_iam_role_policy.table_read,
    aws_iam_role_policy.actions,
  ]
}

resource "aws_lambda_alias" "live" {
  name             = local.alias_name
  function_name    = aws_lambda_function.this.function_name
  function_version = aws_lambda_function.this.version
}

resource "aws_lambda_provisioned_concurrency_config" "live" {
  count                             = var.provisioned_concurrency > 0 ? 1 : 0
  function_name                     = aws_lambda_function.this.function_name
  qualifier                         = aws_lambda_alias.live.name
  provisioned_concurrent_executions = var.provisioned_concurrency
}

# --- HTTP API ---------------------------------------------------------------

resource "aws_apigatewayv2_api" "this" {
  name          = var.name
  protocol_type = "HTTP"
}

resource "aws_apigatewayv2_integration" "lambda" {
  api_id                 = aws_apigatewayv2_api.this.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_alias.live.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "this" {
  for_each  = toset(["ANY /mcp", "GET /healthz"])
  api_id    = aws_apigatewayv2_api.this.id
  route_key = each.value
  target    = "integrations/${aws_apigatewayv2_integration.lambda.id}"
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.this.id
  name        = "$default"
  auto_deploy = true

  default_route_settings {
    throttling_rate_limit  = var.throttle_rate_limit
    throttling_burst_limit = var.throttle_burst_limit
  }
}

resource "aws_lambda_permission" "apigw" {
  statement_id  = "AllowHttpApiInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.this.function_name
  qualifier     = aws_lambda_alias.live.name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.this.execution_arn}/*/*"
}
