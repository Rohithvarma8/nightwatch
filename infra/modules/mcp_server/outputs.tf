output "mcp_url" {
  description = "Streamable HTTP MCP endpoint."
  value       = "${aws_apigatewayv2_api.this.api_endpoint}/mcp"
}

output "api_endpoint" {
  description = "HTTP API base URL ($default stage)."
  value       = aws_apigatewayv2_api.this.api_endpoint
}

output "function_name" {
  description = "Lambda function name."
  value       = aws_lambda_function.this.function_name
}

output "log_group" {
  description = "CloudWatch log group for the function."
  value       = aws_cloudwatch_log_group.this.name
}
