output "bus_name" {
  description = "EventBridge bus for signals."
  value       = aws_cloudwatch_event_bus.this.name
}

output "ingester_function_name" {
  description = "NWS ingester Lambda."
  value       = aws_lambda_function.ingester.function_name
}

output "builder_function_name" {
  description = "Incident builder Lambda."
  value       = aws_lambda_function.builder.function_name
}
